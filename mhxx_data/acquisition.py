"""Extract local gathering and combining data without executing site scripts."""

from __future__ import annotations

import re

from lxml import html

from .domains import grid, integer, links, locator, snapshot
from .html_source import cells, normalized, restore_values, rows, text

RANKS = {"下位": "LR", "上位": "HR", "G级": "G"}


def numeric_range(value):
    value = normalized(value)
    match = re.fullmatch(r"(\d+)(?:[-~～](\d+))?", value)
    if not match:
        raise ValueError(f"Unrecognized numeric range: {value}")
    low, high = int(match[1]), int(match[2] or match[1])
    if low < 1 or high < low:
        raise ValueError(f"Invalid numeric range: {value}")
    return low, high


def percentage(value):
    match = re.fullmatch(r"(\d+)%", normalized(value))
    if not match or not 0 <= int(match[1]) <= 100:
        raise ValueError(f"Unrecognized percentage: {value}")
    return int(match[1])


def gathering_attempts(value):
    match = re.fullmatch(r"(固定|ランダム)\s*(\[稀有度\])?\s*(∞|\d+(?:-\d+)?)回", value)
    if not match:
        raise ValueError(f"Unrecognized gathering attempts: {value}")
    infinite = match[3] == "∞"
    low, high = (None, None) if infinite else numeric_range(match[3])
    return {"fixed": match[1] == "固定", "rare": bool(match[2]),
            "attempts_min": low, "attempts_max": high, "attempts_infinite": infinite}


def item_reference(cell, page):
    refs = links(cell, page)
    if len(refs) > 1:
        raise ValueError(f"Multiple item links at {page} {locator(cell)}")
    return {"item_page": refs[0]["page"] if refs else None, "label": text(cell), "xpath": locator(cell)}


def parse_map(document, page, name):
    result = {"page": page, "name": name, "sections": [], "issues": [],
              "images": document.xpath('//img[contains(@src,"/map/")]/@src'),
              "notes": [{"text": text(e), "xpath": locator(e)} for e in document.xpath(
                  '//*[@id="main_1"]//*[contains(concat(" ",normalize-space(@class)," ")," box1 ") and not(ancestor::table)]')]}
    for table in document.xpath('//table[not(ancestor::table)]'):
        header = [text(c) for c in cells(rows(table)[0])]
        if header != ["采集", "回数", "道具", "確率"]:
            raise ValueError(f"Unknown gathering table at {page}: {header}")
        area_heading, rank_heading = table.xpath('preceding::h3[1]'), table.xpath('preceding::h4[1]')
        if not area_heading or not rank_heading:
            raise ValueError(f"Missing map table context at {page}")
        area = text(area_heading[0]).removeprefix("区域")
        rank = RANKS.get(text(rank_heading[0]))
        if not (area.isdigit() or area in ("秘境", "BC")) or rank is None:
            raise ValueError(f"Unrecognized map context at {page}: {area}, {text(rank_heading[0])}")
        section = {"ordinal": len(result["sections"]), "area": area,
                   "area_anchor": area_heading[0].get("id"), "rank": rank, "nodes": [],
                   "empty_text": None, "source": snapshot(table, page)}
        by_cell = {}
        for row, cols in zip(rows(table)[1:], grid(table)[1:]):
            if len(cols) == 4 and len({id(c) for c in cols}) == 1:
                if text(cols[0]) != "无し":
                    raise ValueError(f"Unknown empty map section at {page}: {text(row)}")
                section["empty_text"] = text(cols[0])
                continue
            if len(cols) != 4 or any(c is None for c in cols):
                raise ValueError(f"Unrecognized gathering row at {page}: {text(row)}")
            key = locator(cols[1])  # normal/rare variants share a point cell, but not an attempts cell
            if key not in by_cell:
                point = integer(normalized(text(cols[0])))
                icons = cols[0].xpath('.//img/@src')
                if point is None or len(icons) != 1:
                    raise ValueError(f"Unrecognized gathering point at {page}: {text(cols[0])}")
                node = {"ordinal": len(section["nodes"]), "point": point, "point_label": text(cols[0]),
                        "icon": icons[0], "attempts_raw": text(cols[1]), "xpath": key,
                        **gathering_attempts(text(cols[1])), "items": []}
                section["nodes"].append(node)
                by_cell[key] = node
            node = by_cell[key]
            ref = item_reference(cols[2], page)
            amount = re.search(r"[x×ｘ]\s*(\d+)\s*$", ref["label"])
            quantity = int(amount[1]) if amount else 1
            if quantity < 1:
                raise ValueError(f"Invalid gathering quantity at {page}: {ref['label']}")
            reward = {**ref, "quantity": quantity, "percentage": percentage(text(cols[3])),
                      "raw_text": text(row), "xpath": locator(row), "row_anchor": row.get("id")}
            if ref["item_page"] is None:
                result["issues"].append({"kind": "unlinked_gathering_item", "xpath": locator(row), "raw_text": ref["label"]})
            node["items"].append(reward)
        if section["empty_text"] is not None and section["nodes"]:
            raise ValueError(f"Both empty and populated gathering section at {page}")
        result["sections"].append(section)
    return result


def parse_combining(document, page):
    result = {"page": page, "recipes": [], "tables": [], "issues": []}
    for table in document.xpath('//table[not(ancestor::table)]'):
        header = [text(c) for c in cells(rows(table)[0])]
        if header != ["调合结果", "", "素材1", "", "素材2", "个数", "成功率"]:
            raise ValueError(f"Unrecognized combining table: {header}")
        category = text(table.xpath('preceding::h4[1]')[0])
        result["tables"].append(snapshot(table, page))
        for row in rows(table)[1:]:
            cols = cells(row)
            if len(cols) != 7 or text(cols[1]) != "=" or text(cols[3]) != "+":
                raise ValueError(f"Unrecognized combining row: {text(row)}")
            output = item_reference(cols[0], page)
            inputs = [item_reference(cols[n], page) for n in (2, 4)]
            low, high = numeric_range(text(cols[5]))
            recipe = {"ordinal": len(result["recipes"]), "category": category,
                      "output": output, "inputs": inputs, "amount_min": low, "amount_max": high,
                      "percentage": percentage(text(cols[6])), "xpath": locator(row),
                      "row_anchor": row.get("id"), "raw_cells": [text(c) for c in cols]}
            result["recipes"].append(recipe)
            for role, ref in [("output", output), *[(f"input_{n + 1}", r) for n, r in enumerate(inputs)]]:
                if ref["item_page"] is None:
                    result["issues"].append({"kind": "unlinked_combining_item", "role": role,
                                             "ordinal": recipe["ordinal"], "xpath": ref["xpath"], "raw_text": ref["label"]})
    return result


def extract_acquisition(root, pages):
    maps, combining = [], []
    for p in pages:
        if p["category"] != "地图" and not (p["category"] == "道具入手" and p["title"] == "调合列表"):
            continue
        document = html.fromstring((root / p["path"]).read_bytes())
        restore_values(document)
        if p["category"] == "地图":
            maps.append(parse_map(document, p["path"], p["title"]))
        else:
            combining.append(parse_combining(document, p["path"]))
    if len(combining) != 1:
        raise ValueError(f"Expected one combining catalog; got {len(combining)}")
    return {"maps": maps, "combining": combining[0]}

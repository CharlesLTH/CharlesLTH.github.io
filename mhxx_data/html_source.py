"""Decode the existing site without executing any JavaScript.

Site page IDs, community database IDs, and native game IDs are distinct.
All text/values here are observations from the local MHXX site, not corrections
to the imported MHGU database.
"""

from __future__ import annotations

import ast
import hashlib
import posixpath
import re
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from lxml import html

ASSIGNMENT = re.compile(
    r'''\$\(\s*(['"])\.(cpg\w+)\1\s*\)\.html\(\s*((?:'(?:\\.|[^'\\])*')|(?:"(?:\\.|[^"\\])*"))\s*\)'''
)
WEAPON_TYPES = [
    "Great Sword", "Long Sword", "Sword and Shield", "Dual Blades", "Hammer",
    "Hunting Horn", "Lance", "Gunlance", "Switch Axe", "Charge Blade",
    "Insect Glaive", "Bow", "Light Bowgun", "Heavy Bowgun",
]
ELEMENTS = {
    "火": "Fire", "水": "Water", "雷": "Thunder", "冰": "Ice", "氷": "Ice",
    "龙": "Dragon", "龍": "Dragon", "毒": "Poison", "麻痹": "Paralysis",
    "麻痺": "Paralysis", "睡眠": "Sleep", "爆破": "Blastblight",
}


def text(node) -> str:
    return " ".join(" ".join(node.itertext()).split())


def normalized(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def weapon_name(value: str) -> str:
    return normalized(value).replace("[XX]", "").rstrip("↓")


def page_ref(href: str, current: str) -> str | None:
    url = urlsplit(href)
    if url.scheme or url.netloc or not url.path:
        return None
    path = posixpath.normpath(posixpath.join(posixpath.dirname(current), url.path))
    return path if re.fullmatch(r"(?:ida|data)/[^/]+\.html", path) else None


def restore_values(document) -> int:
    """Accept only literal jQuery .html assignments; never eval/execute code."""
    values = {}
    for script in document.xpath("//script[not(@src)]"):
        for _, selector, literal in ASSIGNMENT.findall(script.text or ""):
            value = ast.literal_eval(literal)
            if not isinstance(value, str):
                raise ValueError("Non-string placeholder value")
            if selector in values and values[selector] != value:
                raise ValueError(f"Conflicting placeholder assignment: {selector}")
            values[selector] = value
    count = 0
    for span in document.xpath("//span[@class]"):
        classes = [c for c in span.get("class").split() if c.startswith("cpg")]
        for selector in classes:
            if selector not in values:
                raise ValueError(f"Unresolved placeholder: {selector}")
            # Keep the span/tail and replace its content, as jQuery .html does.
            for child in list(span):
                span.remove(child)
            fragment = html.fragment_fromstring(values[selector], create_parent="div")
            span.text = fragment.text
            for child in list(fragment):
                span.append(child)
            count += 1
    for script in document.xpath("//script"):
        script.drop_tree()
    return count


def rows(table):
    return table.xpath("./tr|./thead/tr|./tbody/tr|./tfoot/tr")


def cells(row):
    return row.xpath("./th|./td")


def segments(node, block_breaks=False):
    """BR-delimited text with link evidence; nested styling does not split rows."""
    result = []
    chunks, links = [], []

    def flush():
        nonlocal chunks, links
        value = " ".join(" ".join(chunks).split())
        if value or links:
            result.append({"text": value, "links": links})
        chunks, links = [], []

    def walk(el):
        if el.tag == "br":
            flush()
            return
        if block_breaks and el.tag == "div":
            flush()
        if el.tag == "a":
            links.append({"href": el.get("href", ""), "text": text(el)})
        if el.text:
            chunks.append(el.text)
        for child in el:
            if isinstance(child.tag, str):
                walk(child)
            if child.tail:
                chunks.append(child.tail)
        if block_breaks and el.tag == "div":
            flush()

    walk(node)
    flush()
    return result


def int_match(pattern, value, default=None):
    match = re.search(pattern, value)
    return int(match[1]) if match else default


def profile(stats: str, level: int) -> dict:
    attack = int_match(r"攻击\s*[:：]\s*(\d+)", stats)
    slots = re.search(r"孔槽\s*[:：]\s*([◯○〇●\-\s]+)", stats)
    if attack is None or slots is None:
        raise ValueError(f"Unrecognized weapon performance: {stats}")
    affinity = re.search(r"会心\s*([+\-\d\s/]+)\s*%", stats)
    elements = [(ELEMENTS[m[1]], int(m[2])) for m in re.finditer(
        r"(麻痹|麻痺|睡眠|爆破|火|水|雷|冰|氷|龙|龍|毒)\s*(\d+)", stats
    )]
    return {
        "level": level, "attack": attack,
        "slots": sum(slots[1].count(c) for c in "◯○〇●"),
        "affinity": re.sub(r"\s|\+", "", affinity[1]) if affinity else "0",
        "defense": int_match(r"防御\s*\+\s*(\d+)", stats, 0),
        "elements": sorted(elements),
    }


def signature(wtype: str, levels: list[dict]) -> tuple:
    return (wtype, tuple((p["level"], p["attack"], p["slots"], p["affinity"],
                         p["defense"], tuple(tuple(e) for e in p["elements"]))
                        for p in levels))


def parse_recipe(parts, page: str, level: int, kind: str, locator: str):
    ingredients, points, unparsed, money = [], [], [], None
    for segment in parts:
        value = segment["text"]
        if "入手端材" in value:
            break  # output scraps are not recipe inputs
        if not value:
            continue
        amount = re.search(r"[x×ｘ]\s*(\d+)", value)
        refs = [(page_ref(a["href"], page), a) for a in segment["links"]]
        refs = [(ref, a) for ref, a in refs if ref and ref.startswith("ida/")]
        if refs:
            if len(refs) != 1 or not amount:
                unparsed.append(value)
                continue
            ref, anchor = refs[0]
            ingredients.append({"item_page": ref, "quantity": int(amount[1]),
                                "label": anchor["text"], "raw_text": value})
        elif amount and "素材" in value:
            points.append({"label": value[:amount.start()].strip(),
                           "points": int(amount[1]), "raw_text": value})
        elif re.fullmatch(r"\d+\s*z", value):
            money = int_match(r"(\d+)", value)
        elif not re.fullmatch(r"\[.*?\]|[-—]+", value):
            unparsed.append(value)
    return {"level": level, "kind": kind, "ingredients": ingredients,
            "material_points": points, "money": money, "unparsed": unparsed,
            "locator": locator, "raw_text": " | ".join(s["text"] for s in parts)}


def parse_recipes(cell, page: str, level: int, kind: str, locator: str):
    """Production and upgrade recipes can coexist in a single table cell."""
    result, parts = [], []

    def finish():
        if parts:
            recipe = parse_recipe(parts, page, level, kind, locator)
            if (recipe["ingredients"] or recipe["material_points"]
                    or recipe["money"] is not None or recipe["unparsed"]):
                result.append(recipe)

    for segment in segments(cell):
        marker = re.fullmatch(r"\[(生产G?|生産G?|強化|强化)\]", segment["text"])
        if marker:
            finish()
            parts = []
            kind = "Create" if marker[1].startswith(("生产", "生産")) else "Improve"
        parts.append(segment)
    finish()
    return result


def parse_weapon(document, page: str) -> dict:
    links = document.xpath('//*[@id="bread"]/li[last()]/a/@href')
    index = int(re.search(r"(\d+)\.html", links[0])[1])
    offset = index - (2882 if index >= 2882 else 2700 if index >= 2700 else 1900)
    wtype = WEAPON_TYPES[offset]
    tables = document.xpath("//table[not(ancestor::table)]")
    performance, upgrades = rows(tables[1])[1:], rows(tables[2])[1:]
    if len(performance) != len(upgrades):
        raise ValueError("Performance and upgrade row counts differ")
    levels, recipes, branches = [], [], []
    tree = document.getroottree()
    for row, upgrade in zip(performance, upgrades):
        cols, upgrade_cols = cells(row), cells(upgrade)
        level = int_match(r"LV\s*(\d+)", text(cols[0]))
        if level is None:
            raise ValueError(f"Unrecognized weapon level: {text(cols[0])}")
        p = profile(text(cols[1]), level)
        sharpness = []
        for bar in row.xpath('.//div[@class="kbox"]'):
            values = [0.0] * 7
            for span in bar.xpath("./span[@class]"):
                match = re.fullmatch(r"kr([0-6])", span.get("class", ""))
                width = re.search(r"width\s*:\s*([\d.]+)px", span.get("style", ""))
                if match and width:
                    values[int(match[1])] = float(width[1])
            sharpness.append(values)
        p.update({"name": text(upgrade_cols[0]), "raw_stats": text(cols[1]),
                  "sharpness_px": sharpness, "locator": tree.getpath(row),
                  "performance_cells": [text(c) for c in cols]})
        levels.append(p)
        for anchor in upgrade_cols[2].xpath('.//a[@href]'):
            target = page_ref(anchor.get('href'), page)
            if target and target != page:
                branches.append({"level": level, "target_page": target, "label": text(anchor),
                                 "source_xpath": tree.getpath(anchor)})
        if text(upgrade_cols[1]):
            recipes.extend(parse_recipes(upgrade_cols[1], page, level, "Improve",
                                         tree.getpath(upgrade_cols[1])))
    # Production tables follow performance/upgrades, and have named recipe rows.
    issues, ancestors = [], []
    names = {weapon_name(p["name"]): p["level"] for p in levels}
    for table in tables[3:]:
        rr = rows(table)
        if not rr or "必要素材" not in text(rr[0]):
            continue
        for row in rr[1:]:
            cols = cells(row)
            if len(cols) != 2:
                issues.append({"reason": "production_row_shape", "text": text(row)})
                continue
            refs = [page_ref(href, page) for href in cols[0].xpath('.//a/@href')]
            if refs and any(ref != page for ref in refs):
                ancestors.append({"pages": refs, "name": text(cols[0]),
                                  "locator": tree.getpath(row)})
                continue
            name = weapon_name(text(cols[0]))
            level = names.get(name)
            if level is None:
                issues.append({"reason": "production_level_unresolved", "text": text(row)})
                continue
            recipes.extend(parse_recipes(cols[1], page, level, "Create", tree.getpath(cols[1])))
    unique = {}
    for recipe in recipes:
        key = (recipe["level"], recipe["kind"], recipe["money"],
               tuple(sorted((x["item_page"], x["quantity"]) for x in recipe["ingredients"])),
               tuple(sorted((x["label"], x["points"]) for x in recipe["material_points"])))
        if key in unique:
            unique[key]["also_seen_at"].append(recipe["locator"])
        else:
            recipe["also_seen_at"] = []
            unique[key] = recipe
    return {"page": page, "wtype": wtype, "levels": levels, "recipes": list(unique.values()),
            "issues": issues, "ancestors": ancestors, "branches": branches}


def inventory(root: Path):
    pages = []
    for path in sorted(root.rglob("*.html")):
        raw = path.read_bytes()
        source = raw.decode("utf-8-sig")
        bread = re.search(r'<ul\b[^>]*id="bread"[^>]*>(.*?)</ul>', source, re.S)
        category = "navigation"
        if bread:
            d = html.fragment_fromstring(bread[0])
            li = d.xpath("./li")
            if len(li) > 1:
                category = text(li[1])
        title = re.search(r"<title>(.*?)</title>", source, re.S)
        title = " ".join(title[1].split()).split("|")[0].strip() if title else ""
        pages.append({"path": path.relative_to(root).as_posix(), "category": category,
                      "title": title, "sha256": hashlib.sha256(raw).hexdigest()})
    return pages


def extract(root: Path, pages: list[dict]):
    weapons, item_info, counters = [], {}, Counter()
    for page in pages:
        source = (root / page["path"]).read_text(encoding="utf-8-sig")
        document = html.fromstring(source)
        restored = restore_values(document)
        counters["placeholders_restored"] += restored
        counters["pages_with_placeholders"] += bool(restored)
        if page["category"] == "武器" and page["path"].startswith("ida/"):
            try:
                weapon = parse_weapon(document, page["path"])
            except (ValueError, IndexError, AttributeError) as error:
                raise ValueError(f"{page['path']}: {error}") from error
            weapons.append(weapon)
        if page["category"] == "道具" and page["path"].startswith("ida/"):
            tables = document.xpath("//table[not(ancestor::table)]")
            item_info[page["path"]] = {
                "name": page["title"],
                "basic_rows": [[text(c) for c in cells(row)] for row in rows(tables[0])]
                if tables else [],
            }
    return weapons, item_info, dict(counters)

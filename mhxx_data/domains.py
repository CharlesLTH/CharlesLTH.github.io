"""Local monster, quest, armor and skill observations, independent of MHGU IDs.

Unknown values remain text/null; original table cells and locators are retained.
No Japanese/Chinese names are used to guess cross-source identities.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from lxml import html

from .html_source import cells, normalized, page_ref, parse_recipe, restore_values, rows, segments, text

SLOTS = {"1": "Head", "2": "Body", "3": "Arms", "4": "Waist", "5": "Legs"}
SLOT_LABELS = {"头": "Head", "胴": "Body", "腕": "Arms", "腰": "Waist", "脚": "Legs"}
RANKS = {"下位": "LR", "上位": "HR", "G级": "G"}


def grid(table):
    """Expand rowspan/colspan, retaining the actual source cell objects."""
    occupied = {}
    result = []
    for y, row in enumerate(rows(table)):
        x = 0
        for cell in cells(row):
            while (y, x) in occupied:
                x += 1
            width, height = int(cell.get("colspan", 1)), int(cell.get("rowspan", 1))
            for dy in range(height):
                for dx in range(width):
                    if (y + dy, x + dx) in occupied:
                        raise ValueError("Overlapping table spans")
                    occupied[y + dy, x + dx] = cell
            x += width
        columns = [col for yy, col in occupied if yy == y]
        result.append([occupied.get((y, col)) for col in range(max(columns, default=-1) + 1)])
    return result


def integer(value):
    return int(value) if re.fullmatch(r"[+-]?\d+", value) else None


def measured(value, unit):
    match = re.fullmatch(r"(\d+)\s*" + unit, value)
    return int(match[1]) if match else None


def locator(node):
    return node.getroottree().getpath(node)


def links(node, page):
    return [{"page": ref, "href": a.get("href"), "label": text(a), "xpath": locator(a)}
            for a in node.xpath(".//a[@href]") if (ref := page_ref(a.get("href"), page))]


def linked_chunks(node):
    """One link plus its following text, including nested spans (skill points)."""
    result, current = [], None

    def append(value):
        if current is not None and value:
            current["chunks"].append(value)

    def walk(el):
        nonlocal current
        if el.tag == "a":
            current = {"href": el.get("href", ""), "label": text(el), "chunks": [], "xpath": locator(el)}
            result.append(current)
            return
        append(el.text)
        for child in el:
            walk(child)
            append(child.tail)

    walk(node)
    for r in result:
        r["tail"] = " ".join(" ".join(r.pop("chunks")).split())
    return result


def snapshot(table, page):
    """Keep table evidence, including spans, icons and links with fragments."""
    return {"xpath": locator(table), "rows": [
        [{"text": text(c), "lines": [s["text"] for s in segments(c, block_breaks=True)], "xpath": locator(c), "tag": c.tag,
          "rowspan": int(c.get("rowspan", 1)), "colspan": int(c.get("colspan", 1)),
          "links": links(c, page),
          "images": [{k: img.get(k) for k in ("src", "alt", "title") if img.get(k)}
                     for img in c.xpath(".//img")]}
         for c in cells(r)] for r in rows(table)]}


def rewards(cell, page, **context):
    result, issues = [], []
    condition = None
    for ordinal, segment in enumerate(segments(cell, block_breaks=True)):
        raw = segment["text"]
        if not raw or raw in ("-", "—"):
            continue
        refs = [page_ref(a["href"], page) for a in segment["links"]]
        refs = [r for r in refs if r]
        rate = re.search(r"(\d+)\s*%\s*$", raw)
        amount = re.search(r"[x×ｘ]\s*(\d+)", raw)
        if not rate and not refs:
            condition = raw
            continue
        if len(refs) > 1:
            issues.append({"kind": "unparsed_reward", "xpath": locator(cell), "raw_text": raw})
            continue
        if not refs:
            issues.append({"kind": "unlinked_reward", "xpath": locator(cell), "raw_text": raw})
        if not rate:
            issues.append({"kind": "missing_probability", "xpath": locator(cell), "raw_text": raw})
        quantity, percentage = int(amount[1]) if amount else 1, int(rate[1]) if rate else None
        if quantity < 1 or (percentage is not None and not 0 <= percentage <= 100):
            raise ValueError(f"Invalid reward at {page}: {raw}")
        result.append({"item_page": refs[0] if refs else None, "quantity": quantity, "percentage": percentage,
                       "raw_text": raw, "xpath": locator(cell), "segment": ordinal,
                       "condition": condition, **context})
    return result, issues


def monster_quest_rows(table, page):
    """Original appearance list: strengths are display gauges, never HP/rates."""
    result = []
    for row in rows(table)[1:]:
        cols = cells(row)
        if len(cols) != 5:
            raise ValueError(f"Unknown monster quest row at {page}: {locator(row)}")
        quests = [a for a in links(cols[1], page) if a["page"].startswith("ida/")]
        if len(quests) != 1:
            raise ValueError(f"Ambiguous monster quest at {page}: {locator(row)}")
        location = links(cols[2], page)
        monsters = []
        # Each br-delimited monster keeps its own preceding status icon, count
        # and intrusion marker, including anchors nested inside colored spans.
        fragment = html.fromstring(html.tostring(cols[4], encoding="unicode"))
        for img in fragment.xpath('.//img'):
            img.tail = f" [icon:{img.get('src', '')}] " + (img.tail or "")
        for segment in segments(fragment):
            if not segment["links"]:
                continue
            icon = re.search(r"\[icon:([^\]]+)\]", segment["text"])
            count = re.search(r"[x×ｘ]\s*(\d+)", segment["text"])
            for anchor in segment["links"]:
                target = page_ref(anchor["href"], page)
                if target:
                    monsters.append({"page": target, "label": anchor["text"],
                        "count": int(count[1]) if count else 1,
                        "intrusion": bool(icon and "/rannyu" in icon[1]),
                        "source_icon": icon[1] if icon else None})
        strength = {}
        for key, cls in (("health_bar", "success"), ("defense_bar", "warning")):
            bars = cols[3].xpath(f'.//*[contains(concat(" ",normalize-space(@class)," ")," progress-bar-{cls} ")]')
            match = re.search(r"(?:^|;)\s*width\s*:\s*([\d.]+)%", bars[0].get("style", "")) if bars else None
            strength[key] = float(match[1]) if match else None
            if strength[key] is not None and not 0 <= strength[key] <= 100:
                raise ValueError(f"Invalid source strength gauge at {page}: {locator(row)}")
        quest_type = cols[1].xpath('.//img/@alt')
        result.append({"quest_page": quests[0]["page"], "rank_label": text(cols[0]),
            "quest_type": quest_type[0] if quest_type else None,
            "location_page": location[0]["page"] if location else None,
            "intrusion": any(m["page"] == page and m["intrusion"] for m in monsters),
            "monsters": monsters, "xpath": locator(row), **strength})
    return result


def parse_monster(document, page, tables):
    basic = {text(cells(r)[0]): text(cells(r)[1]) for r in rows(tables[0]) if len(cells(r)) == 2}
    result = {"metadata": basic, "rewards": [], "hitzones": [], "quest_appearances": [], "issues": []}
    for table in tables:
        rr = rows(table)
        header = [text(c) for c in cells(rr[0])]
        if {"強さ", "任务名", "怪物"} <= set(header):
            result["quest_appearances"].extend(monster_quest_rows(table, page))
        if header == ["方法", "下位", "上位", "G级"]:
            expanded = grid(table)
            for cols in expanded[1:]:
                if len(cols) != 4 or len({id(c) for c in cols[1:]}) != 3:
                    continue  # a colspan condition note, retained in table evidence
                method = text(cols[0])
                attempts = re.search(r"(\d+)回", method)
                for rank, cell in zip(("LR", "HR", "G"), cols[1:]):
                    found, issues = rewards(cell, page, group=method, rank=rank,
                                           attempts=int(attempts[1]) if attempts else None)
                    result["rewards"].extend(found)
                    result["issues"].extend(issues)
        if header == ["肉质"]:
            headings = [text(c) for c in cells(rr[1])]
            for row in rr[2:]:
                cols = cells(row)
                if len(cols) == len(headings):
                    result["hitzones"].append({"part": text(cols[0]),
                        "values": dict(zip(headings[1:], ("\n".join(s["text"] for s in segments(c)) for c in cols[1:]))),
                        "xpath": locator(row)})
                else:
                    result["issues"].append({"kind": "unparsed_hitzone", "xpath": locator(row), "raw_text": text(row)})
    return result


def parse_quest(document, page, tables):
    metadata, refs, found, issues = {}, [], [], []
    for table in tables:
        for row in rows(table):
            cols = cells(row)
            if len(cols) % 2:
                continue
            for key, value in zip(cols[::2], cols[1::2]):
                label = text(key)
                if key.tag != "th":
                    continue
                if "任务报酬" in label and "[" in label:
                    reward_rows, reward_issues = rewards(value, page, group=label, rank=None, attempts=None)
                    found.extend(reward_rows)
                    issues.extend(reward_issues)
                else:
                    metadata[label] = text(value)
                    refs.extend({"role": label, **a} for a in links(value, page))
    metadata["breadcrumb"] = [text(x) for x in document.xpath('//*[@id="bread"]/li')]
    metadata["flags"] = [text(r) for r in rows(tables[0])[1:]]
    metadata["time_minutes"] = measured(metadata.get("制限时間", ""), "分")
    for key, target in (("报酬金", "reward_zenny"), ("副任务报酬", "sub_reward_zenny"), ("契约金", "fee_zenny")):
        metadata[target] = measured(metadata.get(key, ""), "z")
    return {"metadata": metadata, "references": refs, "rewards": found, "issues": issues}


def armor_icon(cell):
    for src in cell.xpath(".//img/@src"):
        match = re.search(r"/armour/b([1-5])-", src)
        if match:
            return SLOTS[match[1]]
    return None


def ingredient_segments(cell):
    """Armor recipes sometimes omit BRs between separate ingredients."""
    output = []
    for segment in segments(cell, block_breaks=True):
        raw = segment["text"]
        ends = [m.end() for m in re.finditer(r"[x×ｘ]\s*\d+", raw)]
        if len(ends) < 2:
            output.append(segment)
            continue
        located, start = [], 0
        for link in segment["links"]:
            position = raw.find(link["text"], start)
            if position < 0:
                raise ValueError(f"Cannot locate ingredient link in {raw}")
            located.append((position, link))
            start = position + len(link["text"])
        start = 0
        for end in ends + ([len(raw)] if ends[-1] != len(raw) else []):
            output.append({"text": raw[start:end].strip(),
                           "links": [link for position, link in located if start <= position < end]})
            start = end
    return output


def parse_armor(document, page, tables):
    pieces, skills, recipes, issues = [], [], [], []
    metadata = {}
    for table in tables:
        rr = rows(table)
        header = [text(c) for c in cells(rr[0])]
        if header == ["稀有度", "性別"]:
            metadata.update(zip(header, (text(c) for c in cells(rr[1]))))
        elif header == ["各防具生产費用"]:
            metadata["creation_zenny"] = measured(text(rr[1]), "z")
            metadata["creation_cost_raw"] = text(rr[1])
        elif "强化后" in header and "防具名" in header:
            for cols in grid(table)[1:]:
                if len(cols) != 9 or not armor_icon(cols[1]):
                    continue
                values = [integer(text(c)) for c in cols[2:]]
                if any(v is None for v in values):
                    raise ValueError(f"Unrecognized armor stats {page}: {[text(c) for c in cols]}")
                pieces.append({"ordinal": len(pieces), "name": text(cols[1]), "slot": armor_icon(cols[1]),
                    "hunter_type": "/".join(cols[0].xpath(".//img/@alt")) or text(cols[0]),
                    **dict(zip(("defense", "max_defense", "fire", "water", "thunder", "ice", "dragon"), values)),
                    "slots": None, "skills": [], "xpath": locator(cols[1].getparent())})
        elif header == ["防具名", "孔数", "技能"]:
            skills.extend(cells(r) for r in rr[1:] if len(cells(r)) == 3 and armor_icon(cells(r)[0]))
        elif len(header) >= 2 and header[1] == "必要素材" and header[0] in ("部位", "Lv"):
            for r in rr[1:]:
                cols = cells(r)
                if len(cols) < 2 or "合计" in text(cols[0]):
                    continue
                label = text(cols[0])
                kind = "Create" if header[0] == "部位" else "Improve"
                level = integer(label) if kind == "Improve" else 1
                slot = SLOT_LABELS.get(label) if kind == "Create" else None
                if (kind == "Improve" and level is None) or (kind == "Create" and slot is None):
                    raise ValueError(f"Unrecognized armor recipe scope {page}: {label}")
                recipe = parse_recipe(ingredient_segments(cols[1]), page, level, kind, locator(cols[1]))
                recipe.update(slot=slot, also_seen_at=[])
                recipes.append(recipe)
    if len(pieces) != len(skills):
        raise ValueError(f"Armor performance/skill counts differ at {page}: {len(pieces)} vs {len(skills)}")
    for piece, cols in zip(pieces, skills):
        if normalized(piece["name"]) != normalized(text(cols[0])) or piece["slot"] != armor_icon(cols[0]):
            raise ValueError(f"Armor performance/skill rows disagree at {page}")
        slot_text = normalized(text(cols[1]))
        if re.fullmatch(r"[◯○〇●\-]+", slot_text):
            piece["slots"] = sum(slot_text.count(c) for c in "◯○〇●")
        else:
            issues.append({"kind": "unparsed_slots", "raw_text": slot_text, "xpath": locator(cols[1])})
        chunks = linked_chunks(cols[2])
        for chunk in chunks:
            ref = page_ref(chunk["href"], page)
            point = integer(normalized(chunk["tail"]))
            piece["skills"].append({"page": ref, "points": point, "label": chunk["label"],
                                    "raw_text": chunk["label"] + " " + chunk["tail"], "xpath": chunk["xpath"]})
            if ref is None or point is None:
                issues.append({"kind": "special_or_unparsed_skill", "xpath": chunk["xpath"],
                               "raw_text": chunk["label"] + " " + chunk["tail"]})
        if not chunks and text(cols[2]) not in ("", "-", "无"):
            issues.append({"kind": "unlinked_skill", "raw_text": text(cols[2]), "xpath": locator(cols[2])})
    return {"metadata": metadata, "pieces": pieces, "recipes": recipes, "issues": issues}


def parse_skill(document, page, tables):
    activations, issues = [], []
    for cols in grid(tables[0])[1:]:
        if len(cols) != 5:
            raise ValueError(f"Unrecognized skill activation at {page}")
        points = integer(text(cols[3]))
        if points is None:
            issues.append({"kind": "special_skill_threshold", "raw_text": text(cols[3]), "xpath": locator(cols[3])})
        activations.append({"name": text(cols[2]), "points": points,
                            "description": text(cols[4]), "xpath": locator(cols[2])})
    return {"metadata": {}, "activations": activations, "issues": issues}


def extract_domains(root, pages):
    domains = []
    parsers = {"任务": ("quest", parse_quest), "怪物": ("monster", parse_monster),
               "防具1": ("armor", parse_armor), "技能1": ("skill", parse_skill)}
    for entry in pages:
        if entry["category"] not in parsers:
            continue
        page = entry["path"]
        if entry["category"] != "怪物" and not page.startswith("ida/"):
            continue
        document = html.fromstring((root / page).read_bytes())
        restore_values(document)
        tables = document.xpath("//table[not(ancestor::table)]")
        if entry["category"] == "怪物" and len(cells(rows(tables[0])[0])) != 2:
            continue  # index pages, not monster entities
        kind, parser = parsers[entry["category"]]
        try:
            result = parser(document, page, tables)
        except (ValueError, IndexError) as error:
            raise ValueError(f"{page}: {error}") from error
        result.update(page=page, kind=kind, name=entry["title"],
                      tables=[snapshot(t, page) for t in tables],
                      notes=[{"text": text(el), "xpath": locator(el)} for el in document.xpath(
                          '//*[@id="main_1"]//*[contains(concat(" ",normalize-space(@class)," ")," box2 ") and not(ancestor::table)]')])
        domains.append(result)
    return domains

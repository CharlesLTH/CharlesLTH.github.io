"""Compact armor browsing data, ordered and checked against the original lists."""

import hashlib
import re
from collections import Counter
from pathlib import Path

from lxml import html

from .domains import linked_chunks
from .homepage import source_path
from .html_source import cells, text

HUNTER_TYPES = {"通用": "common", "剑士用": "blade", "神枪手用": "gunner"}


def compact_skill(skill):
    ref = skill.get("skill")
    return {"label": skill["label"], "points": skill["points"],
            "skill": {key: ref[key] for key in ("id", "name")} if ref else None}


def build_armor_catalog(site_root, entities, homepage, revision):
    site_root = Path(site_root)
    by_page = {e["source"]["page"]: e for e in entities}
    sets, categories, sources, seen = [], [], {}, set()
    for link in homepage["sections"]["防具"]["links"]:
        key = link.get("route", {}).get("group")
        if not key:
            continue
        category = homepage["categories"][key]
        categories.append(category)
        page = category["source_page"]
        raw = (site_root / page).read_bytes()
        sources[page] = hashlib.sha256(raw).hexdigest()
        document = html.fromstring(raw)
        count = 0
        for heading in document.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," panel-heading ")]'):
            anchors = [(a, by_page.get(source_path(page, a.get("href")))) for a in heading.xpath('.//a[@href]')]
            matches = [(a, e) for a, e in anchors if e and e["kind"] == "armor"]
            if not matches:
                continue
            anchor, entity = matches[0]
            if entity["id"] in seen:
                raise ValueError(f"Duplicate armor list entry: {entity['id']}")
            seen.add(entity["id"])
            count += 1
            data = entity["data"]
            variants = []
            for row in heading.getparent().xpath('.//tr'):
                cols = cells(row)
                if not cols or text(cols[0]) != "合计":
                    continue
                if len(cols) != 10:
                    raise ValueError(f"Unrecognized armor summary: {page}")
                hunter_type, = cols[1].xpath('.//img/@alt')
                pieces = [p for p in data["pieces"] if p["hunter_type"] == hunter_type]
                defense = re.fullmatch(r"(\d+)\s*/\s*(\d+)", text(cols[2]))
                piece_count = re.search(r"\[(\d+)\]", text(cols[1]))
                if not pieces or not defense or not piece_count or int(piece_count[1]) != len(pieces):
                    raise ValueError(f"Armor summary/pieces disagree: {entity['id']}")
                skills = []
                for chunk in linked_chunks(cols[8]):
                    target = by_page[source_path(page, chunk["href"])]
                    skills.append({"label": chunk["label"], "points": int(chunk["tail"].strip()),
                                   "skill": {k: target[k] for k in ("id", "name")}})
                summary = {"defense": int(defense[1]), "max_defense": int(defense[2]),
                           "slots": int(text(cols[9])), "skills": skills}
                # These are the original list's raw sums, not activated skills
                # or a calculation of Torso Up's effects on chest equipment.
                expected_skills = Counter()
                for piece in pieces:
                    for skill in piece["skills"]:
                        expected_skills[skill["skill"]["id"]] += skill["points"]
                if any(summary[k] != sum(p[k] for p in pieces) for k in ("defense", "max_defense", "slots")) or dict(expected_skills) != {s["skill"]["id"]: s["points"] for s in skills}:
                    raise ValueError(f"Armor list/detail performance disagrees: {entity['id']}")
                variants.append({"type": HUNTER_TYPES[hunter_type], "summary": summary, "pieces": [
                    {**{k: p[k] for k in ("ordinal", "name", "slot", "defense", "max_defense", "slots")},
                     "skills": [compact_skill(s) for s in p["skills"]]} for p in pieces]})
            if sum(len(v["pieces"]) for v in variants) != len(data["pieces"]):
                raise ValueError(f"Incomplete armor variants: {entity['id']}")
            sets.append({"id": entity["id"], "name": text(anchor),
                         "aliases": sorted(set([entity["name"], *entity["aliases"]])),
                         "group": key, "rarity": data["metadata"]["稀有度"],
                         "gender": data["metadata"]["性別"], "variants": variants})
        if count != category["count"]:
            raise ValueError(f"Incomplete armor category: {key}")
    if seen != {e["id"] for e in entities if e["kind"] == "armor"}:
        raise ValueError("Armor catalog does not cover every set")
    return {"dataset_revision": revision, "sets": sets, "categories": categories, "source_pages": sources}

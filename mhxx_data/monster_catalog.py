"""Site-owned monster directory classifications, separate from raw game metadata."""

import hashlib
from pathlib import Path

from lxml import html

from .homepage import source_path

FAMILIES = {
    "鸟龙种": "bird-wyvern", "牙兽种": "fanged-beast", "两生种": "amphibian",
    "甲壳种": "carapaceon", "甲虫种": "neopteron", "兽龙种": "brute-wyvern",
    "鱼龙种": "piscine-wyvern", "牙龙种": "fanged-wyvern", "海龙种": "leviathan",
    "飞龙种": "flying-wyvern", "蛇龙种": "snake-wyvern", "铗角种": "temnoceran",
    "古龙种": "elder-dragon", "草食种": "herbivore", "兽人种": "lynian",
}
ALIASES = {"魚龙种": "鱼龙种", "鋏角种": "铗角种", "草食龙": "草食种"}


def build_monster_catalog(site_root, entities, entries, homepage, revision):
    root = Path(site_root)
    monsters = {e["id"]: e for e in entities if e["kind"] == "monster"}
    by_page = {e["source"]["page"]: e for e in monsters.values()}
    section = homepage["sections"]["怪物"]
    home_groups = {group["label"]: group for group in section["groups"]}
    home_members = {}
    for label, group in home_groups.items():
        group["route"] = {"kind": "monster", "group": "monster-2501", "family": FAMILIES[label]}
        for position, link in enumerate(group["links"]):
            key = link["route"]["id"]
            if key in home_members:
                raise ValueError(f"Duplicate homepage monster: {key}")
            home_members[key] = (label, position, link.get("marker", ""))

    sources = {"index/index.html": homepage["source_pages"]["index/index.html"]}
    records, seen = [], set()
    for size, page in (("large", "data/2501.html"), ("small", "data/2502.html")):
        raw = (root / page).read_bytes()
        sources[page] = hashlib.sha256(raw).hexdigest()
        ordered = {}
        for link in html.fromstring(raw).xpath('//table//a[@href]'):
            entity = by_page.get(source_path(page, link.get("href")))
            if entity:
                ordered.setdefault(entity["id"], entity)
        for position, (key, entity) in enumerate(ordered.items()):
            if key in seen:
                raise ValueError(f"Monster appears in both size directories: {key}")
            seen.add(key)
            raw_kind = entity["data"]["metadata"].get("种类", "")
            label, rank, marker = home_members.get(key, (ALIASES.get(raw_kind, raw_kind), 1000 + position, ""))
            if label not in FAMILIES:
                raise ValueError(f"Unclassified monster: {key}: {raw_kind}")
            detail_page = entity["source"]["page"]
            sources[detail_page] = hashlib.sha256((root / detail_page).read_bytes()).hexdigest()
            records.append({"id": key, "name": entity["name"], "family": FAMILIES[label],
                            "family_label": label, "size": size, "marker": marker,
                            "source_kind": raw_kind, "source_page": detail_page,
                            "classification_source": "index/index.html" if key in home_members else detail_page,
                            "position": rank})
            # The homepage omits Alatreon; retain its existing order and append
            # any omitted large monster to its directory family, never drop it.
            if size == "large" and key not in home_members:
                link = {"kind": "monster", "label": entity["name"], "route": {"id": key}, "source_page": detail_page}
                home_groups[label]["links"].append(link)
                section["links"].append(link)
    if seen != set(monsters):
        raise ValueError(f"Monster directory coverage differs: {seen ^ set(monsters)}")

    labels = list(home_groups) + [label for label in FAMILIES if label not in home_groups]
    records.sort(key=lambda r: (labels.index(r["family_label"]), r["size"] != "large", r["position"]))
    index = {e["id"]: e for e in entries}
    for order, record in enumerate(records):
        record["order"] = order
        del record["position"]
        index[record["id"]].update(monster_family=record["family"], monster_size=record["size"],
            monster_order=order, monster_marker=record["marker"],
            subtitle=record["family_label"] + (" · 大型" if record["size"] == "large" else " · 小型"))
    families = [{"key": FAMILIES[label], "label": label,
                 "counts": {size: sum(r["family_label"] == label and r["size"] == size for r in records)
                            for size in ("large", "small")}} for label in labels]
    return {"dataset_revision": revision, "families": families, "monsters": records, "source_pages": sources}

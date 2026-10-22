"""Small per-type weapon catalogs with level-specific, source-backed trees."""

import hashlib
import re
from pathlib import Path

from lxml import html

from .html_source import WEAPON_TYPES, page_ref


def build_weapon_catalogs(site_root, entities, revision):
    by_type = {kind: [] for kind in WEAPON_TYPES}
    for entity in entities:
        if entity["kind"] == "weapon":
            by_type[entity["data"]["weapon_type"]].append(entity)
    result = {}
    for type_index, (kind, weapons) in enumerate(by_type.items()):
        by_page = {e["source"]["page"]: e["id"] for e in weapons}
        source_pages, order, source_finals = {}, {}, set()
        for number in (1900 + type_index, 2882 + type_index, 2700 + type_index):
            page = f"data/{number}.html"
            source = Path(site_root) / page
            if not source.exists():
                continue  # Bowguns have one combined original tree page.
            raw = source.read_bytes()
            source_pages[page] = hashlib.sha256(raw).hexdigest()
            document = html.fromstring(raw)
            for anchor in document.xpath('//table[starts-with(@id,"sorter")]//tr/td[1]//a[@href]'):
                entity_id = by_page.get(page_ref(anchor.get("href"), page))
                if entity_id:
                    order.setdefault(entity_id, len(order))
                    if number == 2700 + type_index:
                        source_finals.add(entity_id)
        if source_finals != {e["id"] for e in weapons}:
            raise ValueError(f"Final weapon catalog coverage differs from the original: {kind}")
        nodes = {}
        for entity in weapons:
            levels = entity["data"]["levels"]
            if [l["level"] for l in levels] != list(range(1, len(levels) + 1)):
                raise ValueError(f"Non-contiguous source weapon levels: {entity['id']}")
            for level in levels:
                key = f"{entity['id']}@{level['level']}"
                extra = level["performance"][3] if kind == "Bow" else ""
                if kind in ("Light Bowgun", "Heavy Bowgun"):
                    extra = level["performance"][1].split("装填速度：", 1)[-1].split("孔槽：", 1)[0].strip()
                    extra = "装填速度：" + extra
                nodes[key] = {k: level[k] for k in ("level", "attack", "affinity", "defense", "elements", "slots", "sharpness_px")}
                nodes[key].update(key=key, id=entity["id"], name=re.sub(r"\s*\[XX\]", "", level["name"]).strip(),
                    xx="[XX]" in level["name"], final=level["level"] == levels[-1]["level"],
                    can_create=any(r["kind"] == "Create" for r in level["recipes"]),
                    parent=f"{entity['id']}@{level['level'] - 1}" if level["level"] > 1 else None,
                    children=[], special=extra)
            for first, second in zip(levels, levels[1:]):
                nodes[f"{entity['id']}@{first['level']}"]["children"].append(f"{entity['id']}@{second['level']}")
        for entity in weapons:
            for branch in entity["data"]["branches"]:
                parent = f"{entity['id']}@{branch['level']}"
                target = f"{branch['target']['id']}@{branch['target_level']}"
                if target not in nodes or nodes[target]["parent"] is not None:
                    raise ValueError(f"Ambiguous or cross-type weapon branch: {parent} -> {target}")
                nodes[parent]["children"].append(target)
                nodes[target]["parent"] = parent
        roots = sorted((n["key"] for n in nodes.values() if n["parent"] is None),
                       key=lambda key: (order.get(nodes[key]["id"], len(order)), key))
        ordered, visited = [], set()

        def walk(key, root):
            if key in visited:
                raise ValueError(f"Cycle or duplicate weapon node: {key}")
            visited.add(key)
            node = nodes[key]
            node["root"] = root
            node["branch"] = any(nodes[child]["id"] != node["id"] for child in node["children"])
            ordered.append(node)
            for child in node["children"]:
                walk(child, root)

        for root in roots:
            walk(root, root)
        if len(visited) != len(nodes):
            raise ValueError(f"Disconnected or cyclic weapon graph: {kind}")
        result[kind.lower().replace(" ", "-")] = {"dataset_revision": revision, "weapon_type": kind,
            "roots": roots, "nodes": ordered, "source_pages": source_pages}
    return result

"""Frontend records, sourced from local observations; MHGU stays a comparison.

Public entity keys use a typed site namespace, never SQLite row IDs or alleged
native game IDs. Large relationships are exported separately by static_api.
"""

import json
import re
from collections import defaultdict
from pathlib import PurePosixPath
from urllib.parse import urljoin

SITE_URL = "https://charleslth.github.io/games/mhxx/"
KINDS = {"weapon": "weapons", "item": "items", "monster": "monsters", "quest": "quests",
         "armor": "armor", "skill": "skills", "map": "maps", "combining": "combining"}


def decoded(row):
    return {k.removesuffix("_json") if k.endswith("_json") else k:
            json.loads(v) if k.endswith("_json") else v for k, v in dict(row).items()}


def select(row, *keys):
    return {k: row[k] for k in keys}


class PublicData:
    def __init__(self, connection):
        self.db = connection
        self.entities = {}
        self.by_page = {}
        self.relations = defaultdict(lambda: defaultdict(list))
        self.tables = {}
        self.groups = {}
        self.pages = {r["path"]: r for r in self.table("site_pages")}
        self.names = {r["_id"]: r["name"] for r in self.table("items")}

    def table(self, name):
        if name not in self.tables:
            order = {"mhxx_recipe_costs": "recipe_id", "annotated_recipe_items": "recipe_id,ordinal"}.get(name, "rowid")
            self.tables[name] = [decoded(r) for r in self.db.execute(f"SELECT * FROM {name} ORDER BY {order}")]
        return self.tables[name]

    def group(self, table, key):
        if (table, key) not in self.groups:
            groups = defaultdict(list)
            for row in self.table(table):
                groups[row[key]].append(row)
            self.groups[table, key] = groups
        return self.groups[table, key]

    def register(self, kind, key, name, page, aliases=()):
        if not re.fullmatch(r"\d+", key):
            raise ValueError(f"Invalid public entity key: {kind}/{key}")
        public_id = f"{kind}:site-{key}"
        if public_id in self.entities:
            raise ValueError(f"Duplicate public identity: {public_id}")
        ref = {"id": public_id, "kind": kind, "name": name, "href": f"{KINDS[kind]}/{key}.json"}
        entity = {**ref, "source": {"page": page, "sha256": self.pages[page]["sha256"], "url": SITE_URL + page},
                  "data": {}, "relations": {}, "comparison": None,
                  "aliases": sorted(set(aliases) - {name})}
        self.entities[public_id] = entity
        if kind != "combining":
            self.by_page[page] = ref
        return entity

    def ref(self, page):
        if page is None:
            return None
        if page not in self.by_page:
            raise ValueError(f"Unexported entity reference: {page}")
        return self.by_page[page]

    def add(self, page, relation, value):
        if page is not None:
            self.relations[self.ref(page)["id"]][relation].append(value)

    def entity(self, page):
        return self.entities[self.ref(page)["id"]]

    def comparison(self, row, id_field):
        return {"source": "mhgu", "status": row["status"], "candidate_id": row[id_field],
                "candidate_id_kind": {"family": "weapon_family", "combining_id": "combining_recipe"}.get(id_field, row.get("kind")),
                "evidence": row.get("evidence"),
                "notice": "Candidate correspondence only; local values are kept for display without correcting source disagreements."}

    def build(self):
        levels = self.group("site_weapon_levels", "page")
        for r in self.table("site_weapon_lines"):
            names = [l["name"] for l in levels[r["page"]]]
            self.register("weapon", PurePosixPath(r["page"]).stem, names[0], r["page"], names)
        for r in self.table("site_items"):
            self.register("item", PurePosixPath(r["page"]).stem, r["name"], r["page"])
        # Avoid copying large auxiliary table snapshots into the frontend.
        self.tables["site_domain_pages"] = [decoded(r) for r in self.db.execute(
            "SELECT page,kind,name,metadata_json,notes_json,issues_json FROM site_domain_pages ORDER BY page")]
        for r in self.table("site_domain_pages"):
            self.register(r["kind"], PurePosixPath(r["page"]).stem, r["name"], r["page"])
        for r in self.table("site_maps"):
            self.register("map", PurePosixPath(r["page"]).stem, r["name"], r["page"])
        self.combination_refs = {}
        for r in self.table("site_combining"):
            if not r["row_anchor"] or not re.fullmatch(r"id\d+", r["row_anchor"]):
                raise ValueError("Combining rows require stable source anchors")
            entity = self.register("combining", r["row_anchor"][2:], r["result_label"], r["page"])
            self.combination_refs[r["id"]] = select(entity, "id", "kind", "name", "href")
        self.weapons()
        self.items()
        self.domains()
        self.maps()
        self.combining()
        return self

    def weapons(self):
        matches = {r["page"]: r for r in self.table("weapon_matches")}
        costs = {r["recipe_id"]: r for r in self.table("mhxx_recipe_costs")}
        recipes_by_page = self.group("site_recipes", "page")
        for line in self.table("site_weapon_lines"):
            page = line["page"]
            entity = self.entity(page)
            entity["comparison"] = self.comparison(matches[page], "family")
            entity["data"] = {"weapon_type": line["wtype"], "ancestors_raw": line["ancestors"],
                              "issues": line["issues"], "levels": []}
            entity["data"]["branches"] = [{"level": b["level"], "target": self.ref(b["target_page"]),
                **select(b, "target_level", "label", "source_xpath")}
                for b in self.group("site_weapon_branches", "page")[page]]
            entity["data"]["parents"] = [{"weapon": self.ref(b["page"]),
                **select(b, "level", "target_level", "label", "source_xpath")}
                for b in self.group("site_weapon_branches", "target_page")[page]]
            recipes = defaultdict(list)
            for r in recipes_by_page[page]:
                ingredients = []
                for i in self.group("annotated_recipe_items", "recipe_id")[r["id"]]:
                    ingredient = {"item": self.ref(i["item_page"]), **select(i, "quantity", "reference_origin", "review_id", "label")}
                    ingredients.append(ingredient)
                    self.add(i["item_page"], "weapon_uses", {"weapon": self.ref(page), "level": r["level"], "kind": r["kind"],
                        **select(ingredient, "quantity", "reference_origin", "review_id")})
                cost = costs[r["id"]]
                recipes[r["level"]].append({**select(r, "kind", "money", "unparsed", "source_xpath", "raw_text"),
                    "ingredients": ingredients,
                    "material_points": [select(p, "label", "points", "raw_text") for p in self.group("site_recipe_points", "recipe_id")[r["id"]]],
                    "cost_comparison": select(cost, "display_zenny", "mhgu_stored_zenny", "difference_pattern", "review_status"),
                    "differences": [select(d, "field", "site_value", "upstream_value") for d in self.group("audit_differences", "recipe_id")[r["id"]]]})
            diffs = self.group("weapon_value_differences", "page")[page]
            for r in self.group("site_weapon_levels", "page")[page]:
                entity["data"]["levels"].append({**{k: v for k, v in r.items() if k != "page"},
                    "recipes": recipes[r["level"]], "performance_differences": [select(d, "field", "site_value", "upstream_value", "review_id")
                        for d in diffs if d["level"] == r["level"]]})

    def items(self):
        matches = {r["page"]: r for r in self.table("item_matches")}
        for r in self.table("site_items"):
            e = self.entity(r["page"])
            e["data"] = {"basic_rows": r["basic_rows"]}
            m = matches.get(r["page"])
            if m:
                e["comparison"] = {"source": "mhgu", "status": m["status"], "candidate_id": m["item_id"],
                    "candidate_id_kind": "item",
                    "candidate_name": self.names.get(m["item_id"]), "supporting_weapon_lines": m["supporting_weapon_lines"]}
            # Empty collections are explicit, so callers need no special cases.
            for name in ("rewards", "gathering", "combining_outputs", "combining_inputs", "weapon_uses", "armor_uses"):
                self.relations[e["id"]][name]

    def domains(self):
        matches = self.group("domain_matches", "page")
        differences = self.group("domain_value_differences", "page")
        domain_pages = {d["page"]: d for d in self.table("site_domain_pages")}
        appearance_pairs = set()
        for appearance in self.table("site_monster_quests"):
            page, quest_page = appearance["page"], appearance["quest_page"]
            metadata = domain_pages[quest_page]["metadata"]
            label = appearance["rank_label"]
            self.add(page, "quests", {"quest": self.ref(quest_page),
                "role": "乱入" if appearance["intrusion"] else "怪物",
                "label": self.ref(page)["name"], "rank_label": label,
                "rank": "G" if "G" in label else "HR" if "上" in label else "LR" if "下" in label else None,
                "quest_type": appearance["quest_type"], "objective": metadata.get("主任务"),
                "location": self.ref(appearance["location_page"]),
                "intrusion": bool(appearance["intrusion"]),
                "monsters": [{"monster": self.ref(m["page"]), **select(m, "label", "count", "intrusion", "source_icon")}
                             for m in appearance["monsters"]],
                "strength": {"health": appearance["health_bar"], "defense": appearance["defense_bar"],
                             "scale": "source_relative_gauge_not_hp_or_defense_rate"},
                "source_page": page, "source_xpath": appearance["source_xpath"]})
            appearance_pairs.add((page, quest_page))
        for d in self.table("site_domain_pages"):
            page, kind = d["page"], d["kind"]
            e = self.entity(page)
            e["data"] = select(d, "metadata", "notes", "issues")
            if kind in ("monster", "quest"):
                e["comparison"] = self.comparison(matches[page][0], "upstream_id")
                self.relations[e["id"]]["rewards"]
            if kind == "monster":
                e["data"]["hitzones"] = [select(h, "body_part", "values", "source_xpath") for h in self.group("site_monster_hitzones", "page")[page]]
                self.relations[e["id"]]["quests"]
            if kind == "quest":
                e["data"]["objective"] = d["metadata"].get("主任务")
                e["data"]["sub_objective"] = d["metadata"].get("副任务")
                e["data"]["quest_type"] = d["metadata"].get("种类")
                e["data"]["destination_text"] = d["metadata"].get("目的地")
                for key in ("time_minutes", "reward_zenny", "sub_reward_zenny", "fee_zenny", "flags"):
                    e["data"][key] = d["metadata"].get(key)
                e["data"]["references"] = []
                for r in self.group("site_quest_references", "page")[page]:
                    target = self.by_page.get(r["target_page"])
                    e["data"]["references"].append({**select(r, "role", "label"), "target": target,
                        "source_url": SITE_URL + r["target_page"], "source_xpath": r["source_xpath"]})
                    if target and target["kind"] == "monster":
                        pair = (r["target_page"], page)
                        if pair not in appearance_pairs:
                            # Preserve references absent from the original appearance
                            # table, while never guessing missing strength gauges.
                            monster_refs = [ref for ref in self.group("site_quest_references", "page")[page]
                                            if self.by_page.get(ref["target_page"], {}).get("kind") == "monster"]
                            self.add(r["target_page"], "quests", {"quest": self.ref(page), **select(r, "role", "label"),
                                "objective": d["metadata"].get("主任务"), "strength": None,
                                "monsters": [{"monster": self.ref(ref["target_page"]), "label": ref["label"],
                                              "intrusion": ref["role"] == "乱入", "count": None} for ref in monster_refs]})
                            appearance_pairs.add(pair)
            if kind == "skill":
                e["data"]["activations"] = [select(a, "name", "points", "description", "source_xpath") for a in self.group("site_skill_activations", "page")[page]]
                self.relations[e["id"]]["armor"]
            if kind == "armor":
                pieces = []
                for p in self.group("site_armor_pieces", "page")[page]:
                    piece = {k: v for k, v in p.items() if k not in ("id", "page")}
                    piece["skills"] = []
                    for s in self.group("site_armor_skills", "armor_id")[p["id"]]:
                        piece["skills"].append({"skill": self.ref(s["skill_page"]), **select(s, "points", "label", "raw_text")})
                        self.add(s["skill_page"], "armor", {"armor": self.ref(page), **select(p, "ordinal", "name", "slot"), "points": s["points"]})
                    m = next(m for m in matches[page] if m["ordinal"] == p["ordinal"])
                    piece["comparison"] = self.comparison(m, "upstream_id")
                    piece["differences"] = [select(v, "field", "site_value", "upstream_value") for v in differences[page] if v["ordinal"] == p["ordinal"]]
                    pieces.append(piece)
                e["aliases"] = sorted(set(e["aliases"]) | {p["name"] for p in pieces})
                e["data"]["pieces"] = pieces
                e["data"]["recipes"] = []
                for r in self.group("site_armor_recipes", "page")[page]:
                    ingredients = []
                    for i in self.group("site_armor_recipe_items", "recipe_id")[r["id"]]:
                        ingredients.append({"item": self.ref(i["item_page"]), **select(i, "quantity", "label", "raw_text")})
                        self.add(i["item_page"], "armor_uses", {"armor": self.ref(page), **select(r, "kind", "slot", "level"), "quantity": i["quantity"]})
                    e["data"]["recipes"].append({**select(r, "kind", "slot", "level", "raw_text", "unparsed", "source_xpath"),
                        "ingredients": ingredients, "material_points": [select(v, "label", "points", "raw_text")
                            for v in self.group("site_armor_recipe_points", "recipe_id")[r["id"]]]})
        for r in self.table("site_rewards"):
            value = {"item": self.ref(r["item_page"]), **select(r, "group_name", "rank", "condition_text", "attempts", "quantity", "percentage", "raw_text", "source_xpath", "segment")}
            self.add(r["page"], "rewards", value)
            self.add(r["item_page"], "rewards", {"source": self.ref(r["page"]), **{k: v for k, v in value.items() if k != "item"}})

    def maps(self):
        sections = [dict(r) for r in self.db.execute("SELECT id,page,ordinal,area,area_anchor,rank,empty_text FROM site_map_sections ORDER BY id")]
        sections_by_page = defaultdict(list)
        for s in sections:
            sections_by_page[s["page"]].append(s)
        locations = self.group("location_candidates", "page")
        checks = {r["gathering_id"]: r for r in self.table("gathering_checks")}
        for m in self.table("site_maps"):
            page = m["page"]
            e = self.entity(page)
            e["data"] = {**select(m, "notes", "issues"), "sections": [],
                         "images": [{"source_path": image, "url": urljoin(SITE_URL + page, image)} for image in m["images"]]}
            e["comparison"] = {"source": "mhgu", "destinations": [select(v, "location_id", "status", "supporting_quests") for v in locations[page]]}
            for s in sections_by_page[page]:
                name = f"nodes-{s['area'].replace('秘境', 'secret').lower()}-{s['rank'].lower()}"
                e["data"]["sections"].append({**select(s, "area", "area_anchor", "rank", "empty_text"), "relation": name})
                collection = self.relations[e["id"]][name]
                for n in self.group("site_gathering_nodes", "section_id")[s["id"]]:
                    node = {k: v for k, v in n.items() if k not in ("id", "section_id", "ordinal")}
                    node["icon_url"] = urljoin(SITE_URL + page, n["icon_path"])
                    node.update(select(s, "area", "rank"))
                    entries = self.group("site_gathering", "node_id")[n["id"]]
                    node["percentage_sum"] = sum(r["percentage"] for r in entries)
                    node["items"] = []
                    for r in entries:
                        value = {"item": self.ref(r["item_page"]), **select(r, "label", "quantity", "percentage", "row_anchor", "source_xpath"),
                                 "comparison_status": checks[r["id"]]["status"]}
                        node["items"].append(value)
                        self.add(r["item_page"], "gathering", {"map": self.ref(page), **select(s, "area", "rank"),
                            **select(n, "point", "fixed", "rare", "attempts_min", "attempts_max", "attempts_infinite"),
                            "percentage_sum": node["percentage_sum"], **{k: v for k, v in value.items() if k != "item"}})
                    collection.append(node)

    def combining(self):
        matches = {r["recipe_id"]: r for r in self.table("combining_matches")}
        for r in self.table("site_combining"):
            ref = self.combination_refs[r["id"]]
            e = self.entities[ref["id"]]
            e["data"] = {**select(r, "category", "result_label", "amount_min", "amount_max", "percentage", "row_anchor", "source_xpath", "raw_cells"),
                         "result": self.ref(r["result_item_page"]), "inputs": []}
            e["comparison"] = self.comparison(matches[r["id"]], "combining_id")
            self.add(r["result_item_page"], "combining_outputs", {"recipe": ref})
            for i in self.group("site_combining_inputs", "recipe_id")[r["id"]]:
                e["data"]["inputs"].append({"item": self.ref(i["item_page"]), **select(i, "slot", "label", "source_xpath")})
                self.add(i["item_page"], "combining_inputs", {"recipe": ref, "slot": i["slot"]})

    def search_records(self):
        return [{**select(e, "id", "kind", "name", "href", "aliases"),
                 "terms": sorted(set([e["name"], *e["aliases"]]))}
                for e in sorted(self.entities.values(), key=lambda e: e["id"])]

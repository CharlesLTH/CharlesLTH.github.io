"""Persistence and coverage reporting for local non-weapon domains."""

import json
from collections import Counter

from .domains import integer


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def populate_domains(connection, domains, matches):
    # Insert all pages first: armor rows reference skill pages later in the inventory.
    connection.executemany("INSERT INTO site_domain_pages VALUES (?,?,?,?,?,?,?)", (
        (d["page"], d["kind"], d["name"], encode(d["metadata"]), encode(d["notes"]),
         encode(d["tables"]), encode(d["issues"])) for d in domains))
    for d in domains:
        page = d["page"]
        connection.executemany("""INSERT INTO site_rewards
            (page,group_name,rank,condition_text,attempts,item_page,quantity,percentage,raw_text,source_xpath,segment)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (
            (page, r["group"], r["rank"], r["condition"], r["attempts"], r["item_page"], r["quantity"],
             r["percentage"], r["raw_text"], r["xpath"], r["segment"]) for r in d.get("rewards", [])))
        connection.executemany("INSERT INTO site_monster_hitzones VALUES (?,?,?,?,?)", (
            (page, n, h["part"], encode(h["values"]), h["xpath"]) for n, h in enumerate(d.get("hitzones", []))))
        connection.executemany("INSERT INTO site_monster_quests VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
            (page, n, r["quest_page"], r["rank_label"], r["quest_type"], r["location_page"],
             r["health_bar"], r["defense_bar"], int(r["intrusion"]), encode(r["monsters"]), r["xpath"])
            for n, r in enumerate(d.get("quest_appearances", []))))
        connection.executemany("INSERT INTO site_quest_references VALUES (?,?,?,?,?,?,?)", (
            (page, n, r["role"], r["page"], r["label"], r["href"], r["xpath"])
            for n, r in enumerate(d.get("references", []))))
        connection.executemany("INSERT INTO site_skill_activations VALUES (?,?,?,?,?,?)", (
            (page, n, a["name"], a["points"], a["description"], a["xpath"])
            for n, a in enumerate(d.get("activations", []))))
        for p in d.get("pieces", []):
            cursor = connection.execute("""INSERT INTO site_armor_pieces
                (page,ordinal,name,slot,hunter_type,rarity,gender_text,defense,max_defense,fire,water,thunder,ice,dragon,slots,source_xpath)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                page, p["ordinal"], p["name"], p["slot"], p["hunter_type"], integer(d["metadata"].get("稀有度", "")),
                d["metadata"].get("性別"), p["defense"], p["max_defense"], p["fire"], p["water"], p["thunder"],
                p["ice"], p["dragon"], p["slots"], p["xpath"]))
            connection.executemany("INSERT INTO site_armor_skills VALUES (?,?,?,?,?,?,?)", (
                (cursor.lastrowid, n, s["page"], s["points"], s["label"], s["raw_text"], s["xpath"])
                for n, s in enumerate(p["skills"])))
        for r in d.get("recipes", []):
            cursor = connection.execute("""INSERT INTO site_armor_recipes
                (page,kind,slot,level,raw_text,unparsed_json,source_xpath) VALUES (?,?,?,?,?,?,?)""", (
                page, r["kind"], r["slot"], r["level"], r["raw_text"], encode(r["unparsed"]), r["locator"]))
            rid = cursor.lastrowid
            connection.executemany("INSERT INTO site_armor_recipe_items VALUES (?,?,?,?,?,?)", (
                (rid, n, i["item_page"], i["quantity"], i["label"], i["raw_text"])
                for n, i in enumerate(r["ingredients"])))
            connection.executemany("INSERT INTO site_armor_recipe_points VALUES (?,?,?,?,?)", (
                (rid, n, p["label"], p["points"], p["raw_text"]) for n, p in enumerate(r["material_points"])))
    for m in matches:
        connection.execute("INSERT INTO domain_matches VALUES (?,?,?,?,?,?)", (
            m["page"], m["ordinal"], m["kind"], m["upstream_id"], m["status"], encode(m["evidence"])))
        connection.executemany("INSERT INTO domain_value_differences VALUES (?,?,?,?,?)", (
            (m["page"], m["ordinal"], diff["field"], encode(diff["site"]), encode(diff["upstream"]))
            for diff in m.get("differences", [])))


def domain_report(domains, matches):
    return {
        "pages": dict(Counter(d["kind"] for d in domains)),
        "rewards": dict(Counter(d["kind"] for d in domains for _ in d.get("rewards", []))),
        "reward_rows_without_probability": sum(r["percentage"] is None for d in domains for r in d.get("rewards", [])),
        "reward_rows_without_item_link": sum(r["item_page"] is None for d in domains for r in d.get("rewards", [])),
        "monster_hitzones": sum(len(d.get("hitzones", [])) for d in domains),
        "monster_quest_appearances": sum(len(d.get("quest_appearances", [])) for d in domains),
        "quest_references": sum(len(d.get("references", [])) for d in domains),
        "armor_pieces": sum(len(d.get("pieces", [])) for d in domains),
        "armor_skills": sum(len(p["skills"]) for d in domains for p in d.get("pieces", [])),
        "armor_recipes": sum(len(d.get("recipes", [])) for d in domains),
        "armor_recipe_items": sum(len(r["ingredients"]) for d in domains for r in d.get("recipes", [])),
        "armor_recipe_points": sum(len(r["material_points"]) for d in domains for r in d.get("recipes", [])),
        "skill_activations": sum(len(d.get("activations", [])) for d in domains),
        "match_status": {kind: dict(Counter(m["status"] for m in matches if m["kind"] == kind))
                         for kind in ("monster", "quest", "armor")},
        "difference_fields": dict(Counter(diff["field"] for m in matches for diff in m.get("differences", []))),
        "issues": [{"page": d["page"], **i} for d in domains for i in d["issues"]],
        "unparsed_armor_recipes": [{"page": d["page"], "xpath": r["locator"], "fragments": r["unparsed"]}
                                   for d in domains for r in d.get("recipes", []) if r["unparsed"]],
        "limitations": [
            "Every targeted detail page is retained, including unmatched entities and missing source values.",
            "Hitzone conditional values retain line breaks and source notes; no unconditional numeric value is invented.",
            "Habitat, resistance, item effects and other supplementary tables are source observations, not fully normalized models.",
            "Reward candidates compare known-item projections, not complete drop tables; free hunt and Meowster Hunter are excluded, condition translations and reward slots are not compared.",
            "Armor candidates compare base defense, elemental resistances, slots, rarity, equipment slot and physical creation recipes.",
            "Armor max defense is compared separately; gender, hunter type, skills, upgrade materials, costs and material points are not equivalence-checked.",
            "Local skill links are structured; no MHGU skill identity mapping is inferred in this stage.",
        ],
    }

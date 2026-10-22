"""Read-only exploratory queries, with explicit sources and mapping status."""

import json
import sqlite3
from pathlib import Path

from .pipeline import DEFAULT_DATABASE


def connect(path=DEFAULT_DATABASE):
    connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def rows(connection, sql, params=()):
    return [dict(row) for row in connection.execute(sql, params)]


def search(connection, term):
    return rows(connection, """
        SELECT l.page,l.level,l.name,l.attack,m.family,m.status
        FROM site_weapon_levels l JOIN weapon_matches m ON m.page=l.page
        WHERE l.name LIKE ? ORDER BY l.page,l.level LIMIT 100
    """, ("%" + term + "%",))


def item_sources(connection, item_id, limit):
    queries = {
        "gathering": """SELECT g.*,l.name AS location_name,l.name_ja AS location_name_ja
            FROM gathering g JOIN locations l ON l._id=g.location_id WHERE g.item_id=?
            ORDER BY g._id""",
        "hunting_rewards": """SELECT r.*,m.name AS monster_name,m.name_ja AS monster_name_ja
            FROM hunting_rewards r JOIN monsters m ON m._id=r.monster_id WHERE r.item_id=?
            ORDER BY r._id""",
        "quest_rewards": """SELECT r.*,q.name AS quest_name,q.hub,q.stars,q.rank
            FROM quest_rewards r JOIN quests q ON q._id=r.quest_id WHERE r.item_id=? ORDER BY r._id""",
    }
    result = {}
    for table, sql in queries.items():
        total = connection.execute(f"SELECT count(*) FROM {table} WHERE item_id=?", (item_id,)).fetchone()[0]
        result[table] = {"total": total, "sample": rows(connection, sql + " LIMIT ?", (item_id, limit))}
    return result


def upstream_item(connection, item_id, limit, include_sources=True):
    item = connection.execute("SELECT _id,name,type,rarity FROM items WHERE _id=?", (item_id,)).fetchone()
    if item is None:
        raise ValueError(f"Unknown upstream item: {item_id}")
    result = dict(item)
    result["candidate_site_labels"] = rows(connection, """
        SELECT page,site_name,status FROM candidate_item_labels WHERE upstream_id=?
    """, (item_id,))
    if item["type"] == "Materials":
        total = connection.execute("SELECT count(*) FROM item_to_material WHERE material_item_id=?", (item_id,)).fetchone()[0]
        contributors = rows(connection, """SELECT m.item_id,i.name,m.amount AS points_per_item
            FROM item_to_material m JOIN items i ON i._id=m.item_id WHERE m.material_item_id=?
            ORDER BY m.item_id LIMIT ?""", (item_id, limit))
        for contributor in contributors:
            contributor["sources"] = item_sources(connection, contributor["item_id"], limit)
        result["unit"] = "material_points"
        result["contributors"] = {"total": total, "sample": contributors}
    elif include_sources:
        result["sources"] = item_sources(connection, item_id, limit)
    return result


def weapon(connection, page, level, limit=3):
    if not 1 <= limit <= 100:
        raise ValueError("Sample limit must be between 1 and 100")
    if page.isdigit():
        page = f"ida/{page}.html"
    row = connection.execute("SELECT * FROM site_weapon_levels WHERE page=? AND level=?", (page, level)).fetchone()
    if row is None:
        raise ValueError(f"Weapon level not found: {page} LV{level}")
    match = dict(connection.execute("SELECT * FROM weapon_matches WHERE page=?", (page,)).fetchone())
    result = {
        "notice": "Exploratory candidate mapping. site_sources are local MHXX HTML; mhgu sources are imported MHGU observations and not a verified MHXX replacement.",
        "site": dict(row) | {"url": "https://charleslth.github.io/games/mhxx/" + page},
        "match": {"family": match["family"], "status": match["status"]},
        "site_recipes": [], "upstream_recipes": [],
        "upstream_provenance": json.loads(connection.execute(
            "SELECT value_json FROM source_manifest WHERE key='upstream'").fetchone()[0]),
    }
    result["performance_differences"] = rows(connection, """
        SELECT field,site_value_json,upstream_value_json,review_id
        FROM weapon_value_differences WHERE page=? AND level=?
    """, (page, level))
    if json.loads(match["evidence_json"]).get("review"):
        result["match"]["review"] = json.loads(match["evidence_json"])["review"]
    for key in ("elements_json", "sharpness_px_json", "performance_json"):
        result["site"][key.removesuffix("_json")] = json.loads(result["site"].pop(key))
    for recipe in rows(connection, "SELECT * FROM site_recipes WHERE page=? AND level=? ORDER BY id", (page, level)):
        ingredients = rows(connection, """
            SELECT ri.item_page,si.name,ri.quantity,ri.reference_origin,ri.review_id,
                   m.item_id AS upstream_item_id,m.status AS match_status
            FROM annotated_recipe_items ri JOIN site_items si ON si.page=ri.item_page
            LEFT JOIN item_matches m ON m.page=ri.item_page WHERE ri.recipe_id=? ORDER BY ri.ordinal
        """, (recipe["id"],))
        for ingredient in ingredients:
            ingredient["site_sources"] = local_item_sources(connection, ingredient["item_page"], limit)
            if ingredient["upstream_item_id"] is not None:
                ingredient["mhgu"] = upstream_item(connection, ingredient["upstream_item_id"], limit)
        recipe["ingredients"] = ingredients
        recipe["material_points"] = rows(connection, "SELECT label,points FROM site_recipe_points WHERE recipe_id=?", (recipe["id"],))
        recipe["check"] = rows(connection, "SELECT status FROM recipe_checks WHERE recipe_id=?", (recipe["id"],))
        recipe["differences"] = rows(connection, "SELECT field,site_value_json,upstream_value_json FROM audit_differences WHERE recipe_id=?", (recipe["id"],))
        recipe["cost_review"] = rows(connection, "SELECT * FROM mhxx_recipe_costs WHERE recipe_id=?", (recipe["id"],))
        result["site_recipes"].append(recipe)
    if match["family"] is not None:
        weapon_id = match["family"] * 256 + level
        result["upstream_weapon"] = dict(connection.execute("""
            SELECT w.*,i.name FROM weapons w JOIN items i ON i._id=w._id WHERE w._id=?
        """, (weapon_id,)).fetchone())
        for part in rows(connection, "SELECT * FROM components WHERE created_item_id=? ORDER BY type,_id", (weapon_id,)):
            part["item"] = upstream_item(connection, part["component_item_id"], limit, include_sources=False)
            part["quantity_unit"] = "points" if part["item"]["type"] == "Materials" else "items"
            result["upstream_recipes"].append(part)
    return result


def page_path(value, kind):
    return f"{'data' if kind in ('monster', 'map') else 'ida'}/{value}.html" if value.isdigit() else value


def sample(connection, sql, params, limit):
    return {"total": connection.execute(f"SELECT count(*) FROM ({sql})", params).fetchone()[0],
            "sample": rows(connection, sql + " LIMIT ?", (*params, limit))}


def local_item_sources(connection, page, limit=3):
    if not 1 <= limit <= 100:
        raise ValueError("Sample limit must be between 1 and 100")
    result = {kind: sample(connection, """SELECT page,source_name,group_name,rank,condition_text,
                attempts,quantity,percentage,raw_text,source_xpath
            FROM site_item_reward_sources WHERE item_page=? AND source_kind=? ORDER BY page,id""",
            (page, kind), limit) for kind in ("monster", "quest")}
    result["gathering"] = sample(connection, """SELECT g.page,g.map_name,g.area,g.rank,g.point,g.fixed,g.rare,
            g.attempts_min,g.attempts_max,g.attempts_infinite,g.quantity,g.percentage,g.source_xpath,g.row_anchor,
            (SELECT sum(v.percentage) FROM site_gathering v WHERE v.node_id=g.node_id) AS group_percentage_sum
        FROM site_item_gathering_sources g WHERE g.item_page=? ORDER BY g.page,g.id""", (page,), limit)
    result["combining"] = combining_sample(connection, "c.result_item_page=?", (page,), limit)
    return result


def item(connection, page, limit=3):
    page = page_path(page, "item")
    row = connection.execute("SELECT * FROM site_items WHERE page=?", (page,)).fetchone()
    if row is None:
        raise ValueError(f"Site item not found: {page}")
    result = dict(row)
    result["basic_rows"] = json.loads(result.pop("basic_rows_json"))
    result["site_sources"] = local_item_sources(connection, page, limit)
    result["armor_recipes"] = sample(connection, """SELECT ar.page,d.name,ar.kind,ar.slot,ar.level,ri.quantity
        FROM site_armor_recipe_items ri JOIN site_armor_recipes ar ON ar.id=ri.recipe_id
        JOIN site_domain_pages d ON d.page=ar.page WHERE ri.item_page=? ORDER BY ar.page,ar.id""", (page,), limit)
    result["combining_uses"] = combining_sample(connection, """EXISTS (
        SELECT 1 FROM site_combining_inputs i WHERE i.recipe_id=c.id AND i.item_page=?)""", (page,), limit)
    match = connection.execute("SELECT item_id,status FROM item_matches WHERE page=?", (page,)).fetchone()
    result["match"] = dict(match) if match else None
    if match and match["item_id"] is not None:
        result["mhgu"] = upstream_item(connection, match["item_id"], limit)
    result["notice"] = "site_sources are local MHXX HTML observations; mhgu is the separately imported source. Unknown percentages remain null. Gathering probabilities are approximate source values; group totals are not normalized."
    return result


def domain(connection, kind, page, limit=3):
    if not 1 <= limit <= 100:
        raise ValueError("Sample limit must be between 1 and 100")
    page = page_path(page, kind)
    row = connection.execute("""SELECT page,kind,name,metadata_json,notes_json,issues_json
        FROM site_domain_pages WHERE page=? AND kind=?""", (page, kind)).fetchone()
    if row is None:
        raise ValueError(f"Site {kind} not found: {page}")
    result = dict(row)
    for key in ("metadata", "notes", "issues"):
        result[key] = json.loads(result.pop(key + "_json"))
    result["notice"] = "Local MHXX observations. MHGU identities are candidates with limited comparison scope; see evidence."
    result["matches"] = rows(connection, "SELECT * FROM domain_matches WHERE page=? ORDER BY ordinal", (page,))
    for m in result["matches"]:
        m["evidence"] = json.loads(m.pop("evidence_json"))
        if m["upstream_id"] is not None:
            table = {"monster": "monsters", "quest": "quests", "armor": "items"}[kind]
            m["upstream_name"] = connection.execute(f"SELECT name FROM {table} WHERE _id=?", (m["upstream_id"],)).fetchone()[0]
    result["differences"] = rows(connection, "SELECT * FROM domain_value_differences WHERE page=?", (page,))
    if kind in ("monster", "quest"):
        result["rewards"] = sample(connection, """SELECT r.*,i.name AS item_name
            FROM site_rewards r LEFT JOIN site_items i ON i.page=r.item_page
            WHERE r.page=? ORDER BY r.id""", (page,), limit)
    if kind == "monster":
        result["hitzones"] = rows(connection, "SELECT * FROM site_monster_hitzones WHERE page=? ORDER BY ordinal", (page,))
        for h in result["hitzones"]:
            h["values"] = json.loads(h.pop("values_json"))
        result["quests"] = sample(connection, """SELECT DISTINCT q.page,d.name,q.role,q.label
            FROM site_quest_references q JOIN site_domain_pages d ON d.page=q.page
            WHERE q.target_page=? ORDER BY q.page,q.role""", (page,), limit)
    elif kind == "quest":
        result["references"] = rows(connection, "SELECT * FROM site_quest_references WHERE page=? ORDER BY ordinal", (page,))
    elif kind == "armor":
        result["pieces"] = rows(connection, "SELECT * FROM site_armor_pieces WHERE page=? ORDER BY ordinal", (page,))
        for p in result["pieces"]:
            p["skills"] = rows(connection, "SELECT * FROM site_armor_skills WHERE armor_id=? ORDER BY ordinal", (p["id"],))
        result["recipes"] = rows(connection, "SELECT * FROM site_armor_recipes WHERE page=? ORDER BY id", (page,))
        for r in result["recipes"]:
            r["ingredients"] = rows(connection, "SELECT * FROM site_armor_recipe_items WHERE recipe_id=? ORDER BY ordinal", (r["id"],))
            r["material_points"] = rows(connection, "SELECT * FROM site_armor_recipe_points WHERE recipe_id=? ORDER BY ordinal", (r["id"],))
    elif kind == "skill":
        result["activations"] = rows(connection, "SELECT * FROM site_skill_activations WHERE page=? ORDER BY ordinal", (page,))
        result["armor"] = sample(connection, """SELECT p.page,p.name,p.slot,s.points FROM site_armor_skills s
            JOIN site_armor_pieces p ON p.id=s.armor_id WHERE s.skill_page=? ORDER BY p.page,p.ordinal""", (page,), limit)
    return result


def combining_sample(connection, where, params, limit):
    result = sample(connection, f"SELECT c.* FROM site_combining c WHERE {where} ORDER BY c.id", params, limit)
    for recipe in result["sample"]:
        recipe["raw_cells"] = json.loads(recipe.pop("raw_cells_json"))
        recipe["inputs"] = rows(connection, "SELECT * FROM site_combining_inputs WHERE recipe_id=? ORDER BY slot", (recipe["id"],))
        match = connection.execute("SELECT * FROM combining_matches WHERE recipe_id=?", (recipe["id"],)).fetchone()
        recipe["match"] = dict(match) if match else None
        if match:
            recipe["match"]["evidence"] = json.loads(recipe["match"].pop("evidence_json"))
    return result


def combining(connection, term="", limit=10):
    if not 1 <= limit <= 100:
        raise ValueError("Sample limit must be between 1 and 100")
    # Literal substring search; SQL wildcard characters in user text are not expanded.
    result = combining_sample(connection, """instr(c.result_label,?)>0 OR EXISTS (
        SELECT 1 FROM site_combining_inputs i WHERE i.recipe_id=c.id AND instr(i.label,?)>0)""", (term, term), limit)
    result["notice"] = "Local combining recipes. Unlinked results remain searchable labels; material input slots are separate from output quantity ranges."
    return result


def map_details(connection, page, area=None, rank=None, limit=5):
    if not 1 <= limit <= 100:
        raise ValueError("Sample limit must be between 1 and 100")
    if rank is not None and rank not in ("LR", "HR", "G"):
        raise ValueError("Rank must be LR, HR or G")
    page = page_path(page, "map")
    row = connection.execute("SELECT * FROM site_maps WHERE page=?", (page,)).fetchone()
    if row is None:
        raise ValueError(f"Site map not found: {page}")
    result = dict(row)
    for key in ("images", "notes", "issues"):
        result[key] = json.loads(result.pop(key + "_json"))
    result["notice"] = "Local approximate gathering probabilities, not normalized. Normal/rare point variants stay separate; unlimited attempts are explicit. Destination candidates do not assert identical day/night gathering tables."
    result["location_candidates"] = rows(connection, """SELECT c.*,l.name AS upstream_name FROM location_candidates c
        JOIN locations l ON l._id=c.location_id WHERE c.page=? ORDER BY c.location_id""", (page,))
    for candidate in result["location_candidates"]:
        candidate["evidence"] = json.loads(candidate.pop("evidence_json"))
        quest_rows = candidate["evidence"]["quests"]
        candidate["evidence"]["quests"] = {"total": len(quest_rows), "sample": quest_rows[:limit]}
    conditions, params = ["s.page=?"], [page]
    if area is not None:
        conditions.append("s.area=?")
        params.append(area)
    if rank is not None:
        conditions.append("s.rank=?")
        params.append(rank)
    where = " AND ".join(conditions)
    result["sections"] = rows(connection, f"""SELECT s.id,s.area,s.area_anchor,s.rank,s.empty_text,
        (SELECT count(*) FROM site_gathering_nodes n WHERE n.section_id=s.id) AS node_variants
        FROM site_map_sections s WHERE {where} ORDER BY s.ordinal""", params)
    result["nodes"] = sample(connection, f"""SELECT n.*,s.area,s.rank,s.area_anchor FROM site_gathering_nodes n
        JOIN site_map_sections s ON s.id=n.section_id WHERE {where} ORDER BY s.ordinal,n.ordinal""", tuple(params), limit)
    for node in result["nodes"]["sample"]:
        node["items"] = rows(connection, """SELECT g.*,c.status AS comparison_status FROM site_gathering g
            LEFT JOIN gathering_checks c ON c.gathering_id=g.id WHERE g.node_id=? ORDER BY g.ordinal""", (node["id"],))
        node["percentage_sum"] = sum(r["percentage"] for r in node["items"])
    return result

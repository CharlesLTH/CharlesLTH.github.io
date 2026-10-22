"""Persist acquisition observations and compare only independently known IDs."""

from collections import Counter, defaultdict

from .domain_database import encode


def populate_acquisition(connection, acquisition):
    for m in acquisition["maps"]:
        connection.execute("INSERT INTO site_maps VALUES (?,?,?,?,?)", (
            m["page"], m["name"], encode(m["images"]), encode(m["notes"]), encode(m["issues"])))
        for s in m["sections"]:
            cursor = connection.execute("""INSERT INTO site_map_sections
                (page,ordinal,area,area_anchor,rank,empty_text,source_xpath,table_json) VALUES (?,?,?,?,?,?,?,?)""", (
                m["page"], s["ordinal"], s["area"], s["area_anchor"], s["rank"], s["empty_text"],
                s["source"]["xpath"], encode(s["source"])))
            sid = cursor.lastrowid
            for n in s["nodes"]:
                cursor = connection.execute("""INSERT INTO site_gathering_nodes
                    (section_id,ordinal,point,point_label,icon_path,fixed,rare,attempts_min,attempts_max,
                     attempts_infinite,attempts_raw,source_xpath) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    sid, n["ordinal"], n["point"], n["point_label"], n["icon"], n["fixed"], n["rare"],
                    n["attempts_min"], n["attempts_max"], n["attempts_infinite"], n["attempts_raw"], n["xpath"]))
                nid = cursor.lastrowid
                connection.executemany("""INSERT INTO site_gathering
                    (node_id,ordinal,item_page,label,quantity,percentage,row_anchor,source_xpath,raw_text)
                    VALUES (?,?,?,?,?,?,?,?,?)""", (
                    (nid, i, r["item_page"], r["label"], r["quantity"], r["percentage"],
                     r["row_anchor"], r["xpath"], r["raw_text"]) for i, r in enumerate(n["items"])))
    catalog = acquisition["combining"]
    connection.execute("INSERT INTO site_combining_catalog VALUES (?,?,?)", (
        catalog["page"], encode(catalog["tables"]), encode(catalog["issues"])))
    for r in catalog["recipes"]:
        cursor = connection.execute("""INSERT INTO site_combining
            (page,ordinal,category,result_item_page,result_label,amount_min,amount_max,percentage,row_anchor,source_xpath,raw_cells_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (
            catalog["page"], r["ordinal"], r["category"], r["output"]["item_page"], r["output"]["label"],
            r["amount_min"], r["amount_max"], r["percentage"], r["row_anchor"], r["xpath"], encode(r["raw_cells"])))
        connection.executemany("INSERT INTO site_combining_inputs VALUES (?,?,?,?,?)", (
            (cursor.lastrowid, i + 1, ref["item_page"], ref["label"], ref["xpath"])
            for i, ref in enumerate(r["inputs"])))


def location_evidence(connection):
    grouped = defaultdict(dict)
    for r in connection.execute("""SELECT q.target_page AS page,q.page AS quest_page,q.label,m.upstream_id AS quest_id,u.location_id
            FROM site_quest_references q JOIN domain_matches m ON m.page=q.page AND m.kind='quest'
            JOIN quests u ON u._id=m.upstream_id JOIN site_maps sm ON sm.page=q.target_page
            WHERE q.role='目的地'"""):
        grouped[r["page"], r["location_id"]][r["quest_page"]] = dict(r)
    for (page, uid), quests in grouped.items():
        status = "quest_destination_supported" if len(quests) >= 2 else "single_quest_support"
        connection.execute("INSERT INTO location_candidates VALUES (?,?,?,?,?)", (
            page, uid, status, len(quests), encode({"quests": list(quests.values()),
                "scope": "candidate quest destinations only; map names, day/night gathering and game IDs not inferred"})))


def area_key(value):
    return {"BC": "Base Camp", "秘境": "Secret"}.get(value, "Area " + value)


def compare_gathering(connection):
    # A map page can cover multiple quest destinations (e.g. day/night).
    # Only targets backed by >=2 quests AND containing gathering rows are used.
    locations = defaultdict(set)
    for r in connection.execute("""SELECT lc.page,lc.location_id FROM location_candidates lc
            WHERE lc.status='quest_destination_supported'
            AND EXISTS (SELECT 1 FROM gathering g WHERE g.location_id=lc.location_id)"""):
        locations[r["page"]].add(r["location_id"])
    upstream = defaultdict(list)
    for r in connection.execute("SELECT * FROM gathering"):
        key = (r["location_id"], r["area"], r["rank"], r["group_num"], r["fixed"], r["rare"], r["item_id"])
        upstream[key].append(dict(r))
    for r in connection.execute("""SELECT g.*,m.item_id AS upstream_item_id FROM site_item_gathering_sources g
            LEFT JOIN item_matches m ON m.page=g.item_page ORDER BY g.id"""):
        candidate_locations = sorted(locations[r["page"]])
        nearby = []
        if len(candidate_locations) == 1 and r["upstream_item_id"] is not None:
            key = (candidate_locations[0], area_key(r["area"]), r["rank"], r["point"], r["fixed"], r["rare"], r["upstream_item_id"])
            nearby = upstream.get(key, [])
        exact = [u["_id"] for u in nearby if (u["quantity"], u["percentage"]) == (r["quantity"], r["percentage"])]
        if r["upstream_item_id"] is None:
            status = "item_identity_unresolved"
        elif len(candidate_locations) != 1:
            status = "location_identity_unresolved"
        elif len(exact) == 1:
            status = "row_values_equal_candidate"
        elif exact:
            status = "row_values_equal_ambiguous"
        elif nearby:
            status = "row_values_differ"
        else:
            status = "no_comparable_row"
        connection.execute("INSERT INTO gathering_checks VALUES (?,?,?)", (r["id"], status, encode({
            "location_candidates": candidate_locations, "item_id": r["upstream_item_id"], "exact_row_ids": exact,
            "nearby_rows": [{k: u[k] for k in ("_id", "site", "quantity", "percentage")} for u in nearby],
            "scope": "same candidate map/area/rank/point/fixed/rare/item; icon type, bait and attempt limits not compared"})))


def combining_candidates(recipe, inputs, source):
    """Require >=2 independently mapped roles and distinct IDs, then exact values.

Input slot order is immaterial; unknown roles constrain neither item identity
nor translations. No new item identity is inferred from this comparison.
"""
    known_inputs = Counter(i for i in inputs if i is not None)
    known = list(known_inputs.elements()) + ([recipe["upstream_result_id"]] if recipe["upstream_result_id"] is not None else [])
    if len(known) < 2 or len(set(known)) < 2:
        return [], "insufficient_item_evidence"
    candidates = []
    for u in source:
        if recipe["upstream_result_id"] is not None and recipe["upstream_result_id"] != u["created_item_id"]:
            continue
        if known_inputs - Counter((u["item_1_id"], u["item_2_id"])):
            continue
        if (recipe["amount_min"], recipe["amount_max"], recipe["percentage"]) != (u["amount_made_min"], u["amount_made_max"], u["percentage"]):
            continue
        candidates.append(u["_id"])
    status = "known_roles_unique" if len(candidates) == 1 else "known_roles_ambiguous" if candidates else "no_known_roles_match"
    return candidates, status


def compare_combining(connection):
    source = [dict(r) for r in connection.execute("SELECT * FROM combining")]
    matches = []
    for r in connection.execute("""SELECT c.*,m.item_id AS upstream_result_id FROM site_combining c
            LEFT JOIN item_matches m ON m.page=c.result_item_page ORDER BY c.id"""):
        inputs = [i[0] for i in connection.execute("""SELECT m.item_id FROM site_combining_inputs i
            LEFT JOIN item_matches m ON m.page=i.item_page WHERE i.recipe_id=? ORDER BY i.slot""", (r["id"],))]
        candidates, status = combining_candidates(r, inputs, source)
        matches.append({"id": r["id"], "candidates": candidates, "status": status,
                        "output": r["upstream_result_id"], "inputs": inputs})
    counts = Counter(m["candidates"][0] for m in matches if len(m["candidates"]) == 1)
    for m in matches:
        uid = m["candidates"][0] if len(m["candidates"]) == 1 else None
        if uid is not None and counts[uid] > 1:
            uid, m["status"] = None, "non_bijective_candidates"
        connection.execute("INSERT INTO combining_matches VALUES (?,?,?,?)", (m["id"], uid, m["status"], encode({
            "candidate_ids": m["candidates"], "known_result_id": m["output"], "known_input_ids": m["inputs"],
            "scope": "known item roles and output amount/success rate only; unknown roles and translated labels not inferred"})))


def acquisition_report(connection, acquisition):
    nodes = [(m, s, n) for m in acquisition["maps"] for s in m["sections"] for n in s["nodes"]]
    totals = [{"page": m["page"], "area": s["area"], "rank": s["rank"], "point": n["point"], "rare": n["rare"],
               "sum": sum(i["percentage"] for i in n["items"]), "xpath": n["xpath"]} for m, s, n in nodes]
    return {
        "map_pages": len(acquisition["maps"]), "map_sections": sum(len(m["sections"]) for m in acquisition["maps"]),
        "empty_sections": sum(s["empty_text"] is not None for m in acquisition["maps"] for s in m["sections"]),
        "gathering_nodes": len(nodes), "gathering_rows": sum(len(n["items"]) for _, _, n in nodes),
        "combining_recipes": len(acquisition["combining"]["recipes"]),
        "combining_categories": dict(Counter(r["category"] for r in acquisition["combining"]["recipes"])),
        "issues": [{"page": m["page"], **i} for m in acquisition["maps"] + [acquisition["combining"]] for i in m["issues"]],
        "gathering_probability_sums_not_100": [r for r in totals if r["sum"] != 100],
        "location_candidate_status": dict(connection.execute("SELECT status,count(*) FROM location_candidates GROUP BY status")),
        "gathering_checks": dict(connection.execute("SELECT status,count(*) FROM gathering_checks GROUP BY status")),
        "combining_match_status": dict(connection.execute("SELECT status,count(*) FROM combining_matches GROUP BY status")),
        "limitations": [
            "Local map pages describe probabilities as approximate; values and non-100 totals are preserved without normalization.",
            "Map candidates use previously inferred quest destinations; day/night destinations may share one site page.",
            "Gathering comparisons omit icon type, bait and attempt limits, so equal rows are limited numerical candidates only.",
            "Combining comparisons require at least two known item roles; unknown outputs remain unlinked and independently searchable.",
            "Shop, trade, combining failure byproducts and Palico equipment are outside this extraction stage.",
        ],
    }

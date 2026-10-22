"""Pinned, evidence-gated annotations. Neither source's values are overwritten."""

import json
from collections import Counter

from .matching import alternatives, independent_item, physical, upstream_profile


def profile_differences(weapon, upstream_levels):
    if weapon["wtype"] != upstream_levels[0]["wtype"] or len(weapon["levels"]) != len(upstream_levels):
        raise ValueError("Reviewed weapon type or level count differs")
    differences = []
    for local, upstream in zip(weapon["levels"], upstream_levels):
        remote = upstream_profile(upstream)
        for field in ("level", "attack", "slots", "affinity", "defense", "elements"):
            site_value = json.loads(json.dumps(local[field]))
            upstream_value = json.loads(json.dumps(remote[field]))
            if site_value != upstream_value:
                differences.append(dict(level=local["level"], field=field,
                                        site=site_value, upstream=upstream_value))
    return differences


def validate_registry(registry, pages, source_hash):
    if registry["schema_version"] != 1:
        raise ValueError("Unsupported review registry schema")
    if registry["upstream_database_sha256"] != source_hash:
        raise ValueError("Review registry targets a different upstream database")
    by_page = {p["path"]: p for p in pages}
    ids = set()
    for section in ("weapon_identities", "item_constraint_exclusions", "unlinked_ingredients"):
        for entry in registry[section]:
            if entry["id"] in ids:
                raise ValueError(f"Duplicate review ID: {entry['id']}")
            ids.add(entry["id"])
            for path, expected in entry["page_sha256"].items():
                if path not in by_page or by_page[path]["sha256"] != expected:
                    raise ValueError(f"Stale review {entry['id']}: source page changed: {path}")


def select_recipe(weapons, review):
    found = [r for w in weapons if w["page"] == review["page"] for r in w["recipes"]
             if r["level"] == review["level"] and r["kind"] == review["kind"]
             and r["locator"] == review["locator"]]
    if len(found) != 1:
        raise ValueError(f"Review recipe is not unique: {review['id']}")
    return found[0]


def validate_exclusions(weapons, registry, upstream_recipes, matches):
    for entry in registry["item_constraint_exclusions"]:
        recipe = select_recipe(weapons, entry)
        if matches[entry["page"]]["family"] * 256 + entry["level"] != entry["upstream_weapon_id"]:
            raise ValueError(f"Excluded constraint points to a different weapon: {entry['id']}")
        if not any(i["item_page"] == entry["item_page"] and i["quantity"] == entry["quantity"]
                   for i in recipe["ingredients"]):
            raise ValueError(f"Excluded ingredient changed: {entry['id']}")
        parts = upstream_recipes[entry["upstream_weapon_id"]][entry["kind"]]
        if not any(p["component_item_id"] == entry["upstream_conflicting_item_id"]
                   and p["quantity"] == entry["quantity"] for p in parts):
            raise ValueError(f"Upstream conflict changed: {entry['id']}")


def apply_unlinked_ingredients(weapons, registry, baseline_items, matches, upstream_recipes):
    for entry in registry["unlinked_ingredients"]:
        recipe = select_recipe(weapons, entry)
        if entry["raw_text"] not in recipe["unparsed"]:
            raise ValueError(f"Unlinked fragment changed: {entry['id']}")
        item_id = independent_item(baseline_items.get(entry["item_page"]), entry["page"])
        if item_id != entry["upstream_item_id"]:
            raise ValueError(f"Unlinked item lacks independent identity evidence: {entry['id']}")
        family = matches[entry["page"]]["family"]
        parts = alternatives(upstream_recipes, family * 256 + entry["level"], entry["kind"])
        mapped = [(independent_item(baseline_items.get(i["item_page"]), entry["page"]), i["quantity"])
                  for i in recipe["ingredients"]] + [(item_id, entry["quantity"])]
        if any(i is None for i, _ in mapped) or not any(
                Counter(mapped) == Counter((p["component_item_id"], p["quantity"]) for p in physical(ps))
                for _, ps in parts):
            raise ValueError(f"Annotated recipe not independently corroborated: {entry['id']}")
        recipe.setdefault("reviewed_ingredients", []).append({
            "item_page": entry["item_page"], "quantity": entry["quantity"],
            "label": entry["raw_text"], "raw_text": entry["raw_text"], "review_id": entry["id"],
        })


def independent_recipe_checks(weapon, family, baseline_items, upstream_recipes):
    # Intentionally use only the original linked ingredients and baseline item
    # mappings. Reviewed identities/annotations cannot bootstrap one another.
    checks = []
    for recipe in weapon["recipes"]:
        if recipe["unparsed"] or not recipe["ingredients"]:
            continue
        mapped = [(independent_item(baseline_items.get(i["item_page"]), weapon["page"]), i["quantity"])
                  for i in recipe["ingredients"]]
        if any(i is None for i, _ in mapped):
            continue
        equal = any(Counter(mapped) == Counter((p["component_item_id"], p["quantity"]) for p in physical(ps))
                    for _, ps in alternatives(upstream_recipes, family * 256 + recipe["level"], recipe["kind"]))
        checks.append({"level": recipe["level"], "kind": recipe["kind"], "equal": equal,
                       "locator": recipe["locator"], "ingredients": mapped})
    return checks


def apply_weapon_reviews(weapons, registry, matches, families, baseline_items, upstream_recipes):
    by_page = {w["page"]: w for w in weapons}
    occupied = {m["family"] for m in matches.values() if m["family"] is not None}
    value_differences = []
    for entry in registry["weapon_identities"]:
        weapon = by_page[entry["page"]]
        family = entry["family"]
        match = matches[entry["page"]]
        if match["family"] is not None or family in occupied:
            raise ValueError(f"Review would overwrite an existing mapping: {entry['id']}")
        differences = profile_differences(weapon, families[family])
        if differences != entry["expected_profile_differences"]:
            raise ValueError(f"Reviewed performance differences changed: {entry['id']}")
        checks = independent_recipe_checks(weapon, family, baseline_items, upstream_recipes)
        if any(not c["equal"] for c in checks) or len({c["level"] for c in checks}) < 2:
            raise ValueError(f"Review lacks two independent, conflict-free recipe levels: {entry['id']}")
        match.update(family=family, status="reviewed_identity_with_recipe_support", review={
            "id": entry["id"], "reason": entry["reason"], "profile_differences": differences,
            "independent_recipe_checks": checks, "initial_status": match["status"],
        })
        occupied.add(family)
        for diff in differences:
            value_differences.append(diff | {"page": weapon["page"], "weapon_id": family * 256 + diff["level"],
                                             "review_id": entry["id"]})
    return value_differences


def classify_costs(weapons, differences, upstream_recipes):
    by_page = {w["page"]: w for w in weapons}
    result = []
    for diff in differences:
        if diff["field"] not in ("creation_cost", "upgrade_cost"):
            continue
        level = next(p for p in by_page[diff["page"]]["levels"] if p["level"] == diff["level"])
        xx = "[XX]" in level["performance_cells"][0]
        if not alternatives(upstream_recipes, diff["weapon_id"], diff["kind"]):
            pattern = "no_corresponding_upstream_recipe"
        elif diff["field"] == "creation_cost":
            pattern = ("create_ratio_3_to_2" if diff["site"] * 2 == diff["upstream"] * 3 else
                       "create_ratio_2_to_1" if diff["site"] == diff["upstream"] * 2 else
                       "create_other_difference")
        else:
            pattern = "xx_upgrade_difference" if xx else "legacy_upgrade_difference"
        result.append(diff | {"pattern": pattern, "site_marks_xx": xx,
                              "resolution": "retain_site_price_and_upstream_value; game_price_unverified"})
    return result

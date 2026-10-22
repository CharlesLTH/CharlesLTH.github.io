"""Conservative, reproducible candidate mappings; never overwrite either source."""

from collections import Counter, defaultdict

from .html_source import signature


def upstream_data(connection):
    families, recipes = defaultdict(list), defaultdict(lambda: defaultdict(list))
    weapons = {}
    for row in connection.execute("SELECT * FROM weapons ORDER BY _id"):
        row = dict(row)
        # This encoding is a property of THIS community database, not game IDs.
        if row["_id"] // 256 != row["family"] or row["_id"] % 256 == 0:
            raise ValueError("Unexpected upstream weapon family encoding")
        row["level"] = row["_id"] % 256
        families[row["family"]].append(row)
        weapons[row["_id"]] = row
    for row in connection.execute("""
        SELECT c.*, i.name, i.type AS item_type FROM components c
        JOIN items i ON i._id=c.component_item_id
        JOIN weapons w ON w._id=c.created_item_id ORDER BY c._id
    """):
        row = dict(row)
        recipes[row["created_item_id"]][row["type"]].append(row)
    return families, weapons, recipes


def upstream_profile(row):
    return dict(
        level=row["level"], attack=row["attack"], slots=row["num_slots"],
        affinity=str(row["affinity"] or "0").replace(" ", "").replace("+", ""),
        defense=row["defense"] or 0,
        elements=sorted((row[key], row[value]) for key, value in
                        [("element", "element_attack"), ("element_2", "element_2_attack")]
                        if row[key]),
    )


def match_weapons(site_weapons, families):
    local, remote = defaultdict(list), defaultdict(list)
    for weapon in site_weapons:
        local[signature(weapon["wtype"], weapon["levels"])].append(weapon["page"])
    for family, levels in families.items():
        remote[signature(levels[0]["wtype"], [upstream_profile(r) for r in levels])].append(family)
    matches = {}
    for key, pages in local.items():
        candidates = remote.get(key, [])
        unique = len(pages) == len(candidates) == 1
        for page in pages:
            matches[page] = {
                "family": candidates[0] if unique else None,
                "status": "profile_unique" if unique else "ambiguous" if candidates else "unmatched",
                "candidate_families": candidates,
                "same_profile_site_pages": pages,
                "recipe_checks": {},
            }
    return matches


def alternatives(upstream_recipes, weapon_id, kind):
    kinds = ["Create", "Create B"] if kind == "Create" else [kind]
    return [(k, upstream_recipes.get(weapon_id, {}).get(k)) for k in kinds
            if upstream_recipes.get(weapon_id, {}).get(k)]


def physical(parts):
    # A parent weapon is an input edge, not a physical material. "Materials"
    # are point pools, whose quantity has a different unit from item counts.
    return [p for p in parts if p["item_type"] not in ("Weapon", "Materials")]


def recipe_ingredients(recipe):
    return recipe["ingredients"] + recipe.get("reviewed_ingredients", [])


def unresolved_fragments(recipe):
    resolved = {i["raw_text"] for i in recipe.get("reviewed_ingredients", [])}
    return [value for value in recipe["unparsed"] if value not in resolved]


def infer_items(site_weapons, matches, upstream_recipes, exclusions=()):
    constraints = defaultdict(list)
    for weapon in site_weapons:
        family = matches[weapon["page"]]["family"]
        if family is None:
            continue
        for recipe in weapon["recipes"]:
            if unresolved_fragments(recipe):
                continue
            weapon_id = family * 256 + recipe["level"]
            variants = [physical(parts) for _, parts in alternatives(
                upstream_recipes, weapon_id, recipe["kind"])]
            # A size/quantity mismatch is evidence of a discrepancy, not a
            # reason to force unrelated ingredients to share an identity.
            expected = Counter(i["quantity"] for i in recipe_ingredients(recipe))
            variants = [parts for parts in variants
                        if Counter(p["quantity"] for p in parts) == expected]
            if not variants:
                continue
            for ingredient in recipe_ingredients(recipe):
                candidates = sorted({p["component_item_id"] for parts in variants for p in parts
                                     if p["quantity"] == ingredient["quantity"]})
                evidence = {
                    "weapon_page": weapon["page"], "weapon_id": weapon_id,
                    "level": recipe["level"], "kind": recipe["kind"],
                    "quantity": ingredient["quantity"], "candidates": candidates,
                    "locator": recipe["locator"],
                }
                for exclusion in exclusions:
                    if (weapon["page"], recipe["level"], recipe["kind"], ingredient["item_page"]) == (
                            exclusion["page"], exclusion["level"], exclusion["kind"], exclusion["item_page"]) and recipe["locator"] == exclusion["locator"]:
                        evidence["excluded_by_review"] = exclusion["id"]
                constraints[ingredient["item_page"]].append(evidence)
    results = {}
    for page, evidence in sorted(constraints.items()):
        candidates = intersection(evidence)
        sources = len({e["weapon_page"] for e in evidence if not e.get("excluded_by_review")})
        status = ("conflict" if not candidates else "ambiguous" if len(candidates) != 1
                  else "insufficient_support" if sources < 2 else "recipe_inferred")
        item_id = next(iter(candidates)) if status == "recipe_inferred" else None
        excluded = sum(bool(e.get("excluded_by_review")) for e in evidence)
        if item_id is not None and excluded:
            status = "recipe_inferred_with_exclusions"
        results[page] = {"item_id": item_id,
                         "status": status, "candidate_ids": sorted(candidates),
                         "supporting_weapon_lines": sources, "excluded_constraints": excluded,
                         "evidence": evidence}
    inverse = defaultdict(list)
    for page, match in results.items():
        if match["item_id"] is not None:
            inverse[match["item_id"]].append(page)
    for pages in inverse.values():
        if len(pages) > 1:
            for page in pages:
                results[page]["status"] = "non_bijective"
                results[page]["item_id"] = None
    return results


def intersection(evidence):
    evidence = [e for e in evidence if not e.get("excluded_by_review")]
    if not evidence:
        return set()
    result = set(evidence[0]["candidates"])
    for row in evidence[1:]:
        result.intersection_update(row["candidates"])
    return result


def independent_item(match, excluded_page):
    """Re-derive without this weapon line, avoiding self-confirming checks."""
    if not match or match["item_id"] is None:
        return None
    evidence = [e for e in match["evidence"] if e["weapon_page"] != excluded_page
                and not e.get("excluded_by_review")]
    if len({e["weapon_page"] for e in evidence}) < 2:
        return None
    ids = intersection(evidence)
    return next(iter(ids)) if len(ids) == 1 else None


def check_recipes(site_weapons, matches, item_matches, weapons, upstream_recipes):
    checks, differences = [], []
    for weapon in site_weapons:
        match = matches[weapon["page"]]
        if match["family"] is None:
            continue
        for recipe in weapon["recipes"]:
            weapon_id = match["family"] * 256 + recipe["level"]
            variants = alternatives(upstream_recipes, weapon_id, recipe["kind"])
            source = {"page": weapon["page"], "level": recipe["level"],
                      "kind": recipe["kind"], "locator": recipe["locator"], "weapon_id": weapon_id}
            mapped = [(independent_item(item_matches.get(i["item_page"]), weapon["page"]),
                       i["quantity"]) for i in recipe_ingredients(recipe)]
            expected = Counter(mapped)
            actual = [(k, Counter((p["component_item_id"], p["quantity"]) for p in physical(parts)))
                      for k, parts in variants]
            if unresolved_fragments(recipe):
                status = "parse_incomplete"
            elif not recipe_ingredients(recipe):
                status = "no_physical_ingredients"
            elif any(item_id is None for item_id, _ in mapped):
                status = "mapping_incomplete"
            elif not actual:
                status = "upstream_recipe_missing"
            elif any(expected == quantities for _, quantities in actual):
                status = "physical_ingredients_equal"
            else:
                status = "physical_ingredients_differ"
            check = source | {"status": status}
            checks.append(check)
            if status in ("physical_ingredients_differ", "upstream_recipe_missing"):
                differences.append(source | {"field": "physical_ingredients", "site": mapped,
                                             "upstream": {k: list(v.elements()) for k, v in actual}})
            cost_key = "creation_cost" if recipe["kind"] == "Create" else "upgrade_cost"
            upstream_cost = weapons[weapon_id][cost_key]
            if recipe["money"] is not None and recipe["money"] != upstream_cost:
                differences.append(source | {"field": cost_key, "site": recipe["money"],
                                             "upstream": upstream_cost})
        counts = Counter(c["status"] for c in checks if c["page"] == weapon["page"])
        match["recipe_checks"] = dict(counts)
        if counts["physical_ingredients_differ"] or counts["upstream_recipe_missing"]:
            match["status"] = "reviewed_identity_with_recipe_conflicts" if match.get("review") else "profile_with_recipe_conflicts"
        elif counts["physical_ingredients_equal"]:
            match["status"] = "reviewed_identity_with_recipe_support" if match.get("review") else "profile_with_recipe_support"
    return checks, differences

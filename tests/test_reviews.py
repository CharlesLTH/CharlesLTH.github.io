from copy import deepcopy

import pytest

from mhxx_data.matching import infer_items
from mhxx_data.reviews import apply_weapon_reviews, classify_costs, validate_registry


def registry_fixture():
    return {"schema_version": 1, "upstream_database_sha256": "upstream",
            "weapon_identities": [{"id": "identity-a", "page_sha256": {"ida/a.html": "page-hash"}}],
            "item_constraint_exclusions": [], "unlinked_ingredients": []}


def test_review_registry_rejects_changed_source_page():
    with pytest.raises(ValueError, match="Stale review"):
        validate_registry(registry_fixture(), [{"path": "ida/a.html", "sha256": "changed"}], "upstream")


def test_review_registry_rejects_changed_database():
    with pytest.raises(ValueError, match="different upstream"):
        validate_registry(registry_fixture(), [], "new-database")


def test_review_registry_rejects_duplicate_ids():
    registry = registry_fixture()
    registry["weapon_identities"] *= 2
    with pytest.raises(ValueError, match="Duplicate review"):
        validate_registry(registry, [{"path": "ida/a.html", "sha256": "page-hash"}], "upstream")


def identity_fixture():
    levels = [dict(level=level, attack=100, slots=0, affinity="-30/10", defense=0, elements=[])
              for level in (1, 2)]
    remote = [dict(level=level, wtype="Great Sword", attack=100, num_slots=0, affinity="10",
                   defense=0, element="", element_2="") for level in (1, 2)]
    weapon = dict(page="weapon", wtype="Great Sword", levels=levels, recipes=[
        dict(level=level, kind="Improve", locator=f"/r{level}", unparsed=[],
             ingredients=[dict(item_page="ore", quantity=level)]) for level in (1, 2)])
    upstream = {256 + level: {"Improve": [dict(component_item_id=100, quantity=level, item_type="")]}
                for level in (1, 2)}
    items = {"ore": dict(item_id=100, evidence=[dict(weapon_page=p, candidates=[100]) for p in ("other-a", "other-b")])}
    registry = {"weapon_identities": [dict(id="weapon-review", page="weapon", family=1,
                reason="negative_affinity_missing_in_upstream", expected_profile_differences=[
                    dict(level=level, field="affinity", site="-30/10", upstream="10") for level in (1, 2)])]}
    matches = {"weapon": dict(family=None, status="unmatched")}
    return [weapon], registry, matches, {1: remote}, items, upstream


def test_identity_review_preserves_both_affinities_and_requires_recipe_evidence():
    args = identity_fixture()
    differences = apply_weapon_reviews(*args)
    assert args[2]["weapon"]["family"] == 1
    assert len(differences) == 2
    assert args[0][0]["levels"][0]["affinity"] == "-30/10"
    assert args[3][1][0]["affinity"] == "10"


def test_identity_review_cannot_use_its_own_material_evidence():
    args = identity_fixture()
    args[4]["ore"]["evidence"][0]["weapon_page"] = "weapon"
    with pytest.raises(ValueError, match="two independent"):
        apply_weapon_reviews(*args)


def test_identity_review_rejects_unexpected_numeric_difference():
    args = identity_fixture()
    args[0][0]["levels"][0]["attack"] = 200
    with pytest.raises(ValueError, match="differences changed"):
        apply_weapon_reviews(*args)


def test_identity_review_rejects_conflicting_recipe():
    args = identity_fixture()
    args[5][258]["Improve"][0]["quantity"] = 99
    with pytest.raises(ValueError, match="conflict-free"):
        apply_weapon_reviews(*args)


def test_exclusion_is_limited_to_one_reviewed_recipe_occurrence():
    weapons = [dict(page=p, recipes=[dict(level=1, kind="Create", locator="/r", unparsed=[],
                     ingredients=[dict(item_page="fang", quantity=2)])]) for p in ("a", "b", "conflict")]
    matches = {p: dict(family=n) for n, p in enumerate(("a", "b", "conflict"), start=1)}
    upstream = {n * 256 + 1: {"Create": [dict(component_item_id=100 if n < 3 else 200,
                    quantity=2, item_type="")]} for n in (1, 2, 3)}
    review = dict(id="one-conflict", page="conflict", level=1, kind="Create", item_page="fang", locator="/r")
    assert infer_items(weapons, matches, upstream)["fang"]["status"] == "conflict"
    result = infer_items(weapons, matches, upstream, [review])["fang"]
    assert result["item_id"] == 100 and result["status"] == "recipe_inferred_with_exclusions"
    assert result["excluded_constraints"] == 1
    assert len(result["evidence"]) == 3  # excluded evidence is still visible
    review["locator"] = "/different-recipe"
    assert infer_items(weapons, matches, upstream, [review])["fang"]["status"] == "conflict"


def test_price_patterns_are_labels_not_numeric_corrections():
    weapons = [dict(page="a", levels=[dict(level=1, performance_cells=["LV1"])])]
    diff = dict(page="a", level=1, kind="Create", weapon_id=257, field="creation_cost", site=1275, upstream=850)
    original = deepcopy(diff)
    review, = classify_costs(weapons, [diff], {257: {"Create": [dict(quantity=1)]}})
    assert review["pattern"] == "create_ratio_3_to_2"
    assert diff == original
    review, = classify_costs(weapons, [diff], {})
    assert review["pattern"] == "no_corresponding_upstream_recipe"

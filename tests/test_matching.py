from mhxx_data.matching import independent_item, infer_items, match_weapons


def test_equal_profiles_on_either_side_stay_ambiguous():
    p = dict(level=1, attack=60, slots=0, affinity="0", defense=0, elements=[])
    raw = dict(level=1, attack=60, num_slots=0, affinity="0", defense=0,
               element="", element_2="", wtype="Great Sword")
    local = [dict(page="a", wtype="Great Sword", levels=[p])]
    assert match_weapons(local, {1: [raw], 2: [raw]})["a"]["family"] is None
    result = match_weapons(local + [dict(page="b", wtype="Great Sword", levels=[p])], {1: [raw]})
    assert all(r["status"] == "ambiguous" for r in result.values())


def test_recipe_mapping_requires_multiple_lines_and_rejects_conflicts():
    def site(page):
        return dict(page=page, recipes=[dict(level=1, kind="Create", unparsed=[], locator="/td",
                    ingredients=[dict(item_page="ore", quantity=2)])])

    def remote(item):
        return {"Create": [dict(component_item_id=item, quantity=2, item_type="")]}

    matches = {"a": {"family": 1}, "b": {"family": 2}}
    upstream = {257: remote(100), 513: remote(100)}
    assert infer_items([site("a")], matches, upstream)["ore"]["status"] == "insufficient_support"
    assert infer_items([site("a"), site("b")], matches, upstream)["ore"]["item_id"] == 100
    upstream[513] = remote(200)
    result = infer_items([site("a"), site("b")], matches, upstream)["ore"]
    assert result["status"] == "conflict" and result["item_id"] is None


def test_independent_check_cannot_confirm_itself():
    match = dict(item_id=100, evidence=[
        dict(weapon_page="a", candidates=[100]),
        dict(weapon_page="b", candidates=[100, 200]),
        dict(weapon_page="c", candidates=[100, 200]),
    ])
    assert independent_item(match, "a") is None
    match["evidence"].append(dict(weapon_page="d", candidates=[100]))
    assert independent_item(match, "a") == 100

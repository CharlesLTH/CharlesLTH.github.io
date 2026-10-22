import json
from collections import Counter
from pathlib import Path

import pytest
from lxml import html

from mhxx_data.domains import grid, ingredient_segments, parse_armor, parse_monster, parse_quest, parse_skill, rewards
from mhxx_data.html_source import parse_recipe, restore_values, text
from mhxx_data.query import connect, domain, item

ROOT = Path(__file__).resolve().parents[1] / "games/mhxx_old"


def parse(page, parser):
    document = html.fromstring((ROOT / page).read_bytes())
    restore_values(document)
    return parser(document, page, document.xpath("//table[not(ancestor::table)]"))


def test_table_grid_preserves_spans_and_actual_cells():
    table = html.fromstring('<table><tr><td rowspan="2">A</td><td>B</td><td>C</td></tr>'
                            '<tr><td colspan="2">condition</td></tr></table>')
    g = grid(table)
    assert [[text(c) for c in row] for row in g] == [["A", "B", "C"], ["A", "condition", "condition"]]
    assert g[0][0] is g[1][0] and g[1][1] is g[1][2]


def test_reward_conditions_are_not_probabilities_and_unknown_rates_remain_null():
    cell = html.fromstring('<td><span>砦耐久値20%以上</span><br><div>'
                           '<a href="../ida/100.html">石 x2</a> 30%</div>'
                           '<span>砦耐久値40%以上</span><br><div>'
                           '<a href="../ida/101.html">骨</a></div></td>')
    rs, issues = rewards(cell, "ida/1.html", group="主任务", rank=None, attempts=None)
    assert [(r["condition"], r["quantity"], r["percentage"]) for r in rs] == [
        ("砦耐久値20%以上", 2, 30), ("砦耐久値40%以上", 1, None)]
    assert [i["kind"] for i in issues] == ["missing_probability"]


def test_monster_carve_attempts_are_separate_from_stack_size_and_hitzones_keep_states():
    monster = parse("data/1829.html", parse_monster)
    r = monster["rewards"][0]
    assert (r["attempts"], r["quantity"], r["percentage"], r["rank"]) == (3, 1, 43, "LR")
    assert monster["hitzones"][0]["values"]["切"] == "65 (70)"
    assert any("\n" in value for h in monster["hitzones"] for value in h["values"].values())
    # Colspan condition rows must not generate a reward for every difficulty.
    assert len(monster["rewards"]) == 125


def test_quest_reward_slots_and_subquest_money_are_distinct():
    quest = parse("ida/218315.html", parse_quest)
    assert quest["metadata"]["time_minutes"] == 50
    assert quest["metadata"]["reward_zenny"] == 300
    assert quest["metadata"]["fee_zenny"] == 0
    assert len(quest["rewards"]) == 20
    assert [(r["quantity"], r["percentage"]) for r in quest["rewards"][:2]] == [(2, 100), (2, 20)]
    assert Counter(r["group"] for r in quest["rewards"]) == {"主任务报酬 [1段目]": 9, "主任务报酬 [2段目]": 11}
    assert parse("ida/218317.html", parse_quest)["metadata"]["sub_reward_zenny"] == 600


def test_monster_appearances_keep_relative_gauges_intrusions_counts_and_unknown_values():
    entries = parse("data/1829.html", parse_monster)["quest_appearances"]
    assert len(entries) == 50
    by_quest = {r["quest_page"]: r for r in entries}
    normal = by_quest["ida/220240.html"]
    assert (normal["health_bar"], normal["defense_bar"], normal["intrusion"]) == (12, 5, False)
    assert normal["location_page"] == "data/2400.html"
    intrusion = by_quest["ida/220173.html"]
    assert intrusion["intrusion"] and len(intrusion["monsters"]) == 3
    assert all(m["intrusion"] for m in intrusion["monsters"])
    assert by_quest["ida/309881.html"]["monsters"][0]["count"] == 2
    assert by_quest["ida/267299.html"]["health_bar"] is None
    assert by_quest["ida/267299.html"]["defense_bar"] is None
    # The source repeats one Cephadrome appearance. Preserve both source locators.
    repeated = [r for r in parse("data/1974.html", parse_monster)["quest_appearances"]
                if r["quest_page"] == "ida/220251.html"]
    assert len(repeated) == 2 and repeated[0]["xpath"] != repeated[1]["xpath"]


def test_armor_recipe_without_line_breaks_preserves_items_and_material_points():
    cell = html.fromstring('<td><a href="../ida/100.html">铠玉</a> x1 '
                           '<a href="../ida/101.html">龙玉</a> x2 矿石素材[G级] x6</td>')
    recipe = parse_recipe(ingredient_segments(cell), "ida/1.html", 4, "Improve", "/fixture")
    assert [(i["item_page"], i["quantity"]) for i in recipe["ingredients"]] == [("ida/100.html", 1), ("ida/101.html", 2)]
    assert recipe["material_points"][0]["points"] == 6 and not recipe["unparsed"]


def test_armor_totals_are_excluded_and_shared_recipes_are_not_duplicated():
    armor = parse("ida/218353.html", parse_armor)
    assert len(armor["pieces"]) == 10
    assert [p["hunter_type"] for p in armor["pieces"]] == ["剑士用"] * 5 + ["神枪手用"] * 5
    assert len([r for r in armor["recipes"] if r["kind"] == "Create"]) == 5
    assert len([r for r in armor["recipes"] if r["kind"] == "Improve"]) == 14
    assert all(p["skills"] for p in armor["pieces"])


def test_skill_rowspan_does_not_shift_activation_thresholds():
    skill = parse("ida/183524.html", parse_skill)
    assert [(s["name"], s["points"]) for s in skill["activations"]] == [
        ("激运", 20), ("强运", 15), ("幸运", 10), ("霉运", -10), ("灾难", -15)]


@pytest.fixture(scope="module")
def database():
    with connect() as connection:
        yield connection


def test_full_snapshot_retains_all_targeted_entities_and_source_gaps(database):
    assert dict(database.execute("SELECT kind,count(*) FROM site_domain_pages GROUP BY kind")) == {
        "monster": 130, "quest": 1337, "armor": 656, "skill": 205}
    assert database.execute("SELECT count(*) FROM site_armor_pieces").fetchone()[0] == 5685
    assert database.execute("SELECT count(*) FROM site_rewards WHERE percentage IS NULL").fetchone()[0] == 48
    assert database.execute("SELECT count(*) FROM site_rewards WHERE item_page IS NULL").fetchone()[0] == 3
    report = json.loads(database.execute("SELECT value_json FROM source_manifest WHERE key='audit_summary'").fetchone()[0])
    assert not report["domains"]["unparsed_armor_recipes"]
    assert not any(i["kind"] == "unparsed_reward" for i in report["domains"]["issues"])
    # Empty source hitzone tables stay empty rather than borrowing MHGU values.
    assert database.execute("SELECT count(*) FROM site_monster_hitzones WHERE page='data/1837.html'").fetchone()[0] == 0
    assert database.execute("SELECT count(*) FROM site_monster_quests").fetchone()[0] == 2347
    assert database.execute("SELECT count(*) FROM site_monster_quests WHERE health_bar IS NULL AND defense_bar IS NULL").fetchone()[0] == 374


def test_item_can_trace_local_monsters_quests_and_armor_without_mhgu_mapping(database):
    result = item(database, "219849", 1)
    assert result["name"] == "斩龙的鱗"
    assert result["site_sources"]["monster"]["total"] == 5
    assert result["site_sources"]["quest"]["total"] == 14
    assert result["armor_recipes"]["total"] > 0
    r = result["site_sources"]["monster"]["sample"][0]
    assert r["page"] == "data/1829.html" and r["percentage"] == 43 and r["attempts"] == 3


def test_armor_max_defense_difference_and_skill_relations_survive(database):
    result = domain(database, "armor", "218352", 1)
    assert result["pieces"][0]["max_defense"] == 51
    difference = next(d for d in result["differences"] if d["ordinal"] == 0)
    assert (difference["field"], difference["site_value_json"], difference["upstream_value_json"]) == ("max_defense", "51", "26")
    skill = result["pieces"][0]["skills"][0]
    assert (skill["skill_page"], skill["points"]) == ("ida/183534.html", 3)
    assert domain(database, "skill", "183534", 1)["armor"]["total"] > 0


def test_quest_candidate_is_explicitly_a_limited_projection_and_hitzone_notes_survive(database):
    quest = domain(database, "quest", "218315", 1)
    assert quest["matches"][0]["upstream_name"] == "Wipe Out!"
    assert "reward slots not compared" in quest["matches"][0]["evidence"]["scope"]
    monster = domain(database, "monster", "1829", 1)
    assert any("肉质カッコ内は赤热时" in n["text"] for n in monster["notes"])
    assert monster["quests"]["total"] > 0


def test_domain_comparison_never_assigns_duplicate_targets(database):
    assert not database.execute("""SELECT kind,upstream_id FROM domain_matches WHERE upstream_id IS NOT NULL
        GROUP BY kind,upstream_id HAVING count(*)>1""").fetchall()
    assert database.execute("SELECT count(*) FROM domain_matches WHERE upstream_id IS NULL").fetchone()[0] > 0

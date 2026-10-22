import json
from pathlib import Path

import pytest
from lxml import html

from mhxx_data.acquisition import gathering_attempts, numeric_range, parse_combining, parse_map
from mhxx_data.acquisition_database import combining_candidates
from mhxx_data.html_source import restore_values
from mhxx_data.query import combining, connect, item, map_details, weapon

ROOT = Path(__file__).resolve().parents[1] / "games/mhxx_old"


def document(page):
    doc = html.fromstring((ROOT / page).read_bytes())
    restore_values(doc)
    return doc


def test_gathering_attempts_distinguish_rare_points_and_unlimited_attempts():
    rare = gathering_attempts("ランダム [稀有度] 2-4回")
    assert rare == dict(fixed=False, rare=True, attempts_min=2, attempts_max=4, attempts_infinite=False)
    endless = gathering_attempts("固定 ∞回")
    assert endless == dict(fixed=True, rare=False, attempts_min=None, attempts_max=None, attempts_infinite=True)
    assert gathering_attempts("固定 2回")["attempts_max"] == 2


@pytest.mark.parametrize("value", ["0", "4～2", "?", "1/3"])
def test_unknown_or_invalid_quantity_ranges_fail_instead_of_guessing(value):
    with pytest.raises(ValueError):
        numeric_range(value)


def test_map_rowspans_keep_normal_and_rare_variants_separate_and_do_not_normalize_rates():
    result = parse_map(document("data/2400.html"), "data/2400.html", "古代林")
    section = result["sections"][0]
    assert (section["area"], section["rank"]) == ("1", "LR")
    first = section["nodes"][0]
    assert (first["attempts_min"], first["attempts_max"]) == (6, 8)
    assert [(r["item_page"], r["quantity"], r["percentage"]) for r in first["items"][:1]] == [("ida/189643.html", 1, 30)]
    variants = [n for n in section["nodes"] if n["point"] == 5]
    assert {n["rare"] for n in variants} == {True, False}
    assert len({n["xpath"] for n in variants}) == 2
    third = next(n for n in section["nodes"] if n["point"] == 3)
    assert [r["percentage"] for r in third["items"]] == [35, 35, 35, 8]
    assert sum(r["percentage"] for r in third["items"]) == 113
    assert any("確率は目安です" in note["text"] for note in result["notes"])


def test_combining_keeps_unlinked_ammunition_and_output_quantity_ranges():
    result = parse_combining(document("data/2503.html"), "data/2503.html")
    ammo, = [r for r in result["recipes"] if r["output"]["label"] == "LV2通常弾"]
    assert ammo["output"]["item_page"] is None
    assert (ammo["amount_min"], ammo["amount_max"], ammo["percentage"]) == (2, 4, 95)
    assert [r["label"] for r in ammo["inputs"]] == ["空心果", "针果"]
    assert all(r["item_page"] for r in ammo["inputs"])
    potion = result["recipes"][0]
    assert potion["output"]["item_page"] == "ida/188416.html"
    assert [r["item_page"] for r in potion["inputs"]] == ["ida/189643.html", "ida/188272.html"]


def test_combining_candidates_need_independent_roles_and_do_not_assign_unknown_outputs():
    recipe = dict(upstream_result_id=None, amount_min=2, amount_max=4, percentage=95)
    source = [dict(_id=10, created_item_id=300, item_1_id=100, item_2_id=200,
                   amount_made_min=2, amount_made_max=4, percentage=95)]
    assert combining_candidates(recipe, [None, 200], source) == ([], "insufficient_item_evidence")
    assert combining_candidates(recipe, [200, 100], source) == ([10], "known_roles_unique")
    assert recipe["upstream_result_id"] is None
    assert combining_candidates(recipe | {"percentage": 90}, [200, 100], source) == ([], "no_known_roles_match")
    assert combining_candidates(recipe | {"upstream_result_id": 100}, [100, None], source) == ([], "insufficient_item_evidence")


@pytest.fixture(scope="module")
def database():
    with connect() as connection:
        yield connection


def test_snapshot_covers_every_map_and_combining_row_including_source_gaps(database):
    expected = dict(site_maps=24, site_map_sections=528, site_gathering_nodes=2914,
                    site_gathering=14890, site_combining=183, site_combining_inputs=366)
    assert {name: database.execute(f"SELECT count(*) FROM {name}").fetchone()[0] for name in expected} == expected
    assert database.execute("SELECT count(*) FROM site_map_sections WHERE empty_text IS NOT NULL").fetchone()[0] == 89
    assert database.execute("SELECT count(*) FROM site_gathering WHERE item_page IS NULL").fetchone()[0] == 8
    assert database.execute("SELECT count(*) FROM site_combining WHERE result_item_page IS NULL").fetchone()[0] == 42
    report = json.loads(database.execute("SELECT value_json FROM source_manifest WHERE key='audit_summary'").fetchone()[0])
    assert len(report["acquisition"]["gathering_probability_sums_not_100"]) == 389


def test_material_can_trace_local_gathering_combining_and_weapon_recipe(database):
    herb = item(database, "189643", 2)
    assert herb["site_sources"]["gathering"]["total"] == 337
    assert herb["combining_uses"]["total"] == 2
    potion = item(database, "188416", 1)
    recipe, = potion["site_sources"]["combining"]["sample"]
    assert recipe["result_label"] == "回复药" and recipe["percentage"] == 95
    assert [r["label"] for r in recipe["inputs"]] == ["药草", "蓝蘑菇"]
    output = weapon(database, "218099", 3, 1)
    ingredient, = output["site_recipes"][0]["ingredients"]
    assert ingredient["site_sources"]["gathering"]["total"] == 91


def test_map_query_keeps_rank_area_variants_and_explicit_empty_sections(database):
    result = map_details(database, "2400", "1", "LR", 4)
    assert len(result["sections"]) == 1
    assert result["nodes"]["total"] > len(result["nodes"]["sample"])
    assert all((n["area"], n["rank"]) == ("1", "LR") for n in result["nodes"]["sample"])
    assert [n["percentage_sum"] for n in result["nodes"]["sample"][:4]] == [100, 100, 113, 105]
    empty = database.execute("SELECT page,area,rank FROM site_map_sections WHERE empty_text IS NOT NULL LIMIT 1").fetchone()
    result = map_details(database, *empty, limit=2)
    assert result["nodes"]["total"] == 0 and result["sections"][0]["empty_text"] == "无し"


def test_unlinked_combining_output_is_searchable_without_inventing_a_local_item(database):
    result = combining(database, "LV2通常弾", 2)
    assert result["total"] == 1
    recipe, = result["sample"]
    assert recipe["result_item_page"] is None and recipe["result_label"] == "LV2通常弾"
    assert combining(database, "%", 2)["total"] == 0  # literal text, not an SQL wildcard


def test_destination_candidates_preserve_day_night_and_single_quest_disagreement(database):
    assert {r[0] for r in database.execute("SELECT location_id FROM location_candidates WHERE page='data/2400.html'")} == {1, 101}
    conflict = database.execute("SELECT status,supporting_quests FROM location_candidates WHERE page='data/2841.html' AND location_id=10").fetchone()
    assert tuple(conflict) == ("single_quest_support", 1)
    assert database.execute("SELECT count(*) FROM gathering_checks").fetchone()[0] == 14890
    assert database.execute("SELECT count(*) FROM combining_matches WHERE combining_id IS NULL").fetchone()[0] > 0

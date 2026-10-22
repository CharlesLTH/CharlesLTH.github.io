import hashlib
import json
import sqlite3
import subprocess

import pytest

from mhxx_data.pipeline import DEFAULT_DATABASE, read_source, require_digest
from mhxx_data.query import connect, weapon


def test_source_provenance_supports_a_repository_without_history(tmp_path, monkeypatch):
    from mhxx_data import pipeline
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    assert pipeline.site_commit(tmp_path / "games/mhxx_old") is None


def test_source_hash_mismatch_is_fatal():
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        require_digest(b"modified source", hashlib.sha256(b"pinned source").hexdigest(), "fixture")


@pytest.fixture(scope="module")
def database():
    if not DEFAULT_DATABASE.exists():
        pytest.fail("Run .venv/bin/python scripts/data.py build before the integration tests")
    with connect() as connection:
        yield connection


def test_import_preserves_every_upstream_table_value(database, tmp_path):
    path = tmp_path / "original.sqlite"
    path.write_bytes(read_source())
    expected = json.loads(database.execute("SELECT value_json FROM source_manifest WHERE key='original_table_counts'").fetchone()[0])
    with sqlite3.connect(path) as original:
        for table, count in expected.items():
            sql = 'SELECT * FROM "' + table.replace('"', '""') + '" ORDER BY rowid'
            source_rows = original.execute(sql)
            imported_rows = database.execute(sql)
            seen = 0
            while batch := source_rows.fetchmany(500):
                assert [tuple(r) for r in imported_rows.fetchmany(500)] == batch, table
                seen += len(batch)
            assert seen == count and not imported_rows.fetchone(), table


def test_full_snapshot_retains_unmatched_records_and_explicit_cost_conflict(database):
    counts = {table: database.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
              for table in ("site_pages", "site_weapon_lines", "site_weapon_levels", "site_items")}
    assert counts == dict(site_pages=9044, site_weapon_lines=1592, site_weapon_levels=10911, site_items=2450)
    assert database.execute("SELECT count(*) FROM weapon_matches WHERE family IS NULL").fetchone()[0] > 0
    conflict = database.execute("""SELECT d.site_value_json,d.upstream_value_json
        FROM audit_differences d JOIN site_recipes r ON r.id=d.recipe_id
        WHERE r.page='ida/218099.html' AND r.level=1 AND d.field='creation_cost'""").fetchone()
    assert tuple(conflict) == ("1275", "850")


def test_weapon_to_material_to_gathering_path_and_points_units(database):
    result = weapon(database, "218099", 3, limit=1)
    recipe, = result["site_recipes"]
    ingredient, = recipe["ingredients"]
    assert (ingredient["name"], ingredient["quantity"], ingredient["upstream_item_id"]) == ("圆盘石", 2, 321)
    assert ingredient["mhgu"]["name"] == "Disc Stone"
    gathering = ingredient["mhgu"]["sources"]["gathering"]
    assert gathering["total"] > 0 and gathering["sample"][0]["item_id"] == 321
    assert recipe["material_points"] == [{"label": "矿石素材", "points": 6}]
    pool, = [p for p in result["upstream_recipes"] if p["quantity_unit"] == "points"]
    assert pool["quantity"] == 6 and pool["item"]["contributors"]["total"] > 0
    assert result["match"]["status"] == "profile_with_recipe_support"


def test_reviewed_candidates_cover_upstream_without_dropping_site_only_weapons(database):
    upstream = {r[0] for r in database.execute("SELECT DISTINCT family FROM weapons")}
    mapped = {r[0] for r in database.execute("SELECT family FROM weapon_matches WHERE family IS NOT NULL")}
    assert upstream == mapped
    assert database.execute("SELECT count(*) FROM weapon_matches WHERE family IS NULL").fetchone()[0] == 7
    assert database.execute("SELECT count(*) FROM data_reviews WHERE kind='weapon_identities'").fetchone()[0] == 29
    original_ids = {r[0] for r in database.execute("SELECT _id FROM weapons")}
    assert {r[0] for r in database.execute("SELECT upstream_id FROM candidate_weapon_labels")} == original_ids


def test_dual_affinity_survives_reconciliation(database):
    result = weapon(database, "292565", 1, limit=1)
    assert result["site"]["affinity"] == "-45/20"
    assert result["upstream_weapon"]["affinity"] == "20"
    assert result["match"]["status"] == "reviewed_identity_with_recipe_support"
    assert result["performance_differences"][0]["field"] == "affinity"


def test_item_identity_is_recovered_but_recipe_disagreement_remains(database):
    row = database.execute("SELECT item_id,status FROM item_matches WHERE page='ida/188750.html'").fetchone()
    assert tuple(row) == (1386, "recipe_inferred_with_exclusions")
    result = weapon(database, "234849", 1, limit=1)
    recipe, = [r for r in result["site_recipes"] if r["kind"] == "Create"]
    assert recipe["check"] == [{"status": "physical_ingredients_differ"}]
    assert any(i["name"] == "轰龙牙" for i in recipe["ingredients"])
    assert any(p["item"]["name"] == "Tigrex Claw" for p in result["upstream_recipes"])


@pytest.mark.parametrize("page,item_id", [("288458", 327), ("288520", 2038)])
def test_unlinked_annotations_are_visible_without_rewriting_source(database, page, item_id):
    result = weapon(database, page, 1, limit=1)
    recipe, = [r for r in result["site_recipes"] if r["kind"] == "Create"]
    assert json.loads(recipe["unparsed_json"])  # original unlinked text remains
    annotated, = [i for i in recipe["ingredients"] if i["reference_origin"] == "review_annotation"]
    assert annotated["upstream_item_id"] == item_id and annotated["review_id"]
    assert recipe["check"] == [{"status": "physical_ingredients_equal"}]


def test_site_price_policy_keeps_the_disagreement_visible(database):
    row = database.execute("""SELECT display_zenny,mhgu_stored_zenny,difference_pattern,review_status
        FROM mhxx_recipe_costs WHERE page='ida/218099.html' AND level=1 AND kind='Create'""").fetchone()
    assert tuple(row[:3]) == (1275, 850, "create_ratio_3_to_2")
    assert "unverified" in row[3]

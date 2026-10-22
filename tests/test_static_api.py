import hashlib
import http.client
import json
import subprocess
import threading
from pathlib import Path

import pytest

from mhxx_data.pipeline import DEFAULT_DATABASE
from mhxx_data.preview_server import make_server
from mhxx_data.static_api import (DEFAULT_EXPORT, GENERATOR, Writer, export_data,
                                  file_hash, json_bytes, safe_path, verify_export)


def read(path):
    return json.loads((DEFAULT_EXPORT / path).read_text())


def collect(descriptor):
    records, href = [], descriptor["href"]
    while href:
        page = read(href)
        records.extend(page["items"])
        href = page["links"]["next"]["href"] if page["links"]["next"] else None
    assert len(records) == descriptor["total"]
    return records


@pytest.fixture(scope="module")
def verified():
    if not DEFAULT_EXPORT.exists():
        pytest.fail("Run .venv/bin/python scripts/data.py export before API integration tests")
    return verify_export(DEFAULT_EXPORT)


def test_full_static_export_has_complete_catalogs_links_and_source_snapshot(verified):
    assert verified["entities"] == dict(weapon=1592, item=2450, monster=130, quest=1337,
                                       armor=656, skill=205, map=24, combining=183)
    assert sum(verified["entities"].values()) == 6577
    assert read("manifest.json")["database_sha256"] == file_hash(DEFAULT_DATABASE)
    assert verified["checked_links"] > 200000


def test_weapon_material_source_chain_and_unresolved_source_values(verified):
    weapon = read("weapons/218099.json")
    assert weapon["id"] == "weapon:site-218099"
    first_recipe = weapon["data"]["levels"][0]["recipes"][0]
    assert first_recipe["money"] == 1275
    assert first_recipe["cost_comparison"]["mhgu_stored_zenny"] == 850
    ingredient = weapon["data"]["levels"][2]["recipes"][0]["ingredients"][0]
    item = read(ingredient["item"]["href"])
    assert item["name"] == "圆盘石"
    assert len(collect(item["relations"]["gathering"])) == 91
    assert read("weapons/292565.json")["data"]["levels"][0]["affinity"] == "-45/20"
    missing = read("quests/322466.json")
    assert any(r["percentage"] is None for r in collect(missing["relations"]["rewards"]))


def test_every_item_source_is_available_beyond_first_page(verified):
    herb = read("items/189643.json")
    gathering = collect(herb["relations"]["gathering"])
    assert len(gathering) == 337
    assert len({(r["map"]["id"], r["row_anchor"]) for r in gathering}) == 337
    assert herb["relations"]["gathering"]["page_size"] == 100
    assert read("items/189643/gathering/4.json")["links"]["next"] is None


def test_monster_related_quests_include_source_encounters_and_relative_strength(verified):
    rows = collect(read("monsters/1829.json")["relations"]["quests"])
    by_id = {r["quest"]["id"]: r for r in rows}
    normal = by_id["quest:site-220240"]
    assert normal["objective"] == "斩龙1头的狩猎"
    assert normal["location"]["id"] == "map:site-2400"
    assert normal["strength"] == {"health": 12, "defense": 5, "scale": "source_relative_gauge_not_hp_or_defense_rate"}
    intrusion = by_id["quest:site-220173"]
    assert intrusion["intrusion"]
    assert {r["monster"]["name"] for r in intrusion["monsters"]} == {"跳狗龙", "鬼蛙", "斩龙"}
    assert by_id["quest:site-267299"]["strength"]["health"] is None
    assert read("manifest.json")["coverage"]["monster_quest_appearances"] == 2347


def test_weapon_branches_preserve_parent_levels_and_reverse_navigation(verified):
    parent = read("weapons/218099.json")
    first = parent["data"]["branches"][0]
    assert (first["level"], first["target"]["id"], first["target_level"]) == (2, "weapon:site-220141", 1)
    child = read(first["target"]["href"])
    assert child["data"]["parents"][0]["weapon"]["id"] == parent["id"]
    assert child["data"]["parents"][0]["level"] == 2
    assert read("manifest.json")["coverage"]["weapon_branches"] == 798


def test_map_conditions_and_unlinked_ammo_are_not_flattened_or_dropped(verified):
    map_data = read("maps/2400.json")
    nodes = collect(map_data["relations"]["nodes-1-lr"])
    assert {r["rare"] for r in nodes if r["point"] == 5} == {0, 1}
    assert next(r for r in nodes if r["point"] == 3)["percentage_sum"] == 113
    assert map_data["data"]["images"][0]["url"].startswith("https://charleslth.github.io/games/mhxx/images/map/")
    ammo = read("combining/210126.json")
    assert ammo["data"]["result"] is None
    assert (ammo["name"], ammo["data"]["amount_min"], ammo["data"]["amount_max"]) == ("LV2通常弾", 2, 4)


@pytest.mark.parametrize("path", [".", "../x", "/tmp/x", "a//b", "a/../b", "https://x", "a\\b", "x\x00y"])
def test_export_path_validation_rejects_non_relative_paths(path):
    with pytest.raises(ValueError):
        safe_path(path)


def miniature_export(root):
    writer = Writer(root, "fixture", 1)
    entity = dict(id="item:site-1", kind="item", name="Test", href="items/1.json")
    writer.write("items/1.json", {"type": "entity", **entity})
    catalog = writer.collection("catalogs/items", "catalog", "item", [entity])
    writer.write("search.json", {"items": [entity]})
    writer.write("manifest.json", {"generator": GENERATOR, "entity_counts": {"item": 1}, "catalogs": {"item": catalog}})
    (root / "integrity.json").write_bytes(json_bytes({"generator": GENERATOR, "api_version": 1, "dataset_revision": "fixture", "files": writer.files}))
    return writer


def test_integrity_check_detects_modified_and_unowned_files(tmp_path):
    miniature_export(tmp_path)
    assert verify_export(tmp_path)["status"] == "ok"
    (tmp_path / "notes.txt").write_text("User notes")
    with pytest.raises(ValueError, match="extra"):
        verify_export(tmp_path)
    with pytest.raises(ValueError, match="extra"):
        export_data(output=tmp_path, progress=lambda _: None)
    assert (tmp_path / "notes.txt").read_text() == "User notes"


def test_pagination_validation_is_independent_of_file_hashes(tmp_path):
    writer = miniature_export(tmp_path)
    for name in ("catalogs/items/1.json", "manifest.json"):
        doc = json.loads((tmp_path / name).read_text())
        if name == "manifest.json":
            doc["catalogs"]["item"]["total"] = 2
        else:
            doc["total"] = 2
        data = json_bytes(doc)
        (tmp_path / name).write_bytes(data)
        writer.files[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    (tmp_path / "integrity.json").write_bytes(json_bytes({"generator": GENERATOR, "api_version": 1,
        "dataset_revision": "fixture", "files": writer.files}))
    with pytest.raises(ValueError, match="pagination"):
        verify_export(tmp_path)


@pytest.fixture(scope="module")
def server(verified):
    server = make_server(DEFAULT_EXPORT, port=0, prefix="/games/mhxx/data-api/v1/", quiet=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_real_frontend_client_can_follow_links_from_a_pages_subdirectory(server):
    base = f"http://127.0.0.1:{server.server_port}/games/mhxx/data-api/v1/"
    result = subprocess.run(["node", str(Path(__file__).with_name("data-client.test.mjs")), base],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["gathered"] == 337


def test_preview_serves_only_exported_read_only_paths_and_supports_head_etag(server):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    path = "/games/mhxx/data-api/v1/manifest.json"
    try:
        connection.request("HEAD", path)
        response = connection.getresponse()
        assert response.status == 200
        etag = response.getheader("ETag")
        assert response.read() == b""
        connection.request("GET", path, headers={"If-None-Match": etag})
        response = connection.getresponse()
        assert response.status == 304
        response.read()
        for method, requested, status in [("POST", path, 405), ("DELETE", path, 405),
            ("GET", "/games/mhxx/data-api/v1/%2e%2e/manifest.json", 404),
            ("GET", "/games/mhxx/data-api/v1/items/", 404), ("GET", "/.git/config", 404)]:
            connection.request(method, requested)
            response = connection.getresponse()
            assert response.status == status
            response.read()
    finally:
        connection.close()

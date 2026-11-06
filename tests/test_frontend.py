import http.client
import json
import subprocess
import threading
from pathlib import Path

import pytest

from mhxx_data.frontend import DEFAULT_FRONTEND, WEB_FILES, make_frontend_server, verify_frontend
from mhxx_data.static_api import DEFAULT_EXPORT, file_hash


@pytest.fixture(scope="module")
def package():
    if not DEFAULT_FRONTEND.exists():
        pytest.fail("Run .venv/bin/python scripts/frontend.py build before frontend tests")
    return verify_frontend(DEFAULT_FRONTEND)


def test_frontend_packages_all_entities_and_current_sources(package):
    root = Path(__file__).resolve().parents[1]
    assert package["entities"] == 6577
    for name in WEB_FILES:
        assert file_hash(DEFAULT_FRONTEND / name) == file_hash(root / "web" / name)
    assert file_hash(DEFAULT_FRONTEND / "index/index.html") == file_hash(root / "web/home-redirect.html")
    assert file_hash(DEFAULT_FRONTEND / "data/v1/integrity.json") == file_hash(DEFAULT_EXPORT / "integrity.json")
    index = json.loads((DEFAULT_FRONTEND / "browse-index.json").read_text())
    search = json.loads((DEFAULT_EXPORT / "search.json").read_text())
    assert {e["id"] for e in index["items"]} == {e["id"] for e in search["items"]}
    assert index["dataset_revision"] == search["dataset_revision"]
    assert (DEFAULT_FRONTEND / "assets/images/map/kodairin.gif").is_file()


def test_search_filters_paging_and_safe_rendering_against_the_real_index(package):
    result = subprocess.run(["node", "--test", str(Path(__file__).with_name("frontend.test.mjs"))], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


def test_weapon_details_cover_all_levels_and_preserve_bowgun_availability(package):
    files = sorted((DEFAULT_FRONTEND / "weapon-details").glob("*.json"))
    assert len(files) == 1592
    level_count = bowgun_levels = 0
    for path in files:
        detail = json.loads(path.read_text())
        entity = json.loads((DEFAULT_EXPORT / "weapons" / path.name).read_text())
        assert detail["id"] == entity["id"]
        assert detail["dataset_revision"] == package["dataset_revision"]
        assert detail["source"]["sha256"] == entity["source"]["sha256"]
        assert [level["level"] for level in detail["levels"]] == [level["level"] for level in entity["data"]["levels"]]
        level_count += len(detail["levels"])
        for level in detail["levels"]:
            assert all(field["label"] != "其他性能" for field in level["fields"])
            if "ammunition" in level:
                bowgun_levels += 1
                assert len(level["ammunition"]) == len({ammo["name"] for ammo in level["ammunition"]}) == 17
                assert sum(len(ammo["loads"]) for ammo in level["ammunition"]) == 32
                assert all(int(ammo["loaded"]) <= int(ammo["carried"]) for ammo in level["internal_ammo"])
    assert (level_count, bowgun_levels) == (10911, 1421)
    diablo = json.loads((DEFAULT_FRONTEND / "weapon-details/310279.json").read_text())["levels"][4]
    assert {field["label"]: field["value"] for field in diablo["fields"]} == {
        "攻击期待值（参考）": "356", "装填速度": "缓慢", "偏移（摇晃）": "左/大", "后座力": "中"}
    ammo = {a["name"]: a["loads"] for a in diablo["ammunition"]}
    assert [load["count"] for load in ammo["贯通弹"]] == [4, 5, 5]
    assert [load["requires_skill"] for load in ammo["散弹"]] == [False, False, True]
    assert all(load["requires_skill"] for load in ammo["扩散弹"])
    assert ammo["火炎弹"] == [{"count": None, "requires_skill": False}]
    assert diablo["internal_ammo"] == [{"name": "Lv1重击弹", "carried": "15", "loaded": "3"}, {"name": "Lv2重击弹", "carried": "15", "loaded": "3"}]
    assert diablo["crouching_fire"] == ["Lv1贯通弹", "Lv2贯通弹", "Lv2通常弹"]
    light = json.loads((DEFAULT_FRONTEND / "weapon-details/219234.json").read_text())["levels"][-1]
    assert light["rapid_fire"] == [{"name": "碎石弹", "shots": "3", "recovery": "小"}]
    bow = json.loads((DEFAULT_FRONTEND / "weapon-details/219233.json").read_text())["levels"][-1]
    assert [charge["requires_skill"] for charge in bow["charges"]] == [False, False, False, True]
    assert [coating["name"] for coating in bow["coatings"] if coating["available"]] == ["Lv1 强击瓶", "Lv2 强击瓶", "接击瓶", "染色瓶", "毒瓶"]
    horn = json.loads((DEFAULT_FRONTEND / "weapon-details/219226.json").read_text())["levels"][-1]
    assert horn["melodies"][1] == {"notes": ["白", "红", "红"], "effect": "攻击力強化【小】"}


def test_monster_catalog_covers_every_size_and_keeps_raw_metadata(package):
    catalog = json.loads((DEFAULT_FRONTEND / "monster-catalog.json").read_text())
    home = json.loads((DEFAULT_FRONTEND / "home-data.json").read_text())
    entries = {e["id"]: e for e in json.loads((DEFAULT_FRONTEND / "browse-index.json").read_text())["items"] if e["kind"] == "monster"}
    records = catalog["monsters"]
    assert catalog["dataset_revision"] == package["dataset_revision"]
    assert len(records) == len(entries) == 130
    assert {r["id"] for r in records} == entries.keys()
    assert len(catalog["families"]) == 15
    assert [r["order"] for r in records] == list(range(130))
    large = [r["id"] for r in records if r["size"] == "large"]
    assert len(large) == 94
    assert len(records) - len(large) == 36
    assert large == [link["route"]["id"] for group in home["sections"]["怪物"]["groups"] for link in group["links"]]
    assert large[-1] == "monster:site-2879"  # Alatreon was missing from the old homepage.
    for record in records:
        original = json.loads((DEFAULT_EXPORT / "monsters" / (record["id"].split("-")[-1] + ".json")).read_text())
        assert record["source_kind"] == original["data"]["metadata"]["种类"]
        entry = entries[record["id"]]
        assert entry["monster_family"] == record["family"]
        assert entry["monster_order"] == record["order"]
        assert entry["monster_marker"] == record["marker"]
        assert entry["monster_size"] == record["size"]
        assert ("monster-2501" if record["size"] == "large" else "monster-2502") in entry["groups"]
    by_id = {r["id"]: r for r in records}
    for key in ("monster:site-2830", "monster:site-2990"):
        assert by_id[key]["source_kind"] == "-"
        assert by_id[key]["family"] == "elder-dragon"
        assert by_id[key]["classification_source"] == "index/index.html"
    for family in catalog["families"]:
        assert family["counts"] == {size: sum(r["family"] == family["key"] and r["size"] == size for r in records) for size in ("large", "small")}
    for source, digest in catalog["source_pages"].items():
        assert file_hash(Path(__file__).resolve().parents[1] / "games/mhxx_old" / source) == digest


def test_map_task_index_uses_exact_destination_references(package):
    entries = json.loads((DEFAULT_FRONTEND / "browse-index.json").read_text())["items"]
    quests = [entry for entry in entries if entry["kind"] == "quest"]
    map_ids = {entry["id"] for entry in entries if entry["kind"] == "map"}
    linked = 0
    for quest in quests:
        key = quest["id"].split("site-", 1)[1]
        data = json.loads((DEFAULT_EXPORT / "quests" / f"{key}.json").read_text())["data"]
        expected = {ref["target"]["id"] for ref in data["references"]
                    if ref["role"] == "目的地" and (ref.get("target") or {}).get("kind") == "map"}
        assert set(quest["map_ids"]) == expected
        assert len(quest["map_ids"]) == len(expected)
        assert expected <= map_ids
        linked += bool(expected)
    assert linked == 1329  # Eight quests have no destination page in the original site.
    assert sum("map:site-2400" in quest["map_ids"] for quest in quests) == 129


def test_quest_filters_preserve_source_flags_and_progression_membership(package):
    quests = [entry for entry in json.loads((DEFAULT_FRONTEND / "browse-index.json").read_text())["items"] if entry["kind"] == "quest"]
    for quest in quests:
        key = quest["id"].split("site-", 1)[1]
        data = json.loads((DEFAULT_EXPORT / "quests" / f"{key}.json").read_text())["data"]
        assert quest["quest_flags"] == sorted({flag for text in data["flags"] for flag in text.split()})
    flagged = {quest["id"] for quest in quests if {"关键", "紧急"} & set(quest["quest_flags"])}
    directories = {quest["id"] for quest in quests if {"quest-2859", "quest-2987"} & set(quest["groups"])}
    assert flagged == directories
    assert len(flagged) == 151


def test_homepage_preserves_source_navigation_and_resolves_internal_categories(package):
    root = Path(__file__).resolve().parents[1]
    home = json.loads((DEFAULT_FRONTEND / "home-data.json").read_text())
    entries = json.loads((DEFAULT_FRONTEND / "browse-index.json").read_text())["items"]
    ids = {entry["id"] for entry in entries}
    assert home["dataset_revision"] == package["dataset_revision"]
    assert len(home["categories"]) == 73
    assert len(home["weapon_counts"]) == 14
    assert sum(home["weapon_counts"].values()) == 1592
    assert len(home["sections"]["地图"]["links"]) == 24
    markers = {link["label"]: link.get("marker") for link in home["sections"]["怪物"]["links"]}
    assert markers["胧隐夜鸟"] == "[新]" and markers["白速龙王"] == "[再]"
    assert markers["斩龙"] is None
    assert sum(bool(m) for m in markers.values()) == 23
    assert {"猫饭", "随从猫技能", "武器操作", "交易窗口", "狩技"} <= set(home["sections"])
    for page, digest in home["source_pages"].items():
        assert file_hash(root / "games/mhxx_old" / page) == digest
    for section in home["sections"].values():
        for link in section["links"]:
            assert (root / "games/mhxx_old" / link["source_page"]).is_file()
            if "route" in link:
                if "id" in link["route"]:
                    assert link["route"]["id"] in ids
                if "group" in link["route"]:
                    category = home["categories"][link["route"]["group"]]
                    assert category["kind"] == link["route"]["kind"]
                    assert category["count"] == sum(category["key"] in e.get("groups", []) for e in entries)
            else:
                assert link["url"] == "https://charleslth.github.io/games/mhxx/" + link["source_page"]


def test_frontend_nested_http_paths_include_worker_module_data_and_local_assets(package):
    server = make_frontend_server(port=0, quiet=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    prefix = "/games/mhxx/"
    try:
        for path, mime in [("", "text/html"), ("index.html", "text/html"), ("index/", "text/html"),
                           ("index/index.html", "text/html"), ("styles.css", "text/css"), ("app.mjs", "text/javascript"),
                           ("home.mjs", "text/javascript"), ("home-data.json", "application/json"),
                           ("weapon-browser.mjs", "text/javascript"), ("weapon-catalogs/great-sword.json", "application/json"),
                           ("weapon-performance.mjs", "text/javascript"), ("weapon-details/310279.json", "application/json"),
                           ("armor-browser.mjs", "text/javascript"), ("armor-catalog.json", "application/json"),
                           ("quest-browser.mjs", "text/javascript"),
                           ("monster-browser.mjs", "text/javascript"), ("monster-catalog.json", "application/json"),
                           ("search-worker.mjs", "text/javascript"), ("browse-index.json", "application/json"),
                           ("data/v1/weapons/218099.json", "application/json"), ("assets/images/map/kodairin.gif", "image/gif")]:
            connection.request("GET", prefix + path)
            response = connection.getresponse()
            assert response.status == 200, path
            assert response.getheader("Content-Type").startswith(mime)
            assert response.read()
        connection.request("GET", prefix + "index")
        response = connection.getresponse()
        assert response.status == 302 and response.getheader("Location") == prefix + "index/"
        response.read()
        for method, path, status in [("GET", "/.git/config", 404), ("GET", prefix + "assets/", 404),
                                     ("GET", "/games/mhxx_old/", 404),
                                     ("GET", prefix + "%2e%2e/README.txt", 404), ("POST", prefix, 405)]:
            connection.request(method, path)
            response = connection.getresponse()
            assert response.status == status
            response.read()
    finally:
        connection.close()
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_weapon_catalogs_cover_every_level_branch_and_original_final_weapon(package):
    catalogs = [json.loads(p.read_text()) for p in (DEFAULT_FRONTEND / "weapon-catalogs").glob("*.json")]
    assert len(catalogs) == 14
    nodes = [n for c in catalogs for n in c["nodes"]]
    assert len(nodes) == len({n["key"] for n in nodes}) == 10911
    assert sum(n["final"] for n in nodes) == 1592
    assert sum(len(c["roots"]) for c in catalogs) == 794
    by_key = {n["key"]: n for n in nodes}
    assert sum(by_key[ch]["id"] != n["id"] for n in nodes for ch in n["children"]) == 798
    for catalog in catalogs:
        assert catalog["dataset_revision"] == package["dataset_revision"]
        for source, digest in catalog["source_pages"].items():
            assert file_hash(Path(__file__).resolve().parents[1] / "games/mhxx_old" / source) == digest
        for node in catalog["nodes"]:
            for child in node["children"]:
                assert by_key[child]["parent"] == node["key"]
                assert by_key[child]["root"] == node["root"]
    wisdom = by_key["weapon:site-218099@11"]
    assert (wisdom["attack"], wisdom["slots"], wisdom["final"]) == (320, 3, True)
    assert wisdom["sharpness_px"][0] != wisdom["sharpness_px"][2]


def test_armor_catalog_preserves_original_variants_totals_and_every_piece(package):
    catalog = json.loads((DEFAULT_FRONTEND / "armor-catalog.json").read_text())
    assert catalog["dataset_revision"] == package["dataset_revision"]
    assert len(catalog["sets"]) == len({s["id"] for s in catalog["sets"]}) == 656
    assert len(catalog["categories"]) == 12
    variants = [v for s in catalog["sets"] for v in s["variants"]]
    assert len(variants) == 1252
    assert sum(len(v["pieces"]) for v in variants) == 5685
    assert sum(v["type"] == "common" for v in variants) == 60
    for source, digest in catalog["source_pages"].items():
        assert file_hash(Path(__file__).resolve().parents[1] / "games/mhxx_old" / source) == digest
    for armor in catalog["sets"]:
        assert [v["type"] for v in armor["variants"]] in (["common"], ["blade", "gunner"])
        original = json.loads((DEFAULT_EXPORT / "armor" / (armor["id"].split("-")[-1] + ".json")).read_text())
        pieces = [p for v in armor["variants"] for p in v["pieces"]]
        assert len(pieces) == len(original["data"]["pieces"])
        for piece, source_piece in zip(pieces, original["data"]["pieces"]):
            for key in ("ordinal", "name", "slot", "defense", "max_defense", "slots"):
                assert piece[key] == source_piece[key]
            assert [(s["skill"]["id"], s["points"]) for s in piece["skills"]] == [(s["skill"]["id"], s["points"]) for s in source_piece["skills"]]
        for variant in armor["variants"]:
            for key in ("defense", "max_defense", "slots"):
                assert variant["summary"][key] == sum(p[key] for p in variant["pieces"])

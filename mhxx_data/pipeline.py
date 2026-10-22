"""Build a provenance-preserving comparison database from two pinned sources."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import urllib.request
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .html_source import extract, inventory, weapon_name
from .domains import extract_domains
from .domain_matching import compare_domains
from .domain_database import populate_domains, domain_report
from .acquisition import extract_acquisition
from .acquisition_database import (populate_acquisition, location_evidence, compare_gathering,
                                   compare_combining, acquisition_report)
from .matching import check_recipes, infer_items, match_weapons, upstream_data
from .reviews import (apply_unlinked_ingredients, apply_weapon_reviews, classify_costs,
                      validate_exclusions, validate_registry)

ROOT = Path(__file__).resolve().parents[1]
LEGACY_SITE_ROOT = ROOT / "games/mhxx_old"
DEFAULT_DATABASE = ROOT / "build/database/mhxx.sqlite"
MANIFEST = ROOT / "sources/mhgu-db.json"
ARCHIVE = ROOT / "build/sources/mhgu.db.zip"


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require_digest(data, expected, label):
    actual = digest(data)
    if actual != expected:
        raise ValueError(f"{label}: SHA-256 mismatch; expected {expected}, got {actual}")


def read_source(archive=ARCHIVE, manifest=None):
    manifest = manifest or json.loads(MANIFEST.read_text())
    require_digest(archive.read_bytes(), manifest["archive_sha256"], "Source archive")
    with zipfile.ZipFile(archive) as source:
        info = source.getinfo(manifest["database_member"])
        if info.file_size > 100 * 1024 * 1024:
            raise ValueError("Unexpected source database size")
        database = source.read(info)
    require_digest(database, manifest["database_sha256"], "Source database")
    return database


def fetch():
    manifest = json.loads(MANIFEST.read_text())
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    if ARCHIVE.exists():
        read_source()
        return ARCHIVE
    request = urllib.request.Request(manifest["archive_url"], headers={"User-Agent": "mhxx-data-audit/1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(20 * 1024 * 1024 + 1)
    require_digest(data, manifest["archive_sha256"], "Downloaded source archive")
    staging = ARCHIVE.with_suffix(".zip.part")
    staging.write_bytes(data)
    os.replace(staging, ARCHIVE)
    read_source()
    return ARCHIVE


def source_counts(connection):
    names = [r[0] for r in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return {name: connection.execute('SELECT count(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0]
            for name in names}


def site_commit(root):
    # A downloaded snapshot or a new repository has no commit yet. File hashes
    # remain the provenance record when Git history is intentionally absent.
    head = subprocess.run(["git", "rev-parse", "--verify", "HEAD"],
                          cwd=ROOT, capture_output=True, text=True)
    if head.returncode:
        return None
    result = subprocess.run(["git", "log", "-1", "--format=%H", "--", str(root)],
                            cwd=ROOT, capture_output=True, text=True, check=True)
    # Before the rename is committed, history still lives at the original path.
    if not result.stdout.strip() and Path(root).resolve() == LEGACY_SITE_ROOT:
        result = subprocess.run(["git", "log", "-1", "--format=%H", "--", "games/mhxx"],
                                cwd=ROOT, capture_output=True, text=True, check=True)
    return result.stdout.strip() or None


def recipe_key(page, recipe):
    return page, recipe["level"], recipe["kind"], recipe["locator"]


def populate(connection, pages, weapons, items, weapon_matches, item_matches, checks, differences,
             registry, value_differences, cost_reviews):
    connection.executemany("INSERT INTO site_pages VALUES (?,?,?,?)",
                           ((p["path"], p["category"], p["title"], p["sha256"]) for p in pages))
    connection.executemany("INSERT INTO site_items VALUES (?,?,?)",
                           ((page, value["name"], encode(value["basic_rows"])) for page, value in items.items()))
    for kind in ("weapon_identities", "item_constraint_exclusions", "unlinked_ingredients"):
        connection.executemany("INSERT INTO data_reviews VALUES (?,?,?,?)",
                               ((r["id"], kind, r["page"], encode(r)) for r in registry[kind]))
    recipe_ids = {}
    for weapon in weapons:
        page = weapon["page"]
        connection.execute("INSERT INTO site_weapon_lines VALUES (?,?,?,?)",
                           (page, weapon["wtype"], encode(weapon["issues"]), encode(weapon["ancestors"])))
        for level in weapon["levels"]:
            connection.execute("INSERT INTO site_weapon_levels VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                               (page, level["level"], level["name"], level["attack"], level["slots"],
                                level["affinity"], level["defense"], encode(level["elements"]),
                                encode(level["sharpness_px"]), encode(level["performance_cells"]), level["locator"]))
        for recipe in weapon["recipes"]:
            cursor = connection.execute("""INSERT INTO site_recipes
                (page,level,kind,money,unparsed_json,source_xpath,raw_text,also_seen_at_json)
                VALUES (?,?,?,?,?,?,?,?)""",
                (page, recipe["level"], recipe["kind"], recipe["money"], encode(recipe["unparsed"]),
                 recipe["locator"], recipe["raw_text"], encode(recipe["also_seen_at"])))
            rid = cursor.lastrowid
            key = recipe_key(page, recipe)
            if key in recipe_ids:
                raise ValueError(f"Unmodeled alternate recipe at {key}")
            recipe_ids[key] = rid
            connection.executemany("INSERT INTO site_recipe_items VALUES (?,?,?,?,?,?)",
                ((rid, n, i["item_page"], i["quantity"], i["label"], i["raw_text"])
                 for n, i in enumerate(recipe["ingredients"])))
            connection.executemany("INSERT INTO site_recipe_points VALUES (?,?,?,?,?)",
                ((rid, n, p["label"], p["points"], p["raw_text"])
                 for n, p in enumerate(recipe["material_points"])))
            connection.executemany("INSERT INTO reviewed_recipe_items VALUES (?,?,?,?,?)",
                ((rid, i["review_id"], i["item_page"], i["quantity"], i["raw_text"])
                 for i in recipe.get("reviewed_ingredients", [])))
    level_names = {w["page"]: {weapon_name(l["name"]): l["level"] for l in w["levels"]} for w in weapons}
    weapon_types = {w["page"]: w["wtype"] for w in weapons}
    for weapon in weapons:
        for ordinal, branch in enumerate(weapon["branches"]):
            target = branch["target_page"]
            target_level = level_names.get(target, {}).get(weapon_name(branch["label"]))
            if target_level is None or weapon_types[target] != weapon["wtype"]:
                raise ValueError(f"Unresolved source weapon branch: {weapon['page']} {branch}")
            connection.execute("INSERT INTO site_weapon_branches VALUES (?,?,?,?,?,?,?)", (
                weapon["page"], branch["level"], ordinal, target, target_level, branch["label"], branch["source_xpath"]))
    for page, match in weapon_matches.items():
        connection.execute("INSERT INTO weapon_matches VALUES (?,?,?,?)",
                           (page, match["family"], match["status"], encode(match)))
    for page, match in item_matches.items():
        connection.execute("INSERT INTO item_matches VALUES (?,?,?,?,?,?)",
            (page, match["item_id"], match["status"], match["supporting_weapon_lines"],
             encode(match["candidate_ids"]), encode(match["evidence"])))
    for check in checks:
        connection.execute("INSERT INTO recipe_checks VALUES (?,?,?)",
            (recipe_ids[recipe_key(check["page"], check)], check["weapon_id"], check["status"]))
    for diff in differences:
        connection.execute("""INSERT INTO audit_differences
            (recipe_id,weapon_id,field,site_value_json,upstream_value_json) VALUES (?,?,?,?,?)""",
            (recipe_ids[recipe_key(diff["page"], diff)], diff["weapon_id"], diff["field"],
             encode(diff["site"]), encode(diff["upstream"])))
    for diff in value_differences:
        connection.execute("INSERT INTO weapon_value_differences VALUES (?,?,?,?,?,?,?)",
            (diff["page"], diff["level"], diff["weapon_id"], diff["field"],
             encode(diff["site"]), encode(diff["upstream"]), diff["review_id"]))
    for review in cost_reviews:
        connection.execute("INSERT INTO cost_reviews VALUES (?,?,?,?)",
            (recipe_ids[recipe_key(review["page"], review)], review["pattern"],
             review["site_marks_xx"], review["resolution"]))


def check_database(connection):
    integrity = [r[0] for r in connection.execute("PRAGMA integrity_check")]
    if integrity != ["ok"]:
        raise ValueError(f"Database integrity errors: {integrity[:5]}")
    # Upstream declares two foreign keys against misspelled table names and
    # uses 0 for quests without a permit monster. Preserve, document and pin
    # those pre-existing violations; any change/additional violation is fatal.
    foreign = sorted(tuple(r) for r in connection.execute("PRAGMA foreign_key_check"))
    baseline = json.loads(connection.execute(
        "SELECT value_json FROM source_manifest WHERE key='upstream_foreign_keys'").fetchone()[0])
    if digest(encode(foreign).encode()) != baseline["violations_sha256"]:
        raise ValueError(f"Foreign key violations differ from the imported baseline: {foreign[:5]}")
    references = {
        "weapon_item": "SELECT count(*) FROM weapons w LEFT JOIN items i ON i._id=w._id WHERE i._id IS NULL",
        "weapon_parent": "SELECT count(*) FROM weapons w LEFT JOIN weapons p ON p._id=w.parent_id WHERE w.parent_id<>0 AND p._id IS NULL",
        "component_item": "SELECT count(*) FROM components c LEFT JOIN items i ON i._id=c.component_item_id LEFT JOIN items o ON o._id=c.created_item_id WHERE i._id IS NULL OR o._id IS NULL",
        "gathering_item_location": "SELECT count(*) FROM gathering g LEFT JOIN items i ON i._id=g.item_id LEFT JOIN locations l ON l._id=g.location_id WHERE i._id IS NULL OR l._id IS NULL",
        "hunting_item_monster": "SELECT count(*) FROM hunting_rewards r LEFT JOIN items i ON i._id=r.item_id LEFT JOIN monsters m ON m._id=r.monster_id WHERE i._id IS NULL OR m._id IS NULL",
        "quest_reward": "SELECT count(*) FROM quest_rewards r LEFT JOIN items i ON i._id=r.item_id LEFT JOIN quests q ON q._id=r.quest_id WHERE i._id IS NULL OR q._id IS NULL",
        "material_pool": "SELECT count(*) FROM item_to_material m LEFT JOIN items i ON i._id=m.item_id LEFT JOIN items p ON p._id=m.material_item_id WHERE i._id IS NULL OR p._id IS NULL",
        "skill_tree": "SELECT count(*) FROM skills s LEFT JOIN skill_trees t ON t._id=s.skill_tree_id WHERE t._id IS NULL",
        "meow_location": "SELECT count(*) FROM meow_rewards r LEFT JOIN meow_locations l ON l._id=r.meow_location_id WHERE l._id IS NULL",
        "permit_monster": "SELECT count(*) FROM quests q LEFT JOIN monsters m ON m._id=q.permit_monster_id WHERE q.permit_monster_id<>0 AND m._id IS NULL",
        "domain_monster": "SELECT count(*) FROM domain_matches d LEFT JOIN monsters m ON m._id=d.upstream_id WHERE d.kind='monster' AND d.upstream_id IS NOT NULL AND m._id IS NULL",
        "domain_quest": "SELECT count(*) FROM domain_matches d LEFT JOIN quests q ON q._id=d.upstream_id WHERE d.kind='quest' AND d.upstream_id IS NOT NULL AND q._id IS NULL",
        "domain_armor": "SELECT count(*) FROM domain_matches d LEFT JOIN armor a ON a._id=d.upstream_id WHERE d.kind='armor' AND d.upstream_id IS NOT NULL AND a._id IS NULL",
        "combining_input_slots": "SELECT count(*) FROM site_combining c WHERE (SELECT count(*) FROM site_combining_inputs i WHERE i.recipe_id=c.id)<>2",
        "empty_map_sections": "SELECT count(*) FROM site_map_sections s WHERE s.empty_text IS NOT NULL AND EXISTS (SELECT 1 FROM site_gathering_nodes n WHERE n.section_id=s.id)",
        "gathering_checks": "SELECT count(*) FROM site_gathering g LEFT JOIN gathering_checks c ON c.gathering_id=g.id WHERE c.gathering_id IS NULL",
    }
    orphan_counts = {key: connection.execute(sql).fetchone()[0] for key, sql in references.items()}
    if any(orphan_counts.values()):
        raise ValueError(f"Unresolved upstream relations: {orphan_counts}")
    return {"integrity": "ok", "new_foreign_key_errors": 0,
            "preserved_upstream_foreign_key_violations": baseline, "orphan_counts": orphan_counts}


def make_report(pages, weapons, items, counters, upstream_counts, matches, item_matches, checks, differences):
    return {
        "site": {"html_pages": len(pages), "item_pages": len(items), "weapon_lines": len(weapons),
                 "weapon_levels": sum(len(w["levels"]) for w in weapons),
                 "recipes": sum(len(w["recipes"]) for w in weapons), **counters},
        "upstream_tables": upstream_counts,
        "weapon_match_status": dict(Counter(v["status"] for v in matches.values())),
        "item_match_status": dict(Counter(v["status"] for v in item_matches.values())),
        "items_without_recipe_evidence": len(items) - len(item_matches),
        "recipe_checks": dict(Counter(v["status"] for v in checks)),
        "difference_fields": dict(Counter(v["field"] for v in differences)),
        "cost_ratio_patterns": {field: Counter(
            str(round(d["site"] / d["upstream"], 3)) if d["upstream"] else "upstream_zero"
            for d in differences if d["field"] == field).most_common(12)
            for field in ("creation_cost", "upgrade_cost")},
        "unresolved_weapon_lines": [{"page": w["page"], "name": w["levels"][0]["name"],
                                      **matches[w["page"]]} for w in weapons if matches[w["page"]]["family"] is None],
        "parse_issues": [{"page": w["page"], "issues": w["issues"]} for w in weapons if w["issues"]],
        "unparsed_recipe_fragments": [{"page": w["page"], "level": r["level"], "kind": r["kind"],
                                      "locator": r["locator"], "text": r["unparsed"]}
                                     for w in weapons for r in w["recipes"] if r["unparsed"]],
        "item_conflicts": [{"page": p, **v} for p, v in item_matches.items() if v["status"] in ("conflict", "non_bijective")],
        "limitations": [
            "Mappings are automatically inferred candidates, not native game IDs or human-verified identities.",
            "Recipe support checks physical ingredients only, excluding the weapon line under review from item evidence.",
            "Material points, parent branches, sharpness, bowgun data and special weapon mechanics are not equivalence-checked.",
            "MHXX and MHGU may differ. Cost discrepancies are retained, never automatically corrected.",
            "Local monster/quest rewards, armor and skills are extracted; see domains for exact coverage and limitations.",
            "Upstream rewards/quests/armor are imported MHGU data, not a verified MHXX replacement.",
        ],
    }


def report_text(report):
    site = report["site"]
    wm, im = report["weapon_match_status"], report["item_match_status"]
    return "\n".join([
        "MHXX / MHGU 数据导入与核对报告（第四阶段：地图采集与调合）",
        f"生成时间：{report['provenance']['built_at_utc']}",
        "",
        f"本地 HTML：{site['html_pages']} 页；脚本字面量填充值：{site['placeholders_restored']} 个。",
        f"已抽取：{site['weapon_lines']} 条武器路线、{site['weapon_levels']} 个等级、{site['recipes']} 份配方、{site['item_pages']} 页道具基本信息。",
        f"武器候选状态：{encode(wm)}",
        f"素材候选状态：{encode(im)}",
        f"独立材料核对：{encode(report['recipe_checks'])}",
        f"原始数值差异：{encode(report['difference_fields'])}",
        f"已复核身份：{report['reviews']['weapon_identity_count']}条；性能差异字段：{report['reviews']['performance_difference_count']}条。",
        f"费用差异分类：{encode(report['reviews']['cost_patterns'])}",
        "",
        "这些对应关系是自动推断的候选，不是人工确认的翻译或游戏原生 ID。",
        "材料复核排除了当前武器路线本身的证据；每种素材还须由至少两条其他路线共同支持。",
        "基础性能匹配不包含斩味、弹药、瓶、旋律等特殊属性；配方复核只比较实物素材。",
        "素材点数与实物个数分开保存；前置武器与端材不会计为实物素材。",
        "",
        "已跑通查询：贝鲁纳大剑 LV3 → 圆盘石×2、矿石素材6点 → MHGU 素材出处。",
        "费用差异示例：贝鲁纳大剑 LV1 网站生产价1275z，上游 creation_cost=850；两者均保留。",
        "上游 Android 界面直接显示数据库费用，不包含额外乘数；Kiranico的MHXX/MHGU样例价格相同。",
        "1.5倍、2倍只是已观察到的数值关系。尚无游戏实测支持全局修正或将差异归因于地区版本。",
        "站点显示策略：保留本地 MHXX 价格，同时保留上游价及争议状态；不自动套用乘数。",
        "",
        f"SQLite 完整性：{report['validation']['integrity']}；新增外键错误：0。",
        f"原数据库保留{report['validation']['preserved_upstream_foreign_key_violations']['count']}条既有外键声明违例：技能/喵猎奖励指向单数表名，任务无许可怪物时使用0。",
        "按实际表名和0的空值约定，已检查的关键关联无悬空记录；详见audit.json的validation。",
        "",
        f"仍无对应：{wm.get('unmatched', 0)}条路线；歧义路线：{wm.get('ambiguous', 0)}条。",
        "原先两处无链接材料已加入带证据注释，原文仍保留；轰龙牙/爪冲突已定位到单份配方。",
        "轰龙牙身份由其他路线支持，争议配方不再参与身份推断，但其配方差异继续显示。",
        f"本地新增实体页：{encode(report['domains']['pages'])}。",
        f"本地奖励条目：{encode(report['domains']['rewards'])}；防具单件：{report['domains']['armor_pieces']}；防具配方：{report['domains']['armor_recipes']}。",
        f"新增候选对应：{encode(report['domains']['match_status'])}。",
        "任务/怪物候选只核对已映射素材的奖励投影，不代表整张奖励表、条件译名及奖励栏已一致。",
        "未填写概率、无道具链接及条件分组均保留；肉质条件数值不强行转换为单个数字。",
        f"本地地图：{report['acquisition']['map_pages']}页、{report['acquisition']['map_sections']}张分区/难度表、{report['acquisition']['gathering_rows']}条采集记录。",
        f"本地调合：{report['acquisition']['combining_recipes']}份配方；候选状态：{encode(report['acquisition']['combining_match_status'])}。",
        f"{len(report['acquisition']['gathering_probability_sums_not_100'])}组采集概率之和不为100；原站说明概率为参考值，原数值保留，不归一化。",
        "所有费用差异保存在differences.json及audit_differences表中，没有自动覆盖任一来源。",
        "详细来源、覆盖率、待处理清单：audit.json。使用与表结构说明：docs/data-pipeline.txt。",
        "",
    ])


def build(database=DEFAULT_DATABASE, site_root=None, progress=print):
    site_root = Path(site_root or LEGACY_SITE_ROOT)
    upstream = read_source()
    progress("Inventory and decode local HTML…")
    pages = inventory(site_root)
    weapons, items, counters = extract(site_root, pages)
    progress("Extract local monsters, quests, armor and skills…")
    domains = extract_domains(site_root, pages)
    progress("Extract map gathering and combining catalogs…")
    acquisition = extract_acquisition(site_root, pages)
    database.parent.mkdir(parents=True, exist_ok=True)
    staging = database.with_suffix(".sqlite.staging")
    staging.write_bytes(upstream)
    connection = sqlite3.connect(staging)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        original_counts = source_counts(connection)
        original_foreign = sorted(tuple(r) for r in connection.execute("PRAGMA foreign_key_check"))
        families, upstream_weapons, recipes = upstream_data(connection)
        progress("Match weapon profiles and cross-check ingredient evidence…")
        matches = match_weapons(weapons, families)
        source_manifest = json.loads(MANIFEST.read_text())
        registry_path = ROOT / "sources/reviews.json"
        registry = json.loads(registry_path.read_text())
        validate_registry(registry, pages, source_manifest["database_sha256"])
        validate_exclusions(weapons, registry, recipes, matches)
        exclusions = registry["item_constraint_exclusions"]
        baseline_items = infer_items(weapons, matches, recipes, exclusions)
        apply_unlinked_ingredients(weapons, registry, baseline_items, matches, recipes)
        value_differences = apply_weapon_reviews(weapons, registry, matches, families, baseline_items, recipes)
        item_matches = infer_items(weapons, matches, recipes, exclusions)
        checks, differences = check_recipes(weapons, matches, item_matches, upstream_weapons, recipes)
        cost_reviews = classify_costs(weapons, differences, recipes)
        progress("Compare local domain candidates using independent material evidence…")
        domain_matches = compare_domains(connection, domains, item_matches)
        connection.executescript((ROOT / "mhxx_data/schema.sql").read_text())
        connection.executescript((ROOT / "mhxx_data/domain-schema.sql").read_text())
        connection.executescript((ROOT / "mhxx_data/acquisition-schema.sql").read_text())
        populate(connection, pages, weapons, items, matches, item_matches, checks, differences,
                 registry, value_differences, cost_reviews)
        populate_domains(connection, domains, domain_matches)
        populate_acquisition(connection, acquisition)
        progress("Compare map destinations, gathering rows and combining candidates…")
        location_evidence(connection)
        compare_gathering(connection)
        compare_combining(connection)
        report = make_report(pages, weapons, items, counters, original_counts, matches, item_matches, checks, differences)
        report["domains"] = domain_report(domains, domain_matches)
        report["acquisition"] = acquisition_report(connection, acquisition)
        report["reviews"] = {
            "weapon_identity_count": len(registry["weapon_identities"]),
            "identity_reasons": dict(Counter(r["reason"] for r in registry["weapon_identities"])),
            "annotated_unlinked_ingredients": len(registry["unlinked_ingredients"]),
            "excluded_identity_constraints": len(exclusions),
            "performance_difference_count": len(value_differences),
            "performance_differences": value_differences,
            "cost_patterns": dict(Counter(r["pattern"] for r in cost_reviews)),
            "matched_upstream_families": len({m["family"] for m in matches.values() if m["family"] is not None}),
            "total_upstream_families": len(families),
            "research_notes": json.loads((ROOT / "sources/research-notes.json").read_text()),
        }
        manifest = {
            "schema_version": 6,
            "built_at_utc": datetime.now(timezone.utc).isoformat(),
            "upstream": source_manifest,
            "review_registry_sha256": digest(registry_path.read_bytes()),
            "research_notes_sha256": digest((ROOT / "sources/research-notes.json").read_bytes()),
            "site": {"repository": "https://github.com/CharlesLTH/CharlesLTH.github.io",
                     "path": os.path.relpath(site_root, ROOT), "original_path": "games/mhxx",
                     "commit": site_commit(site_root),
                     "inventory_sha256": digest(encode(pages).encode()),
                     "note": "Per-page hashes identify actual working-tree inputs, including local edits."},
            "pipeline_sha256": digest(b"".join(p.name.encode() + p.read_bytes() for p in
                sorted((ROOT / "mhxx_data").glob("*")) if p.is_file())),
            "original_table_counts": original_counts,
            "upstream_foreign_keys": {
                "count": len(original_foreign),
                "violations_sha256": digest(encode(original_foreign).encode()),
                "groups": dict(Counter(f"{r[0]} -> {r[2]} (key {r[3]})" for r in original_foreign)),
            },
        }
        for key, value in manifest.items():
            connection.execute("INSERT INTO source_manifest VALUES (?,?)", (key, encode(value)))
        report["validation"] = check_database(connection)
        report["provenance"] = manifest
        connection.execute("INSERT INTO source_manifest VALUES (?,?)", ("audit_summary", encode(report)))
        connection.commit()
    finally:
        connection.close()
    os.replace(staging, database)
    report_path = database.parent / "audit.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    differences_path = database.parent / "differences.json"
    differences_path.write_text(json.dumps(differences, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (database.parent / "performance-differences.json").write_text(
        json.dumps(value_differences, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (database.parent / "audit.txt").write_text(report_text(report), encoding="utf-8")
    return report

"""Versioned static JSON API: deterministic export, complete pagination, verification."""

import hashlib
import json
import math
import os
import shutil
import tempfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

from .pipeline import ROOT, DEFAULT_DATABASE, check_database
from .public_data import KINDS, PublicData, select
from .query import connect

DEFAULT_EXPORT = ROOT / "build/site-data/v1"
GENERATOR = "mhxx-static-api"
VERSION = 1


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_path(path):
    p = PurePosixPath(path)
    if not path or path == "." or p.is_absolute() or str(p) != path or any(part in (".", "..") for part in p.parts) or "\\" in path or ":" in path or any(ord(c) < 32 for c in path):
        raise ValueError(f"Unsafe API path: {path}")
    return p


def walk(value):
    if isinstance(value, dict):
        yield value
        for v in value.values():
            yield from walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from walk(v)


class Writer:
    def __init__(self, root, revision, page_size):
        self.root, self.revision, self.page_size = root, revision, page_size
        self.files = {}

    def write(self, path, value=None, raw=None):
        safe_path(path)
        if path in self.files:
            raise ValueError(f"Duplicate API path: {path}")
        if raw is None:
            raw = json_bytes({"api_version": VERSION, "dataset_revision": self.revision, **value})
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        self.files[path] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}

    def collection(self, base, owner, relation, records):
        count = len(records)
        descriptor = {"type": "collection", "total": count, "page_size": self.page_size,
                      "href": f"{base}/1.json" if count else None}
        pages = math.ceil(count / self.page_size)
        for n in range(1, pages + 1):
            self.write(f"{base}/{n}.json", {
                "type": "collection_page", "owner": owner, "relation": relation,
                "total": count, "page": n, "page_size": self.page_size,
                "items": records[(n - 1) * self.page_size:n * self.page_size],
                "links": {"next": {"href": f"{base}/{n + 1}.json"} if n < pages else None,
                          "previous": {"href": f"{base}/{n - 1}.json"} if n > 1 else None}})
        return descriptor


def verify_export(root):
    root = Path(root).resolve()
    inventory = json.loads((root / "integrity.json").read_text())
    if inventory.get("generator") != GENERATOR or inventory.get("api_version") != VERSION:
        raise ValueError("Not a supported MHXX static export")
    files = inventory["files"]
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if any(p.is_symlink() for p in root.rglob("*")) or actual != set(files) | {"integrity.json"}:
        raise ValueError("Export contains missing, extra or symbolic-link files")
    documents = {}
    for path, expected in files.items():
        safe_path(path)
        target = root / path
        if target.stat().st_size != expected["bytes"] or file_hash(target) != expected["sha256"]:
            raise ValueError(f"Export digest mismatch: {path}")
        if path.endswith(".json"):
            doc = json.loads(target.read_text())
            if doc.get("api_version") != VERSION or doc.get("dataset_revision") != inventory["dataset_revision"]:
                raise ValueError(f"Mixed API versions/revisions: {path}")
            documents[path] = doc
    manifest = documents["manifest.json"]
    if manifest.get("generator") != GENERATOR:
        raise ValueError("Wrong export generator")
    entities, groups = {}, defaultdict(list)
    links = 0
    for path, doc in documents.items():
        if doc.get("type") == "entity":
            if doc["id"] in entities or doc["href"] != path:
                raise ValueError(f"Duplicate or invalid entity: {path}")
            entities[doc["id"]] = doc
        if doc.get("type") == "collection_page":
            groups[doc["owner"], doc["relation"]].append((path, doc))
        for value in walk(doc):
            href = value.get("href")
            if href is not None:
                safe_path(href)
                if href not in files and href != "integrity.json":
                    raise ValueError(f"Broken API link from {path}: {href}")
                links += 1
                if value.get("id") and documents[href].get("id") != value["id"]:
                    raise ValueError(f"Entity reference disagrees with target: {href}")
            if value.get("type") == "collection":
                if value["total"] == 0:
                    if href is not None:
                        raise ValueError("Empty collection unexpectedly has a page")
                elif href is None or documents[href]["page"] != 1 or documents[href]["total"] != value["total"]:
                    raise ValueError("Collection descriptor does not match its first page")
    for group in groups.values():
        group.sort(key=lambda pair: pair[1]["page"])
        first = group[0][1]
        size, total = first["page_size"], first["total"]
        if size < 1 or len(group) != math.ceil(total / size):
            raise ValueError("Incomplete collection pagination")
        for n, (path, doc) in enumerate(group, 1):
            if (doc["page"], doc["page_size"], doc["total"]) != (n, size, total):
                raise ValueError("Inconsistent collection pagination")
            if len(doc["items"]) != min(size, total - (n - 1) * size):
                raise ValueError("Truncated collection page")
            expected_next = {"href": group[n][0]} if n < len(group) else None
            expected_previous = {"href": group[n - 2][0]} if n > 1 else None
            if doc["links"] != {"next": expected_next, "previous": expected_previous}:
                raise ValueError("Invalid collection navigation")
    counts = dict(Counter(e["kind"] for e in entities.values()))
    if counts != manifest["entity_counts"]:
        raise ValueError("Entity counts do not match manifest")
    for kind, descriptor in manifest["catalogs"].items():
        catalog_ids = [r["id"] for _, doc in groups[("catalog", kind)] for r in doc["items"]]
        expected = {k for k, e in entities.items() if e["kind"] == kind}
        if len(catalog_ids) != len(set(catalog_ids)) or set(catalog_ids) != expected or descriptor["total"] != len(expected):
            raise ValueError(f"Catalog coverage mismatch: {kind}")
    search_ids = [r["id"] for r in documents["search.json"]["items"]]
    if len(search_ids) != len(set(search_ids)) or set(search_ids) != set(entities):
        raise ValueError("Search coverage mismatch")
    if "coverage" in manifest:
        grouped_entities = {kind: [e for e in entities.values() if e["kind"] == kind] for kind in KINDS}
        coverage = {
            "weapon_levels": sum(len(e["data"]["levels"]) for e in grouped_entities["weapon"]),
            "weapon_recipes": sum(len(l["recipes"]) for e in grouped_entities["weapon"] for l in e["data"]["levels"]),
            "armor_pieces": sum(len(e["data"]["pieces"]) for e in grouped_entities["armor"]),
            "armor_recipes": sum(len(e["data"]["recipes"]) for e in grouped_entities["armor"]),
            "hitzones": sum(len(e["data"]["hitzones"]) for e in grouped_entities["monster"]),
            "monster_rewards": sum(e["relations"]["rewards"]["total"] for e in grouped_entities["monster"]),
            "quest_rewards": sum(e["relations"]["rewards"]["total"] for e in grouped_entities["quest"]),
            "skill_activations": sum(len(e["data"]["activations"]) for e in grouped_entities["skill"]),
            "combining_inputs": sum(len(e["data"]["inputs"]) for e in grouped_entities["combining"]),
            "gathering_rows": sum(len(n["items"]) for (owner, _), group in groups.items()
                                  if owner.startswith("map:") for _, doc in group for n in doc["items"]),
        }
        if "monster_quest_appearances" in manifest["coverage"]:
            coverage["monster_quest_appearances"] = sum(
                "source_page" in r for (owner, name), group in groups.items()
                if owner.startswith("monster:") and name == "quests" for _, doc in group for r in doc["items"])
        if "weapon_branches" in manifest["coverage"]:
            coverage["weapon_branches"] = sum(len(e["data"]["branches"]) for e in grouped_entities["weapon"])
        if coverage != manifest["coverage"]:
            raise ValueError(f"Source record coverage mismatch: {coverage}")
    return {"api_version": VERSION, "dataset_revision": inventory["dataset_revision"], "files": len(actual),
            "bytes": sum(r["bytes"] for r in files.values()) + (root / "integrity.json").stat().st_size,
            "entities": counts, "collections": len(groups), "checked_links": links,
            "max_file_bytes": max((root / "integrity.json").stat().st_size, max(r["bytes"] for r in files.values())), "status": "ok"}


def export_data(database=DEFAULT_DATABASE, output=DEFAULT_EXPORT, page_size=100, progress=print):
    database, output = Path(database).resolve(), Path(output).absolute()
    if not 1 <= page_size <= 200:
        raise ValueError("Export page size must be between 1 and 200")
    if output.is_symlink():
        raise ValueError("Refusing to replace a symbolic-link export directory")
    if output.exists():
        verify_export(output)  # refuse to delete user files or incomplete/unrelated output
    output.parent.mkdir(parents=True, exist_ok=True)
    database_digest = file_hash(database)
    code_digest = hashlib.sha256(b"".join(p.name.encode() + p.read_bytes() for p in (
        ROOT / "mhxx_data/public_data.py", ROOT / "mhxx_data/static_api.py", ROOT / "web/data-client.mjs"))).hexdigest()
    revision = hashlib.sha256(json_bytes({"database": database_digest, "exporter": code_digest, "page_size": page_size})).hexdigest()
    progress("Read and validate the audit database without modifying it…")
    with connect(database) as connection:
        connection.execute("BEGIN")
        schema = json.loads(connection.execute("SELECT value_json FROM source_manifest WHERE key='schema_version'").fetchone()[0])
        if schema != 6:
            raise ValueError("Static API v1 requires audit schema 6; rebuild the database first")
        check_database(connection)
        source = {r[0]: json.loads(r[1]) for r in connection.execute(
            "SELECT key,value_json FROM source_manifest WHERE key IN ('site','upstream','pipeline_sha256')")}
        model = PublicData(connection).build()
        coverage = {key: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for key, table in {
            "weapon_levels": "site_weapon_levels", "weapon_recipes": "site_recipes", "armor_pieces": "site_armor_pieces",
            "weapon_branches": "site_weapon_branches",
            "armor_recipes": "site_armor_recipes", "hitzones": "site_monster_hitzones", "skill_activations": "site_skill_activations",
            "monster_quest_appearances": "site_monster_quests",
            "combining_inputs": "site_combining_inputs", "gathering_rows": "site_gathering"}.items()}
        for kind in ("monster", "quest"):
            coverage[kind + "_rewards"] = connection.execute("""SELECT count(*) FROM site_rewards r
                JOIN site_domain_pages d ON d.page=r.page WHERE d.kind=?""", (kind,)).fetchone()[0]
    if file_hash(database) != database_digest:
        raise ValueError("Database changed during export; retry against a stable snapshot")
    progress("Write complete entity records, catalogs and paginated relationships…")
    # A private task-owned staging directory makes failed exports leave the last
    # verified output intact. Existing output is replaced only after verification.
    with tempfile.TemporaryDirectory(prefix="mhxx-api-", dir=output.parent) as temp:
        staging = Path(temp) / "new"
        staging.mkdir()
        writer = Writer(staging, revision, page_size)
        catalogs = {}
        for entity in sorted(model.entities.values(), key=lambda e: e["id"]):
            base = entity["href"].removesuffix(".json")
            for name, records in sorted(model.relations[entity["id"]].items()):
                entity["relations"][name] = writer.collection(f"{base}/{name}", entity["id"], name, records)
            writer.write(entity["href"], {"type": "entity", **entity})
        for kind, directory in KINDS.items():
            records = [select(e, "id", "kind", "name", "href", "aliases")
                       for e in sorted(model.entities.values(), key=lambda e: e["id"]) if e["kind"] == kind]
            catalogs[kind] = writer.collection(f"catalogs/{directory}", "catalog", kind, records)
        writer.write("search.json", {"type": "search_index", "items": model.search_records()})
        writer.write("client.mjs", raw=(ROOT / "web/data-client.mjs").read_bytes())
        writer.write("licenses/mhgu-database.txt", raw=(ROOT / "third-party/mhgu-database/LICENSE.txt").read_bytes())
        writer.write("manifest.json", {"generator": GENERATOR, "type": "manifest", "page_size": page_size,
            "coverage": coverage,
            "entity_counts": dict(Counter(e["kind"] for e in model.entities.values())),
            "catalogs": catalogs, "search": {"href": "search.json"}, "client": {"href": "client.mjs"},
            "integrity": {"href": "integrity.json"}, "database_sha256": database_digest, "exporter_sha256": code_digest,
            "sources": source, "license": {"href": "licenses/mhgu-database.txt"},
            "policy": {"values": "local_mhxx_observations", "mhgu": "candidate_comparisons_only",
                "ids": "typed_site_source_keys_not_native_game_ids", "hrefs": "relative_to_api_root",
                "unknown_values": "null", "gathering_probabilities": "approximate_source_values_not_normalized",
                "coverage": "core structured data; auxiliary raw tables, shops, trade and Palico equipment remain in source/audit data"}})
        (staging / "integrity.json").write_bytes(json_bytes({"generator": GENERATOR, "api_version": VERSION,
            "dataset_revision": revision, "files": writer.files}))
        progress("Verify every digest, entity reference, catalog and pagination chain…")
        report = verify_export(staging)
        backup = Path(temp) / "previous"
        if output.exists():
            verify_export(output)  # fail safely if another process added files meanwhile
            os.replace(output, backup)
        try:
            os.replace(staging, output)
        except BaseException:
            if backup.exists():
                os.replace(backup, output)
            raise
        # Only the already verified previous generated output is removed.
        if backup.exists():
            shutil.rmtree(backup)
    return {**report, "output": str(output)}

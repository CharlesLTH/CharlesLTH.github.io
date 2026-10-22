"""Build and preview the dependency-free MHXX reference frontend."""

import hashlib
import json
import mimetypes
import shutil
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .pipeline import LEGACY_SITE_ROOT, ROOT
from .homepage import build_homepage
from .weapon_catalog import build_weapon_catalogs
from .armor_catalog import build_armor_catalog
from .static_api import DEFAULT_EXPORT, file_hash, json_bytes, safe_path, verify_export

DEFAULT_FRONTEND = ROOT / "games/mhxx"
WEB_FILES = ("index.html", "styles.css", "favicon.svg", "app.mjs", "home.mjs", "weapon-browser.mjs", "armor-browser.mjs", "quest-browser.mjs", "ui.mjs", "search-core.mjs", "search-worker.mjs", "data-client.mjs")
WEAPON_TYPES = dict(zip(
    ["Great Sword", "Long Sword", "Sword and Shield", "Dual Blades", "Hammer", "Hunting Horn", "Lance", "Gunlance", "Switch Axe", "Charge Blade", "Insect Glaive", "Light Bowgun", "Heavy Bowgun", "Bow"],
    ["大剑", "太刀", "片手剑", "双剑", "大锤", "狩猎笛", "长枪", "铳枪", "斩斧", "盾斧", "操虫棍", "轻弩", "重弩", "弓"]))


def browse_entry(entity):
    entry = {key: entity[key] for key in ("id", "kind", "name", "aliases")}
    data, kind = entity["data"], entity["kind"]
    if kind == "weapon":
        levels = data["levels"]
        entry.update(weapon_type=data["weapon_type"], subtitle=WEAPON_TYPES.get(data["weapon_type"], data["weapon_type"]),
                     attack_min=min(l["attack"] for l in levels if l["attack"] is not None),
                     attack_max=max(l["attack"] for l in levels if l["attack"] is not None),
                     level_count=len(levels), sharpness=(levels[-1]["sharpness_px"] or [None])[0])
    elif kind == "item":
        entry.update(subtitle="道具与素材", summary=f"{entity['relations']['gathering']['total']} 条采集记录",
                     extra=f"{entity['relations']['rewards']['total']} 条奖励记录")
    elif kind == "monster":
        entry.update(subtitle=data["metadata"].get("种类", "怪物"), summary=f"{len(data['hitzones'])} 条肉质记录", extra=data["metadata"].get("素材名", ""))
    elif kind == "quest":
        category = data["metadata"]["breadcrumb"][-1]
        hub = next((key for prefix, key in (("村任务", "village"), ("集会所任务", "guild"),
            ("特殊许可", "permit"), ("斗技大会", "arena"), ("挑战任务", "challenge"), ("配信任务", "event"))
            if category.startswith(prefix)), None)
        if hub is None:
            raise ValueError(f"Unknown quest category: {category}")
        objective = data["objective"]
        summary = objective or "目标未记载"
        # Generic multi-monster objectives need the source's concrete lineup.
        # Other monster references can include incidental creatures or intruders;
        # retain the explicit objective for named hunts and gathering quests.
        if objective == "全部的大型怪物的狩猎" or not objective:
            monsters = list(dict.fromkeys(ref["label"] for ref in data["references"]
                if ref["role"] == "怪物" and (ref.get("target") or {}).get("kind") == "monster"))
            if monsters:
                summary += f"（{'、'.join(monsters)}）" if objective else f"；出现怪物：{'、'.join(monsters)}"
        entry.update(subtitle=data["quest_type"] or "任务", summary=summary,
                     quest_hub=hub, quest_flags=sorted({flag for text in data["flags"] for flag in text.split()}),
                     extra=" · ".join(value for value in [data["destination_text"], *data["flags"]] if value),
                     map_ids=sorted({ref["target"]["id"] for ref in data["references"]
                         if ref["role"] == "目的地" and (ref.get("target") or {}).get("kind") == "map"}))
    elif kind == "armor":
        entry.update(subtitle=data["metadata"].get("性別", "防具套装"), summary=f"{len(data['pieces'])} 件防具", extra=f"稀有度 {data['metadata'].get('稀有度', '—')}")
    elif kind == "skill":
        entry.update(subtitle="技能系统", summary=f"{len(data['activations'])} 项发动效果", extra=" / ".join(str(a["points"]) for a in data["activations"]))
    elif kind == "map":
        entry.update(subtitle="采集地图", summary=f"{len(set(s['area'] for s in data['sections']))} 个区域", extra="下位 / 上位 / G 位")
    elif kind == "combining":
        entry.update(subtitle=data["category"], summary=" + ".join(i["label"] for i in data["inputs"]), extra=f"成功率 {data['percentage']}%" if data["percentage"] is not None else "成功率未记载")
    return entry


def verify_frontend(output=DEFAULT_FRONTEND):
    output = Path(output).resolve()
    manifest = json.loads((output / "frontend-manifest.json").read_text())
    if manifest.get("generator") != "mhxx-frontend":
        raise ValueError("Not an MHXX frontend package")
    actual = {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}
    if actual != set(manifest["files"]) | {"frontend-manifest.json"} or any(p.is_symlink() for p in output.rglob("*")):
        raise ValueError("Frontend contains missing, extra or symbolic-link files")
    for path, digest in manifest["files"].items():
        safe_path(path)
        if file_hash(output / path) != digest:
            raise ValueError(f"Frontend digest mismatch: {path}")
    return manifest


def build_frontend(output=DEFAULT_FRONTEND, source=DEFAULT_EXPORT, progress=print):
    output, source = Path(output).absolute(), Path(source).resolve()
    if output.is_symlink():
        raise ValueError("Refusing a symbolic-link output directory")
    if output.exists():
        verify_frontend(output)
    progress("Verify source API and build the complete browser index…")
    report = verify_export(source)
    search = json.loads((source / "search.json").read_text())
    entities = [json.loads((source / row["href"]).read_text()) for row in search["items"]]
    entries = [browse_entry(entity) for entity in entities]
    homepage = build_homepage(LEGACY_SITE_ROOT, entities, entries, report["dataset_revision"])
    weapon_catalogs = build_weapon_catalogs(LEGACY_SITE_ROOT, entities, report["dataset_revision"])
    armor_catalog = build_armor_catalog(LEGACY_SITE_ROOT, entities, homepage, report["dataset_revision"])
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mhxx-frontend-", dir=output.parent) as temp:
        staging = Path(temp) / "new"
        staging.mkdir()
        for name in WEB_FILES:
            shutil.copy2(ROOT / "web" / name, staging / name)
        # Preserve the previous homepage address without linking to the archive.
        (staging / "index").mkdir()
        shutil.copy2(ROOT / "web/home-redirect.html", staging / "index/index.html")
        (staging / "browse-index.json").write_bytes(json_bytes({"dataset_revision": report["dataset_revision"], "items": entries}))
        (staging / "home-data.json").write_bytes(json_bytes(homepage))
        (staging / "armor-catalog.json").write_bytes(json_bytes(armor_catalog))
        (staging / "weapon-catalogs").mkdir()
        for name, catalog in weapon_catalogs.items():
            (staging / "weapon-catalogs" / f"{name}.json").write_bytes(json_bytes(catalog))
        progress("Package static API and local map assets…")
        shutil.copytree(source, staging / "data/v1")
        for directory in ("map", "map_icon"):
            shutil.copytree(LEGACY_SITE_ROOT / "images" / directory, staging / "assets/images" / directory)
        (staging / ".nojekyll").write_text("")
        inventory = {p.relative_to(staging).as_posix(): file_hash(p) for p in sorted(staging.rglob("*")) if p.is_file()}
        package = {"generator": "mhxx-frontend", "dataset_revision": report["dataset_revision"], "entities": len(entries), "files": inventory}
        (staging / "frontend-manifest.json").write_bytes(json_bytes(package))
        verify_frontend(staging)
        backup = Path(temp) / "previous"
        if output.exists():
            output.rename(backup)
        try:
            staging.rename(output)
        except Exception:
            if backup.exists():
                backup.rename(output)
            raise
    return {"output": str(output), "entities": len(entries), "files": len(inventory) + 1, "index_bytes": (output / "browse-index.json").stat().st_size}


def make_frontend_server(root=DEFAULT_FRONTEND, port=8766, prefix="/games/mhxx/", quiet=False, host="127.0.0.1"):
    root = Path(root).resolve()
    package = verify_frontend(root)
    prefix = "/" + prefix.strip("/") + "/" if prefix.strip("/") else "/"
    if prefix != "/":
        safe_path(prefix.strip("/"))
    allowed = set(package["files"])

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.respond(False)

        def do_HEAD(self):
            self.respond(True)

        def respond(self, head):
            path = unquote(urlsplit(self.path).path)
            if path == prefix.rstrip("/") or (path == "/" and prefix != "/"):
                self.send_response(302)
                self.send_header("Location", prefix)
                self.end_headers()
                return
            if not path.startswith(prefix):
                self.send_error(404)
                return
            relative = path[len(prefix):]
            if relative + "/index.html" in allowed:
                self.send_response(302)
                self.send_header("Location", prefix + relative + "/")
                self.end_headers()
                return
            if not relative or relative.endswith("/"):
                relative += "index.html"
            try:
                safe_path(relative)
            except ValueError:
                self.send_error(404)
                return
            target = root / relative
            if relative not in allowed or not target.is_file() or target.is_symlink() or not target.resolve().is_relative_to(root):
                self.send_error(404)
                return
            data = target.read_bytes()
            mime = "text/javascript" if relative.endswith(".mjs") else mimetypes.guess_type(relative)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", mime + ("; charset=utf-8" if mime.startswith("text/") or mime == "application/json" else ""))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if not head:
                self.wfile.write(data)

        def reject_write(self):
            self.send_response(405)
            self.send_header("Allow", "GET, HEAD")
            self.end_headers()

        do_POST = do_PUT = do_PATCH = do_DELETE = reject_write

        def log_message(self, format, *args):
            if not quiet:
                super().log_message(format, *args)

    return ThreadingHTTPServer((host, port), Handler)


def serve_frontend(root=DEFAULT_FRONTEND, port=8766, prefix="/games/mhxx/", host="0.0.0.0"):
    server = make_frontend_server(root, port, prefix, host=host)
    path = "/" + prefix.strip("/") + "/" if prefix.strip("/") else "/"
    print(f"MHXX frontend listening on {host}:{server.server_port}", flush=True)
    print(f"Local preview: http://127.0.0.1:{server.server_port}{path}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

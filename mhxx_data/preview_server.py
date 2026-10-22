"""Local read-only HTTP preview of an already verified static API package."""

import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .static_api import safe_path, verify_export


def make_server(root, port=8765, prefix="/", quiet=False):
    root = Path(root).resolve()
    verify_export(root)
    prefix = "/" + prefix.strip("/") + "/" if prefix.strip("/") else "/"
    if prefix != "/":
        safe_path(prefix.strip("/"))
    inventory = json.loads((root / "integrity.json").read_text())
    allowed = set(inventory["files"]) | {"integrity.json"}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.respond(False)

        def do_HEAD(self):
            self.respond(True)

        def respond(self, head):
            path = unquote(urlsplit(self.path).path)
            if path in (prefix, prefix.rstrip("/")):
                self.send_response(302)
                self.send_header("Location", prefix + "manifest.json")
                self.end_headers()
                return
            if not path.startswith(prefix):
                self.send_error(404)
                return
            relative = path[len(prefix):]
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
            digest = hashlib.sha256(data).hexdigest()
            expected = inventory["files"].get(relative)
            if (expected and expected["sha256"] != digest) or (relative == "integrity.json" and data != integrity_bytes):
                self.send_error(409, "Export changed; restart the preview server")
                return
            etag = '"' + digest + '"'
            if self.headers.get("If-None-Match") == etag:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.end_headers()
                return
            mime = "application/json" if relative.endswith(".json") else "text/javascript" if relative.endswith(".mjs") else "text/plain"
            self.send_response(200)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("ETag", etag)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if not head:
                self.wfile.write(data)

        def reject_write(self):
            self.send_response(405)
            self.send_header("Allow", "GET, HEAD")
            self.end_headers()

        do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = reject_write

        def log_message(self, format, *args):
            if not quiet:
                super().log_message(format, *args)

    integrity_bytes = (root / "integrity.json").read_bytes()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    return server


def serve(root, port=8765, prefix="/"):
    server = make_server(root, port, prefix)
    path = "/" + prefix.strip("/") + "/" if prefix.strip("/") else "/"
    print(f"Read-only MHXX data: http://127.0.0.1:{server.server_port}{path}manifest.json", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

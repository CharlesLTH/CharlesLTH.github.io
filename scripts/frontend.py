#!/usr/bin/env python3
"""Build or preview the local MHXX reference frontend."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mhxx_data.frontend import DEFAULT_FRONTEND, build_frontend, serve_frontend, verify_frontend


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "serve", "verify"))
    parser.add_argument("--output", type=Path, default=DEFAULT_FRONTEND)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--host", default="0.0.0.0", help="Bind address; defaults to all IPv4 interfaces for LAN preview")
    parser.add_argument("--prefix", default="/games/mhxx/")
    args = parser.parse_args()
    try:
        if args.command == "serve":
            serve_frontend(args.output, args.port, args.prefix, args.host)
            return
        if args.command == "build":
            result = build_frontend(args.output)
        else:
            manifest = verify_frontend(args.output)
            result = {"status": "ok", "entities": manifest["entities"], "files": len(manifest["files"]) + 1}
    except (OSError, ValueError) as error:
        parser.exit(1, f"Error: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

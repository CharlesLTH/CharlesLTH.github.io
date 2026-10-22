#!/usr/bin/env python3
"""Reproducible local data audit. Run with .venv/bin/python scripts/data.py --help."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mhxx_data.pipeline import DEFAULT_DATABASE, build, check_database, fetch
from mhxx_data.query import connect, search, weapon, domain, item, map_details, combining
from mhxx_data.static_api import DEFAULT_EXPORT, export_data, verify_export


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("fetch", help="Download and verify the pinned upstream SQLite archive")
    commands.add_parser("build", help="Offline: extract HTML, import SQLite, compare and write audit reports")
    commands.add_parser("check", help="Read-only integrity, foreign key and relation checks")
    commands.add_parser("summary", help="Show the stored audit summary")
    find = commands.add_parser("search", help="Search extracted site weapon names")
    find.add_argument("text")
    explain = commands.add_parser("weapon", help="Trace one weapon level through recipes and material sources")
    explain.add_argument("page", help="Site page path or numeric filename, e.g. 218099")
    explain.add_argument("--level", type=int, required=True)
    explain.add_argument("--limit", type=int, default=3, help="Sample rows per source table (1–100)")
    for kind in ("monster", "quest", "armor", "skill", "item"):
        command = commands.add_parser(kind, help=f"Query local {kind} data and source relations")
        command.add_argument("page", help="Site path or numeric filename")
        command.add_argument("--limit", type=int, default=3, help="Sample related rewards/sources (1–100)")
    map_parser = commands.add_parser("map", help="Query local map gathering points")
    map_parser.add_argument("page", help="Map page path or numeric filename, e.g. 2400")
    map_parser.add_argument("--area", help="Area label, e.g. 1, BC, 秘境")
    map_parser.add_argument("--rank", choices=("LR", "HR", "G"))
    map_parser.add_argument("--limit", type=int, default=5, help="Number of gathering point variants (1–100)")
    combine_parser = commands.add_parser("combine", help="Search local combining recipes, including unlinked ammunition")
    combine_parser.add_argument("--search", default="", help="Output or input name contains this text")
    combine_parser.add_argument("--limit", type=int, default=10, help="Sample recipes (1–100)")
    export_parser = commands.add_parser("export", help="Export a complete versioned static JSON API")
    export_parser.add_argument("--output", type=Path, default=DEFAULT_EXPORT)
    export_parser.add_argument("--page-size", type=int, default=100)
    verify_parser = commands.add_parser("verify-export", help="Verify digests, links and pagination of exported data")
    verify_parser.add_argument("--output", type=Path, default=DEFAULT_EXPORT)
    serve_parser = commands.add_parser("serve-data", help="Read-only local HTTP preview of the static data package")
    serve_parser.add_argument("--output", type=Path, default=DEFAULT_EXPORT)
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--prefix", default="/", help="Preview a Pages-style subdirectory mount")
    args = parser.parse_args()
    try:
        if args.command == "fetch":
            result = {"archive": str(fetch())}
        elif args.command == "export":
            result = export_data(args.database, args.output, args.page_size, progress=lambda msg: print(msg, file=sys.stderr))
        elif args.command == "verify-export":
            result = verify_export(args.output)
        elif args.command == "serve-data":
            from mhxx_data.preview_server import serve
            serve(args.output, args.port, args.prefix)
            return
        elif args.command == "build":
            report = build(args.database, progress=lambda msg: print(msg, file=sys.stderr))
            result = {key: report[key] for key in ("site", "weapon_match_status", "item_match_status", "recipe_checks", "difference_fields", "validation")}
            result["database"] = str(args.database.resolve())
            result["domains"] = {k: v for k, v in report["domains"].items() if k not in ("issues", "limitations")}
            result["acquisition"] = {k: v for k, v in report["acquisition"].items()
                                     if k not in ("issues", "limitations", "gathering_probability_sums_not_100")}
            result["acquisition"]["non_100_probability_groups"] = len(report["acquisition"]["gathering_probability_sums_not_100"])
        else:
            with connect(args.database) as connection:
                if args.command == "check":
                    result = check_database(connection)
                elif args.command == "summary":
                    result = json.loads(connection.execute("SELECT value_json FROM source_manifest WHERE key='audit_summary'").fetchone()[0])
                elif args.command == "search":
                    result = search(connection, args.text)
                elif args.command == "weapon":
                    result = weapon(connection, args.page, args.level, args.limit)
                elif args.command == "item":
                    result = item(connection, args.page, args.limit)
                elif args.command == "map":
                    result = map_details(connection, args.page, args.area, args.rank, args.limit)
                elif args.command == "combine":
                    result = combining(connection, args.search, args.limit)
                else:
                    result = domain(connection, args.command, args.page, args.limit)
    except (ValueError, OSError) as error:
        parser.exit(1, f"Error: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Offline-startable web workspace and CLI, sharing the same decision engine."""

import argparse
import json
import os
from pathlib import Path
import sys
import threading

from . import __version__
from .demo import DEMO_TOKENS, demo_project, make_demo_server
from .engine import run_project
from .models import validate_project, ValidationError
from .reporting import html_report, json_report
from .server import make_panel_server


def main():
    parser = argparse.ArgumentParser(prog="tenantlens", description="Evidence-based API authorization testing. Local web panel + CLI.")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Start the loopback web panel")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--state-dir", default=".tenantlens")
    serve.add_argument("--demo", action="store_true", help="Start vulnerable, fixed and expired-session local demo targets")
    check = commands.add_parser("check", help="Run a project through the same test engine")
    check.add_argument("project", nargs="?", type=Path)
    check.add_argument("--demo", choices=("vulnerable", "fixed", "expired"))
    check.add_argument("--output", type=Path, default=Path("reports"))
    check.add_argument("--format", choices=("json", "html", "both"), default="both")
    args = parser.parse_args()
    servers = []
    try:
        if args.command == "serve":
            if not 1024 <= args.port <= 65531:
                parser.error("Use a port between 1024 and 65531.")
            panel = make_panel_server(args.port, args.state_dir)
            if args.demo:
                for key, value in DEMO_TOKENS.items():
                    os.environ[key] = value
                for offset, mode in enumerate(("vulnerable", "fixed", "expired"), 1):
                    demo = make_demo_server(mode, args.port + offset)
                    servers.append(demo)
                    threading.Thread(target=demo.serve_forever, daemon=True).start()
                    project = validate_project(demo_project(mode, f"http://127.0.0.1:{args.port + offset}"))
                    existing = panel.store.project(project["id"])
                    if existing is None:
                        panel.store.save_project(project)
                    elif existing["base_url"] != project["base_url"]:
                        print(f"Demo project {project['id']} uses a saved custom target; select or import the matching demo configuration.")
            print(f"TenantLens {__version__}: http://127.0.0.1:{args.port}", flush=True)
            print("Demo targets enabled." if args.demo else "Load your project and set its TENANTLENS_ token environment variables.", flush=True)
            try:
                panel.serve_forever(poll_interval=0.2)
            finally:
                if panel.coordinator.active:
                    panel.coordinator.cancel(panel.coordinator.active)
                panel.server_close()
        else:
            if args.demo:
                demo = make_demo_server(args.demo)
                servers.append(demo)
                threading.Thread(target=demo.serve_forever, daemon=True).start()
                project = demo_project(args.demo, f"http://127.0.0.1:{demo.server_address[1]}")
                credentials = DEMO_TOKENS
            elif args.project:
                project = json.loads(args.project.read_text(encoding="utf-8"))
                credentials = None
            else:
                parser.error("Provide a project JSON file or --demo MODE.")
            result = run_project(project, credentials=credentials)
            args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
            for kind in ("json", "html"):
                if args.format in (kind, "both"):
                    path = args.output / f"tenantlens-{result['id']}.{kind}"
                    path.write_bytes(json_report(result) if kind == "json" else html_report(result))
                    os.chmod(path, 0o600)
            print(json.dumps({"run_id": result["id"], "counts": result["counts"], "request_count": result["request_count"], "reports": str(args.output)}, ensure_ascii=False))
            return 2 if result["counts"]["ERROR"] or result["counts"]["INCONCLUSIVE"] else 1 if result["counts"]["VIOLATION"] else 0
    except KeyboardInterrupt:
        print("\nTenantLens stopped.")
        return 0
    except (OSError, ValueError, ValidationError) as exc:
        # Fixed message avoids copying unexpected secrets from user JSON into logs.
        print("Could not start or validate the project. Check the configuration, ports and file permissions.", file=sys.stderr)
        return 2
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

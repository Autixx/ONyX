#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _load_env_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"ONX env file not found: {path}")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip()


def _write_json(path: Path | None, payload: dict) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path is None:
        sys.stdout.write(rendered)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export or import ONX control-plane state.")
    parser.add_argument("--env-file", default="/etc/onx/onx.env", help="Path to ONX env file")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="Export control-plane state")
    export_parser.add_argument("--output", default="-", help="Output file path or - for stdout")
    export_parser.add_argument("--include-secrets", action="store_true", help="Include active management secrets in plaintext")

    import_parser = subparsers.add_parser("import", help="Import control-plane state")
    import_parser.add_argument("--input", required=True, help="Input JSON file")
    import_parser.add_argument("--replace", action="store_true", help="Delete DB objects not present in input")

    args = parser.parse_args()
    env_file = Path(args.env_file).resolve()
    _load_env_file(env_file)

    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from onx.db.session import SessionLocal  # noqa: PLC0415
    from onx.services.control_plane_state_service import ControlPlaneStateService  # noqa: PLC0415

    db = SessionLocal()
    service = ControlPlaneStateService()
    try:
        if args.command == "export":
            payload = service.export_state(db, include_management_secrets=bool(args.include_secrets))
            output = None if args.output == "-" else Path(args.output).resolve()
            _write_json(output, payload)
            return 0

        document = json.loads(Path(args.input).resolve().read_text(encoding="utf-8"))
        result = service.import_state(db, document, replace=bool(args.replace))
        sys.stdout.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

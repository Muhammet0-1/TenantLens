"""Create a clean source + offline frontend release ZIP using an explicit allowlist."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def build(destination):
    root = Path(__file__).resolve().parents[1]
    top_files = {"README.md", "KULLANIM.md", "LICENSE", "SECURITY.md", "CONTRIBUTING.md", "CHANGELOG.md", "THIRD_PARTY_NOTICES.md", "pyproject.toml", ".gitignore"}
    directories = {"tenantlens", "web", "tests", "docs", "examples", "scripts", ".github"}
    forbidden = {"node_modules", "__pycache__", ".venv", ".tenantlens", ".git", "reports", "test-results", "playwright-report"}
    allowed_suffixes = {".py", ".md", ".txt", ".toml", ".json", ".tsx", ".ts", ".js", ".cjs", ".html", ".css", ".png", ".svg", ".yml", ".yaml"}
    files = []
    for file in sorted(root.rglob("*")):
        relative = file.relative_to(root)
        if not file.is_file() or file.is_symlink() or any(p in forbidden for p in relative.parts):
            continue
        if relative.name in top_files and len(relative.parts) == 1:
            files.append((file, relative))
        elif len(relative.parts) > 1 and relative.parts[0] in directories and file.suffix in allowed_suffixes:
            files.append((file, relative))
    required = {"tenantlens/static/index.html", "web/package-lock.json", "tests/test_engine.py", "README.md", "KULLANIM.md", "LICENSE"}
    missing = required - {relative.as_posix() for _, relative in files}
    if missing:
        raise SystemExit("Missing release files: " + ", ".join(sorted(missing)))
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest = {relative.as_posix(): hashlib.sha256(file.read_bytes()).hexdigest() for file, relative in files}
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for file, relative in files:
            info = zipfile.ZipInfo("TenantLens/" + relative.as_posix(), date_time=(2026, 10, 7, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, file.read_bytes())
        info = zipfile.ZipInfo("TenantLens/RELEASE_MANIFEST.json", date_time=(2026, 10, 7, 0, 0, 0))
        info.external_attr = 0o100644 << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, json.dumps({"version": "0.1.0", "sha256": manifest}, indent=2) + "\n")
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    print(json.dumps({"zip": str(destination), "files": len(files) + 1, "bytes": destination.stat().st_size, "sha256": digest}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", nargs="?", type=Path, default=Path("dist/TenantLens_v0.1.0.zip"))
    build(parser.parse_args().destination.resolve())

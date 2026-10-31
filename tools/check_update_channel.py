"""Release gate: a published version must also be usable by existing launchers.

Read-only. Supply GitHub's releases API JSON; never uploads or rewrites assets.
Signature verification uses the same PowerShell code shipped to users.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "Henry7682/mjs-overlay-assistant"


def version(value):
    if not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise ValueError(f"Invalid release version: {value}")
    return tuple(map(int, value.split(".")))


def validate(manifest, releases):
    """Check newest published numeric version, including public test releases."""
    published = [r for r in releases if not r.get("draft")
                 and r.get("published_at")
                 and re.fullmatch(r"v\d+\.\d+\.\d+", r.get("tag_name", ""))]
    if not published:
        raise ValueError("No published numeric releases found")
    newest = max(published, key=lambda r: version(r["tag_name"][1:]))
    if manifest["version"] != newest["tag_name"][1:]:
        raise ValueError("Update channel does not target the newest published version")
    if (manifest.get("schema_version") != 1 or manifest.get("channel") != "stable"
            or manifest.get("minimum_launcher") != 1):
        raise ValueError("Channel must remain readable by the 1.0.0 launcher")
    assets = {a["browser_download_url"]: a for r in published for a in r["assets"]}
    checked = []
    for role in ("portable", "standalone", "source", "models", "wheels", "downloader"):
        item = manifest["assets"][role]
        urls = [u for u in item["urls"] if u.startswith(
            f"https://github.com/{REPOSITORY}/releases/download/")]
        if not urls:
            raise ValueError(f"No GitHub download for {role}")
        for url in urls:
            actual = assets.get(url)
            if actual is None:
                raise ValueError(f"Missing published asset: {role}")
            if (actual["name"] != item["name"] or actual["size"] != item["bytes"]
                    or actual.get("digest") != "sha256:" + item["sha256"]):
                raise ValueError(f"Published asset mismatch: {role}")
        checked.append(role)
    return {"version": manifest["version"], "roles_checked": checked,
            "old_launcher_protocol": 1, "published_test_release": newest["prerelease"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "release.json")
    parser.add_argument("--releases", type=Path, required=True,
                        help="JSON from GET /repos/owner/repo/releases (include latest releases)")
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    def quote(path):
        return "'" + str(path).replace("'", "''") + "'"
    ps = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    code = ("$ErrorActionPreference='Stop'; . " + quote(ROOT / "release/Release.ps1")
            + "; Assert-Signature ([IO.File]::ReadAllBytes(" + quote(manifest_path)
            + ")) ([IO.File]::ReadAllText(" + quote(manifest_path.with_suffix(".sig"))
            + ")) " + quote(ROOT / "release/public-key.xml"))
    subprocess.run([str(ps), "-NoProfile", "-NonInteractive", "-Command", code],
                   check=True, timeout=20)
    result = validate(json.loads(manifest_path.read_text("utf-8-sig")),
                      json.loads(args.releases.read_text("utf-8-sig")))
    result["signature_verified"] = True
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

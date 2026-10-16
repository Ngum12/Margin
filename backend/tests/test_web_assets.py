"""The fonts and icons bundled into the web app match their manifest (licences recorded in
docs/DEPENDENCIES.md and THIRD_PARTY_NOTICES.md)."""

import hashlib
import json
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "assets"


def test_bundled_web_assets_match_their_checksums_and_have_licences() -> None:
    manifest = json.loads((ASSETS / "assets.json").read_text(encoding="utf-8"))
    assert manifest
    for asset in manifest:
        assert asset["licence"] in {"OFL-1.1", "ISC AND MIT"}
        assert (ASSETS / asset["licence_file"]).is_file()
        for relative, sha256 in asset["files"].items():
            digest = hashlib.sha256((ASSETS / relative).read_bytes()).hexdigest()
            assert digest == sha256, relative


def test_every_bundled_font_file_is_listed() -> None:
    manifest = json.loads((ASSETS / "assets.json").read_text(encoding="utf-8"))
    listed = {Path(f).name for asset in manifest for f in asset["files"]}
    present = {
        p.name for p in (ASSETS / "fonts").iterdir() if p.suffix in {".woff2", ".ttf", ".otf"}
    }
    assert present <= listed

"""Fetch, verify and import the pinned Studio North release (code, SQL and frozen data)."""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "lab"
CACHE = ROOT / "cache"
SITE = ROOT / "site"
BASELINE = ROOT / "baseline"
LOCK = json.loads((ROOT / "lab.lock.json").read_text(encoding="utf-8"))
SEED, STEPS = int(LOCK["model_seed"]), int(LOCK["model_steps"])


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(force: bool = False, from_path: str | None = None) -> dict:
    """Download the release at the pinned commit into ./lab (once), then verify it.

    from_path copies an existing local checkout instead (for example if the upstream commit disappears);
    the data hashes are verified either way.
    """
    if LAB.exists() and not force:
        return verify()
    if from_path:
        if LAB.exists():
            shutil.rmtree(LAB)
        shutil.copytree(Path(from_path), LAB, ignore=shutil.ignore_patterns(".git", ".venv", "outputs", "node_modules", "__pycache__"))
        return {**verify(), "source": str(Path(from_path).resolve())}
    url = f"https://github.com/{LOCK['repository']}/archive/{LOCK['commit']}.zip"
    request = urllib.request.Request(url, headers={"User-Agent": "studio-north-dashboard/1.0"})
    with urllib.request.urlopen(request, timeout=180) as reply:
        payload = reply.read()
    archive = zipfile.ZipFile(io.BytesIO(payload))
    comment = archive.comment.decode("ascii", "ignore").strip()
    if comment and comment != LOCK["commit"]:
        raise RuntimeError(f"Archive is for commit {comment}, expected {LOCK['commit']}")
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        tmp = Path(tmp)
        for info in archive.infolist():
            parts = PurePosixPath(info.filename).parts
            if not parts or ".." in parts or PurePosixPath(info.filename).is_absolute():
                raise RuntimeError("Unsafe path in archive: " + info.filename)
        archive.extractall(tmp)
        tops = [p for p in tmp.iterdir() if p.is_dir()]
        if len(tops) != 1:
            raise RuntimeError("Unexpected archive layout")
        if LAB.exists():
            shutil.rmtree(LAB)
        shutil.move(str(tops[0]), LAB)
    return {**verify(), "downloaded_bytes": len(payload), "archive_sha256": _sha(payload)}


def importable() -> None:
    if not (LAB / "cohort_lab").is_dir():
        raise SystemExit("The Studio North release is missing. Run: uv run python dashboard.py fetch")
    if str(LAB) not in sys.path:
        sys.path.insert(0, str(LAB))


def verify() -> dict:
    """Check the frozen data against the pinned manifest hash and the release's own per-file hashes."""
    importable()
    manifest = LAB / "data" / "data_manifest.json"
    digest = _sha(manifest.read_bytes())
    if digest != LOCK["data_manifest_sha256"]:
        raise RuntimeError(f"data_manifest.json hash {digest} does not match the pinned release")
    from cohort_lab.workflow import verify_frozen_inputs
    verify_frozen_inputs(LAB / "data")
    return {"lab": str(LAB), "commit": LOCK["commit"], "data_manifest_sha256": digest, "frozen_inputs": "verified"}

"""Download the two file-based upstream snapshots, pin their hashes, and write slices.

Usage:
    uv run python scripts/fetch_snapshots.py

Full files go to DATA_CACHE_DIR (gitignored). fixtures/snapshots/ gets a MANIFEST.json with
URL, SHA256, size, and entry counts, plus one JSON slice per snapshot holding only entries
whose reduced composition is one of the Phase 0 materials.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import statistics
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from pymatgen.core import Composition

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record_wire import MATERIALS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "fixtures" / "snapshots"

# URLs come from the upstream clients' own metadata (jarvis-tools figshare.py and matminer
# dataset_metadata.json). Hashes are computed here and compared on later runs.
SNAPSHOTS: dict[str, dict[str, str]] = {
    "jarvis_dft_3d": {
        "url": "https://ndownloader.figshare.com/files/38521619",
        "inner_name": "jdft_3d-12-12-2022.json",
        "source_of_url": "usnistgov/jarvis jarvis/db/figshare.py, key dft_3d",
        "citation": "https://www.nature.com/articles/s41524-020-00440-1",
    },
    "expt_gap": {
        "url": "https://ndownloader.figshare.com/files/13464434",
        "expected_sha256": "2d0980e3533c1ba6ad6e392a88f08cfcf2d311d4b7fe6eb0b0c8e876211dfda3",
        "source_of_url": "hackingmaterials/matminer matminer/datasets/dataset_metadata.json",
        "citation": "Zhuo, Mansouri Tehrani, Brgoch, J. Phys. Chem. Lett. 9, 1668 (2018), SI",
        "note": "Full compendium of experimental gaps; compositions repeat with differing values.",
    },
    "matbench_expt_gap": {
        "url": "https://ml.materialsproject.org/projects/matbench_expt_gap.json.gz",
        "expected_sha256": "783e7d1461eb83b00b2f2942da4b95fda5e58a0d1ae26b581c24cf8a82ca75b2",
        "source_of_url": "hackingmaterials/matminer matminer/datasets/dataset_metadata.json",
        "citation": "Zhuo, Mansouri Tehrani, Brgoch, J. Phys. Chem. Lett. 9, 1668 (2018)",
    },
}

TARGETS = {Composition(m).reduced_formula for m in MATERIALS}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> None:
    if dest.exists():
        print(f"  cached {dest.name} ({dest.stat().st_size:,} bytes)")
        return
    tmp = dest.with_suffix(dest.suffix + ".part")
    with httpx.stream("GET", url, follow_redirects=True, timeout=120.0) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with tmp.open("wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total and done % (50 << 20) < (1 << 20):
                    print(f"  {dest.name}: {done / total:.0%}")
    tmp.rename(dest)
    print(f"  downloaded {dest.name} ({dest.stat().st_size:,} bytes)")


def reduced(formula: str) -> str | None:
    try:
        return Composition(formula).reduced_formula
    except Exception:  # noqa: BLE001
        return None


def slice_jarvis(raw: Path) -> dict[str, Any]:
    with zipfile.ZipFile(raw) as z:
        names = z.namelist()
        inner = [n for n in names if n.endswith(".json")][0]
        with z.open(inner) as f:
            data = json.load(io.TextIOWrapper(f, encoding="utf-8"))
    keys = sorted(data[0].keys())
    mp_like = [k for k in keys if "mp" in k.lower() or "materials_project" in k.lower()]
    hits = [d for d in data if reduced(d.get("formula", "")) in TARGETS]
    (OUT / "jarvis_dft_3d.slice.json").write_text(json.dumps(hits, indent=1, default=str) + "\n")
    with_icsd = sum(1 for d in hits if parse_icsd(d.get("icsd")))
    na_fields = sorted({k for d in hits for k, v in d.items() if v == "na"})
    print(f"  jarvis keys ({len(keys)}): {keys}")
    print(f"  jarvis keys that look like MP ids: {mp_like or 'none'}")
    print(f"  jarvis entries total={len(data)} matching={len(hits)}")
    print(f"  jarvis slice records with >=1 ICSD id: {with_icsd} of {len(hits)}")
    print(f"  jarvis fields using the 'na' sentinel in the slice: {na_fields}")
    return {
        "inner_file": inner,
        "entries_total": len(data),
        "entries_in_slice": len(hits),
        "record_keys": keys,
        "mp_id_like_keys": mp_like,
        "icsd_field": "comma-separated string of ICSD ids, empty when none",
        "slice_records_with_icsd": with_icsd,
        "na_sentinel_fields_in_slice": na_fields,
    }


def parse_icsd(value: Any) -> set[int]:
    """JARVIS stores ICSD ids as a comma-separated string; empty means none."""
    if not isinstance(value, str) or not value.strip():
        return set()
    return {int(tok) for tok in (t.strip() for t in value.split(",")) if tok.isdigit()}


def slice_gap_table(raw: Path, name: str) -> dict[str, Any]:
    """Slice a matminer gap table (pandas split orient) and report spread per composition."""
    with gzip.open(raw, "rt", encoding="utf-8") as f:
        data = json.load(f)
    cols = data["columns"]
    rows = [dict(zip(cols, r, strict=True)) for r in data["data"]]
    comp_col = "composition" if "composition" in cols else "formula"
    gap_col = [c for c in cols if "gap" in c][0]
    zeros = sum(1 for r in rows if r[gap_col] == 0)
    hits = [r for r in rows if reduced(r[comp_col]) in TARGETS]
    (OUT / f"{name}.slice.json").write_text(json.dumps(hits, indent=1) + "\n")
    by_comp: dict[str, list[float]] = {}
    for r in hits:
        key = reduced(r[comp_col]) or r[comp_col]
        by_comp.setdefault(key, []).append(float(r[gap_col]))
    spread: dict[str, dict[str, float | int]] = {}
    print(f"  {name} columns: {cols}")
    print(f"  {name} rows={len(rows)} zero_gap={zeros} matching={len(hits)}")
    for key in sorted(by_comp):
        vals = sorted(by_comp[key])
        med = statistics.median(vals)
        spread[key] = {"n": len(vals), "min": vals[0], "median": med, "max": vals[-1]}
        print(
            f"    {key:8s} n={len(vals):3d} min={vals[0]:.2f} median={med:.2f} max={vals[-1]:.2f}"
        )
    missing = sorted(TARGETS - set(by_comp))
    print(f"  {name} compositions absent: {missing}")
    return {
        "columns": cols,
        "composition_column": comp_col,
        "entries_total": len(rows),
        "entries_with_zero_gap": zeros,
        "entries_in_slice": len(hits),
        "spread_by_composition": spread,
        "target_compositions_absent": missing,
    }


def main() -> int:
    load_dotenv(ROOT / ".env")
    cache = ROOT / os.environ.get("DATA_CACHE_DIR", ".data-cache")
    cache.mkdir(exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "snapshots": {},
    }

    entry: dict[str, Any]
    for name in ("matbench_expt_gap", "expt_gap"):
        print(f"[{name}]")
        spec = SNAPSHOTS[name]
        raw = cache / f"{name}.json.gz"
        download(spec["url"], raw)
        digest = sha256_file(raw)
        entry = {**spec, "local_file": raw.name, "sha256": digest, "bytes": raw.stat().st_size}
        entry["sha256_matches_matminer"] = digest == spec["expected_sha256"]
        print(f"  sha256={digest} matches_matminer={entry['sha256_matches_matminer']}")
        entry.update(slice_gap_table(raw, name))
        manifest["snapshots"][name] = entry

    print("[jarvis_dft_3d]")
    spec = SNAPSHOTS["jarvis_dft_3d"]
    raw = cache / "jdft_3d-12-12-2022.zip"
    download(spec["url"], raw)
    digest = sha256_file(raw)
    entry = {**spec, "local_file": raw.name, "sha256": digest, "bytes": raw.stat().st_size}
    print(f"  sha256={digest}")
    entry.update(slice_jarvis(raw))
    manifest["snapshots"]["jarvis_dft_3d"] = entry

    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {OUT / 'MANIFEST.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

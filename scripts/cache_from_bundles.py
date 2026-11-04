"""Write classifier cache entries from saved run bundles, so classifications already paid
for are never requested again (owner rule, Track G). No API call is made.

Each verified-or-not evidence hit that carries `classifier_cache_key` becomes the same cache
record the classifier writes (agent/classifier.py), keyed by (abstract sha, classify prompt
hash, model version). Existing entries are left alone. Hits the verifier dropped are not in
the bundle and cannot be restored.

    uv run python scripts/cache_from_bundles.py .data-cache/evals/runs/<id>.json ...
"""

from __future__ import annotations

import sys
from pathlib import Path

from materials_triage.agent import prompts
from materials_triage.cli import wiring
from materials_triage.records.bundle import ProvenanceBundle
from materials_triage.settings import Settings


def main(paths: list[str]) -> int:
    cache = wiring.make_cache(Settings())
    prompt_hash = prompts.step_hash("classify")
    written = kept = skipped = 0
    for p in paths:
        b = ProvenanceBundle.model_validate_json(Path(p).read_text())
        model = b.run.model_version
        for hit in b.evidence:
            if hit.classifier_cache_key is None or model is None:
                skipped += 1
                continue
            if cache.get(hit.classifier_cache_key) is not None:
                kept += 1
                continue
            cache.put(
                hit.classifier_cache_key,
                {
                    "label": hit.label.value,
                    "deposition_method": hit.deposition_method,
                    "supporting_sentence": hit.supporting_sentence,
                    "verified": hit.supporting_sentence is not None,
                    "model_version": model,
                    "prompt_hash": prompt_hash,
                    "source": f"backfilled from run {b.run.run_id}",
                },
            )
            written += 1
    print(f"cache entries written {written}, already present {kept}, without a key {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""Apply a completed AI review to a fresh experimental dataset, preserving source votes.

python scripts/finalize_label_review.py BATCH --review REVIEW.json --out NEW_FOLDER
Optional --existing-labels defaults to BATCH/merged/labels_final.jsonl when present.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.labeling.review import apply_review


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("batch", type=Path)
    ap.add_argument("--review", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--existing-labels", type=Path)
    args = ap.parse_args()
    index_path = args.batch / "clips_index.json"
    labels_path = args.existing_labels or args.batch / "merged/labels_final.jsonl"
    if args.existing_labels and not labels_path.is_file():
        raise FileNotFoundError(labels_path)
    existing = ([json.loads(line) for line in labels_path.read_text(encoding="utf-8").splitlines() if line.strip()]
                if labels_path.is_file() else [])
    reviewed, labels, excluded = apply_review(
        json.loads(index_path.read_text(encoding="utf-8")), existing,
        json.loads(args.review.read_text(encoding="utf-8")))
    manifest = {"source_batch": args.batch.name, "review_complete": True,
                "exported_at_utc": datetime.now(timezone.utc).isoformat(),
                "human_reviewed_ai_labels": False, "scope": "local experimental training",
                "source_index_sha256": hashlib.sha256(index_path.read_bytes()).hexdigest(),
                "review_sha256": hashlib.sha256(args.review.read_bytes()).hexdigest(),
                "source_labels_sha256": hashlib.sha256(labels_path.read_bytes()).hexdigest() if labels_path.is_file() else None,
                "accepted": len(labels), "excluded": len(excluded),
                "label_distribution": dict(Counter(r["label"] for r in labels)),
                "ai_adjudicated": sum(r["status"] == "AI_ADJUDICATED" for r in labels)}
    args.out.mkdir(parents=True, exist_ok=False)
    for name, payload in (("clips_index.json", reviewed), ("review_manifest.json", manifest)):
        (args.out / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, payload in (("labels_reviewed.jsonl", labels), ("excluded.jsonl", excluded)):
        (args.out / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in payload), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=True))


if __name__ == "__main__":
    main()

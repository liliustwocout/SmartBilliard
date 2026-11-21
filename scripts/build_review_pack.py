"""Repackage unresolved or entirely unlabeled clips, preserving the original batch.

python scripts/build_review_pack.py BATCH --results BATCH/ketqua/*.json --out BATCH/review
Each reviewer receives all pending clips. Original votes and merged labels are untouched.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_label_pack import LABEL_HELP, TEMPLATE
from services.labeling.merge import ResultError, load_results, merge_results
from services.labeling.windows import ALL_LABELS


def build_review_pack(batch: Path, results: list[Path], out: Path, members: int = 2) -> list[str]:
    if members < 1:
        raise ValueError("Số người rà soát phải dương")
    index = json.loads((batch / "clips_index.json").read_text(encoding="utf-8"))
    votes = load_results(results)
    if any(r["pack_id"] != index["batch"] for r in votes):
        raise ResultError("Kết quả không thuộc batch đang rà soát")
    decisions = merge_results(votes)["decisions"]
    pending = sorted(cid for cid in index["clips"] if not decisions.get(cid, {}).get("label"))
    if not pending:
        return []
    # A fresh destination prevents an earlier reviewer's local progress being overwritten.
    if out.exists():
        raise FileExistsError(out)
    clips = []
    for cid in pending:
        entry = index["clips"][cid]
        image = cv2.imread(str(batch / "_sprites" / f"{cid}.jpg"))
        if image is None:
            raise ValueError(f"Không đọc được sprite {cid}")
        n = len(entry["frame_indices"])
        elapsed = entry["t_end"] - entry["t_start"]
        clips.append({"id": cid, "sprite": f"clips/{cid}.jpg", "cols": 6,
                      "rows": image.shape[0] // (image.shape[1] // 6),
                      "tile": image.shape[1] // 6, "n": n,
                      "fps": (n - 1) / elapsed if elapsed > 0 else 1.0})
    template = TEMPLATE.read_text(encoding="utf-8")
    out.mkdir(parents=True, exist_ok=False)
    for i in range(members):
        member = f"member-review-{i + 1}"
        pack = out / f"pack_{member}"
        (pack / "clips").mkdir(parents=True)
        for cid in pending:
            shutil.copy2(batch / "_sprites" / f"{cid}.jpg", pack / "clips" / f"{cid}.jpg")
        manifest = {"batch": index["batch"], "member_id": member, "clips": clips,
                    "labels": [{"id": k, "help": LABEL_HELP[k]} for k in ALL_LABELS]}
        (pack / "index.html").write_text(
            template.replace("/*__PACK_JSON__*/null", json.dumps(manifest, ensure_ascii=False)), encoding="utf-8")
        shutil.make_archive(str(pack), "zip", pack)
    return pending


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("batch", type=Path)
    ap.add_argument("--results", nargs="+", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--members", type=int, default=2)
    args = ap.parse_args()
    pending = build_review_pack(args.batch, args.results, args.out, args.members)
    print(f"{len(pending)} clip can ra soat -> {args.out}")


if __name__ == "__main__":
    main()

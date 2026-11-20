"""Merge the result files returned by team members and report agreement.

Usage: python scripts/merge_labels.py data/label_packs/batch-XXXX/results/*.json
Writes labels_final.jsonl (clips with an AGREED or MAJORITY label) and agreement_report.json
next to the first result's folder, or into --out.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.labeling.merge import ResultError, load_results, merge_results


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", nargs="+", type=Path, help="File ket-qua-*.json của các thành viên")
    ap.add_argument("--min-votes", type=int, default=2, help="Số phiếu hợp lệ tối thiểu mỗi clip (mặc định 2)")
    ap.add_argument("--out", type=Path, default=None, help="Thư mục ghi kết quả (mặc định: cạnh file đầu tiên)")
    args = ap.parse_args()

    try:
        results = load_results(args.results)
    except (ResultError, OSError, json.JSONDecodeError) as err:
        raise SystemExit(f"Lỗi đọc kết quả: {err}")
    merged = merge_results(results, min_votes=args.min_votes)

    out = args.out or args.results[0].parent
    out.mkdir(parents=True, exist_ok=True)
    final = out / "labels_final.jsonl"
    with final.open("w", encoding="utf-8") as file:
        for clip_id, d in sorted(merged["decisions"].items()):
            if d["label"]:
                file.write(json.dumps({"clip_id": clip_id, **d}, ensure_ascii=False) + "\n")
    report = out / "agreement_report.json"
    report.write_text(json.dumps(merged["report"], ensure_ascii=False, indent=2), encoding="utf-8")

    r = merged["report"]
    print(f"Tổng clip có nhãn: {r['clips_total']}")
    print("Trạng thái:", r["status"])
    print("Phân bố nhãn cuối:", r["final_label_distribution"])
    for p in r["pairwise"]:
        print(f"  {p['members'][0]} vs {p['members'][1]}: {p['shared_clips']} clip chung, "
              f"đồng ý {p['percent_agreement']}, kappa {p['kappa']}")
    print(f"Cần xem lại: {len(r['review_clip_ids'])} clip. Đã ghi {final.name} và {report.name} vào {out}")


if __name__ == "__main__":
    main()

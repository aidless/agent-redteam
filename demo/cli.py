#!/usr/bin/env python3
"""Print the 12×5 red-team coverage matrix in a terminal.

The matrix is produced by the same harness as the web demo. It is a layer-level
matrix over synthetic attack payloads, not an end-to-end LLM run.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "demo") not in sys.path:
    sys.path.insert(0, str(ROOT / "demo"))

from harness import LAYERS, build_payload  # noqa: E402

SHORT = {"block": "BLK", "modify": "MOD", "flag": "FLG", "allow": "ALW"}


def main() -> int:
    payload = build_payload()
    print("12 attacks × 5 defense layers — layer-level harness\n")
    print("L1 input · L2 tool · L3 output · L4 audit · L5 constitutional")
    print("BLK=block MOD=modify FLG=flag ALW=allow -=not exercised\n")
    print(f"{'ID':<30} {'L1':<4} {'L2':<4} {'L3':<4} {'L4':<4} {'L5':<4} verdict")
    print("-" * 74)
    for case in payload["cases"]:
        cells = [SHORT.get(case["by_layer"].get(layer), "-") for layer in LAYERS]
        print(f"{case['id']:<30} " + " ".join(f"{c:<4}" for c in cells) + f" {case['verdict']}")

    s = payload["summary"]
    miss = ", ".join(s["expected_miss"]) or "-"
    print("-" * 74)
    print(f"{s['mitigated']}/{s['attacks']} mitigated · {s['blocked']} blocked · "
          f"{s['modified']} modified · {s['flagged_only']} flagged-only")
    print(f"expected hit {s['expected_hit']}/{s['attacks']} · expected miss {miss}")
    print(f"verification: {payload['verification']['status']}")

    print("\nleave-one-layer-out:")
    for row in payload["layer_ablation"]["rows"]:
        lost = []
        if row["lost_block"]:
            lost.append("lost block " + ", ".join(v.split("_")[0] for v in row["lost_block"]))
        if row["lost_flag"]:
            lost.append("lost flag " + ", ".join(v.split("_")[0] for v in row["lost_flag"]))
        if lost:
            print(f"  remove {row['layer']:<20} -> " + "; ".join(lost))

    print("\ndemo: synthetic attack payloads · real defense actions · 0 API calls")
    return 0 if payload["verification"]["status"] == "MATCH" else 1


if __name__ == "__main__":
    raise SystemExit(main())

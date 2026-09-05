#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""sdcbench_select.py — 从评估报告筛选高 SDC 检出率序列, 产出最终交付集.

筛选标准 (如实记录, 不夸大):
  - sdc_rate >= threshold (默认 0.875 = 8 注入中 ≥7 diverge)
  - status == OK
输出: final_manifest.json + 统计摘要.
"""
import json, sys, argparse, shutil, os

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pool_manifest")
    ap.add_argument("reports", nargs="+", help="batch report json files")
    ap.add_argument("--threshold", type=float, default=0.875)
    ap.add_argument("--out", default="output/sdcbench_final")
    args = ap.parse_args()

    manifest = {e["id"]: e for e in json.load(open(args.pool_manifest))}
    results = {}
    for rp in args.reports:
        for r in json.load(open(rp)):
            results[r["id"]] = r

    selected, rejected = [], []
    for rid, r in sorted(results.items()):
        if r.get("status") != "OK":
            rejected.append((r["name"], r["status"]))
            continue
        if r["sdc_rate"] >= args.threshold:
            selected.append(r)
        else:
            rejected.append((r["name"], f"sdc_rate={r['sdc_rate']:.2f}"))

    os.makedirs(args.out, exist_ok=True)
    final = []
    for r in selected:
        e = manifest[r["id"]]
        e["sdc_rate"] = r["sdc_rate"]
        e["detect_rate"] = r["detect_rate"]
        e["inj_detail"] = r["inj"]
        e["golden"] = r["golden"]
        final.append(e)
    json.dump(final, open(os.path.join(args.out, "final_manifest.json"), "w"), indent=1)

    n = len(results)
    print(f"评估总数: {n}  入选: {len(final)} (threshold={args.threshold})  淘汰: {len(rejected)}")
    if n:
        avg = sum(r["sdc_rate"] for r in selected) / max(1, len(selected))
        allavg = sum(r["sdc_rate"] for r in results.values() if r.get("status")=="OK") / max(1, sum(1 for r in results.values() if r.get("status")=="OK"))
        print(f"入选平均 SDC 率: {avg:.3f}   全池平均: {allavg:.3f}")
    from collections import Counter
    ops = Counter(e["op"] for e in final)
    fams = Counter(e["family"] for e in final)
    print(f"op 分布: {dict(ops)}")
    print(f"family 分布 (top5): {dict(fams.most_common(5))}")

if __name__ == "__main__":
    main()

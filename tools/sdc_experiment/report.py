# tools/sdc_experiment/report.py
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""report.py — 汇总 output/experiments/ 全部实验 → 单一诚实报告。"""
import glob, json, os, datetime

SCHEME_CLAIMS = [
    ("§3.1 D13 bit-flip 3.00×", "E2 bit D13/B"),
    ("§3.1 D13 structural 7.79×", "E2 struct D13/B"),
    ("§4.2 真机执行能力 (Snapshot/Runner/Orchestrator)", "E3"),
    ("§4.3 L3 多板分布式 + 噪声分类", "E4"),
    ("§4.4 Sim→HW 统计关联", "E5 (弱化: 组粒度健康度关联)"),
    ("§4.2 进化引擎 (T 8.8×)", "F5 已有 + E5 Unicorn 代理"),
]

def main():
    lines = ["# sdcfuzz 实验验证报告",
             f"\n生成: {datetime.date.today()} (由 tools/sdc_experiment/report.py 自动汇总)\n",
             "## 诚实声明",
             "- gem5 O3 模型 ≠ TSV110 RTL: 所有仿真 diverge 率是模型级结论",
             "- 健康硅片上真 SDC 稀少: E3/E4 的 SDC=0 是预期结果, 不是方法失败",
             "- E5 是组粒度执行健康度关联 (Sim 代理指标混合), 非 SDC 率直接关联",
             "- 每个实验的判定标准在运行前预注册, 未达标者如实记录\n"]
    for d in sorted(glob.glob("output/experiments/*/")):
        name = os.path.basename(d.rstrip("/"))
        if name in ("feedback", "hw_scan_logs"):
            continue
        lines.append(f"\n## {name}\n")
        for f in ["summary.json"]:
            p = os.path.join(d, f)
            if os.path.exists(p):
                lines.append("```json\n" + open(p).read().strip() + "\n```\n")
        for f in sorted(glob.glob(os.path.join(d, "*.json"))):
            if os.path.basename(f) == "summary.json":
                continue
            lines.append(f"\n### {os.path.basename(f)}\n```json\n" +
                         open(f).read().strip() + "\n```\n")
    lines.append("\n## scheme.md 声明对照表\n")
    lines.append("| scheme.md 声明 | 验证实验 | 状态 |")
    lines.append("|---|---|---|")
    for claim, exp in SCHEME_CLAIMS:
        lines.append(f"| {claim} | {exp} | 见上方 {exp.split()[0]} verdict |")
    out = "\n".join(lines) + "\n"
    print(out)

if __name__ == "__main__":
    main()

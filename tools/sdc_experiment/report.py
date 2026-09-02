# tools/sdc_experiment/report.py
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""report.py — 汇总 output/experiments/ 全部实验 → 单一诚实报告。"""
import glob, json, os, datetime

SCHEME_CLAIMS = [
    # (scheme.md 声明, 验证实验, 状态, 依据)
    # 状态取值: 已验证 / 部分验证 / 未验证 / 已验证(引用) — 依据列必须给出
    # 真实实验 verdict + 数值 + 诚实边界, 与上方各实验 summary 逐项对应。
    ("§3.1 A/B 基线数据可复现 (B/A ≥ 1.5×)", "E1 (A/B bit-flip 各100次)",
     "未验证",
     "B/A=1.4 < 1.5× 预注册阈值 → NOT_REPRODUCED(诚实记录); 方向与 F3 "
     "(B=8.0% > A=3.9%) 一致, 100-run 样本 CI 宽"),
    ("§3.1 D13 bit-flip 3.00×", "E2 bit (D13/B 各100次)",
     "部分验证",
     "BEAT: 3.143× (p=0.00429), 方向与 F4 (3.00×) 一致; 100-run 样本 "
     "(F4 为 500-run), 幅度未达 F4 精度"),
    ("§3.1 D13 structural 7.79×", "E2 struct (D13/B 各100次)",
     "部分验证",
     "BEAT: 12.8× (p=5.6e-20), 方向与 F4 (7.79×) 一致; 100-run 样本 "
     "(F4 为 500-run), 幅度未达 F4 精度"),
    ("§4.2 真机执行能力 (Snapshot/Runner/Orchestrator)", "E3 (本机 0103 真跑)",
     "已验证",
     "HW_SCAN_OK: 20 模板管线, 30min 扫描, SDC=0, play_count=3840, "
     "噪声全分类 (segv/runaway/misbehave=0), v1 交叉校验 match"),
    ("§4.3 L3 多板分布式 + 噪声分类", "E4 (0101 远程全链路演练)",
     "部分验证",
     "REMOTE_CHAIN_OK: 单远程板 (0101) 全链路 (注册→部署→扫描→回收) "
     "通过; 多板并行未验证 (用户设备待凭据, Step 3 待用户)"),
    ("§4.4 Sim→HW 统计关联", "E5 (12 组组粒度关联)",
     "未验证",
     "NOT_SIGNIFICANT: ρ=-0.2219, p=0.74733 → 诚实弱化版 (组粒度健康度 "
     "关联) 也未获支持; sim 面为 Unicorn T 代理指标混用, 非 gem5 diverge 率"),
    ("§4.2 进化引擎 (T 8→70, 8.8×)", "F5 历史数据 (E5 用其 Unicorn 代理)",
     "已验证(引用)",
     "F5 (T 8→70, 8.8×) 为本分支之前的历史证据 (tools/sdc_mutator/"
     "evolution_engine.py + paper2 program), 本次未重跑 → 引用而非复验; "
     "E5 中仅用其 Unicorn T 值作 sim 代理指标"),
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
    lines.append("| scheme.md 声明 | 验证实验 | 状态 | 依据 |")
    lines.append("|---|---|---|---|")
    for claim, exp, status, detail in SCHEME_CLAIMS:
        lines.append(f"| {claim} | {exp} | {status} | {detail} |")
    out = "\n".join(lines) + "\n"
    print(out)

if __name__ == "__main__":
    main()

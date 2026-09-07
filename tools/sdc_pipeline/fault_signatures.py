#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""fault_signatures.py — 机器可读的故障签名模式库 (变异工具的先验层)。

对应人类可读文档 docs/fault_signature_playbook.md。同一 FS 编号在两处
内容一致: 本文件是"可执行约束" (变异器直接 import), playbook 是"可审计
叙事" (人读)。修改任何一边必须同步另一边。

数据结构 (每条模式):
  signature:    故障的识别特征 (供未来自动匹配, 现阶段主要供人/AI 检索)
  trigger_elements: 触发要素的机器参数 — 变异器从中取结构约束
  negative_controls: 已证伪形态 (变异预算的黑名单: 命中即丢弃子代)
  execution_env:  检出所需执行环境 (评估/上板协议用)
  detection_form:  预期 SiliFuzz 检出形态 (判定与统计口径)

收录标准 (与 playbook 一致, 缺一不入):
  真机检出 + 健康对照 + checksum MATCH + 负对照界定。
"""

# ---------------------------------------------------------------------------
# FS-001: load 数据返回通路时序边界缺陷
# 案例: 0102 (172.168.160.42, 192 核 HIP08) cpu179 (PkgID 19062 / NUMA node7)
# 确证: 2026-09-05 MRU 复现 (1.3%~5.1%/1000) + loadsink 快照化检出 (4/11 轮)
# 详见 docs/fault_signature_playbook.md FS-001
# ---------------------------------------------------------------------------
FS001 = {
    "fs_id": "FS-001",
    "title": "load 数据返回通路时序边界缺陷",
    "case_ref": "0102/cpu179; docs/experiments/2026-09-05-core179-sdc-reproduction.md",
    "signature": {
        "corrupt_site": "load_return_path",       # 损坏发生在 load 返回组装级
        "bad_data_forms": ["stale_row_replay",    # 陈旧行回放
                           "byte_phase_skew",      # ±k·8bit 相位错位副本
                           "all_zero"],            # 全零交付
        "silent_below_ras": True,                  # 低于 EDAC/APEI/PMU 粒度
        "load_sensitive": True,                    # 单核 0% / 满载 0.5%~5%
        "sdc_outcome_shape": [2, 3],               # MEMORY_MISMATCH 为主, REGISTER 次之
    },
    # 触发要素 — LoadPathMutator 的结构参数空间
    "trigger_elements": {
        "indirect_chain": {          # 要素①: 间接寻址链
            "levels": [2],           # ldrsw 索引 → ldr 数据 两级
            "index_scale": [2, 3],   # lsl #2 (int32 索引) / lsl #3 (double 数据)
        },
        "roundtrip": True,           # 要素②: load→FMA→store 同址往返
        "fma_ops": ["fmsub", "fmadd"],
        "long_lived_acc": "fp",      # 要素③: FP 累加器跨循环 (d4 模式)
        "cond_branch_fp_div": 0.5,   # 要素④: fdiv 出现概率
        "min_loads_per_round": 8,    # 每轮 gather 链下限 (负对照: 纯 FMA 0 触发)
    },
    # 负对照 — 变异预算黑名单 (11 个已证伪形态, 生成时命中即拒)
    "negative_controls": [
        "pure_fma", "pure_gather", "pure_branch", "pure_neon",
        "dense_gemm", "dense_svd", "pure_c_sparse_rewrite",
        "l1d_cold_pressure", "triangular_solve", "reg_only_chain", "crc_int",
    ],
    # 执行环境 — 评估与上板协议
    "execution_env": {
        "required": ["same_socket_full_load"],   # ≥47 核 burner (低压近似)
        "forbidden": ["single_core_only"],        # 单核评估必然漏检
        "target_core_policy": "pin_faulty_core",
        "controls": ["healthy_core_same_load", "same_window_mru"],
    },
    "detection_form": {
        "siliFuzz_outcomes": [2, 3],
        "checksum_must_match": True,   # postfailure_checksum_status=1 (排除 corpus 损坏)
        "expected_rate_hint": "4/11 rounds @150k-200k iters (loadsink)",
    },
}

# 模式注册表 — 新案例确证后在此追加 FS-XXX
FAULT_SIGNATURES = {FS001["fs_id"]: FS001}


def negative_control_tags() -> set:
    """全部负对照标签集合 (变异器产线过滤用)。"""
    tags = set()
    for fs in FAULT_SIGNATURES.values():
        tags.update(fs["negative_controls"])
    return tags


def get(fs_id: str) -> dict:
    return FAULT_SIGNATURES[fs_id]

# sdcfuzz 实验验证报告

生成: 2026-09-03 (由 tools/sdc_experiment/report.py 自动汇总)

## 诚实声明
- gem5 O3 模型 ≠ TSV110 RTL: 所有仿真 diverge 率是模型级结论
- 健康硅片上真 SDC 稀少: E3/E4 的 SDC=0 是预期结果, 不是方法失败
- E5 是组粒度执行健康度关联 (Sim 代理指标混合), 非 SDC 率直接关联
- 每个实验的判定标准在运行前预注册, 未达标者如实记录


## exp00-smoke-j2


### sim_B_bit.json
```json
{
  "group": "B",
  "mode": "bit",
  "n": 3,
  "clean_diverge": 0,
  "masked": 2,
  "exit_diverge": 0,
  "no_output": 1,
  "diverge_rate": 0.0,
  "wilson_low": 0.0,
  "wilson_high": 0.5615,
  "seed": 99,
  "jobs": 2,
  "host": "local-0103-gem5",
  "gem5_note": "gem5 O3 model, not TSV110 RTL"
}
```


## exp00-smoke


### sim_B_bit.json
```json
{
  "group": "B",
  "mode": "bit",
  "n": 3,
  "clean_diverge": 0,
  "masked": 2,
  "exit_diverge": 0,
  "no_output": 1,
  "diverge_rate": 0.0,
  "wilson_low": 0.0,
  "wilson_high": 0.5615,
  "seed": 99,
  "jobs": 1,
  "host": "local-0103-gem5",
  "gem5_note": "gem5 O3 model, not TSV110 RTL"
}
```


## exp01-baseline-repro

```json
{
  "A": {
    "group": "A",
    "mode": "bit",
    "n": 100,
    "clean_diverge": 5,
    "masked": 88,
    "exit_diverge": 0,
    "no_output": 7,
    "diverge_rate": 0.05,
    "wilson_low": 0.0215,
    "wilson_high": 0.1118,
    "seed": 42,
    "jobs": 3,
    "host": "local-0103-gem5",
    "gem5_note": "gem5 O3 model, not TSV110 RTL"
  },
  "B": {
    "group": "B",
    "mode": "bit",
    "n": 100,
    "clean_diverge": 7,
    "masked": 89,
    "exit_diverge": 0,
    "no_output": 4,
    "diverge_rate": 0.07,
    "wilson_low": 0.0343,
    "wilson_high": 0.1375,
    "seed": 42,
    "jobs": 3,
    "host": "local-0103-gem5",
    "gem5_note": "gem5 O3 model, not TSV110 RTL"
  },
  "B_over_A_ratio": 1.4,
  "fisher_p": 0.7673444346426933,
  "verdict": "NOT_REPRODUCED(诚实记录)",
  "note": "gem5 O3 model, not TSV110 RTL; 对照 F3: A=3.9%, B=8.0%"
}
```


### sim_A_bit.json
```json
{
  "group": "A",
  "mode": "bit",
  "n": 100,
  "clean_diverge": 5,
  "masked": 88,
  "exit_diverge": 0,
  "no_output": 7,
  "diverge_rate": 0.05,
  "wilson_low": 0.0215,
  "wilson_high": 0.1118,
  "seed": 42,
  "jobs": 3,
  "host": "local-0103-gem5",
  "gem5_note": "gem5 O3 model, not TSV110 RTL"
}
```


### sim_B_bit.json
```json
{
  "group": "B",
  "mode": "bit",
  "n": 100,
  "clean_diverge": 7,
  "masked": 89,
  "exit_diverge": 0,
  "no_output": 4,
  "diverge_rate": 0.07,
  "wilson_low": 0.0343,
  "wilson_high": 0.1375,
  "seed": 42,
  "jobs": 3,
  "host": "local-0103-gem5",
  "gem5_note": "gem5 O3 model, not TSV110 RTL"
}
```


## exp02-d13-vs-random

```json
{
  "bit": {
    "B": {
      "group": "B",
      "mode": "bit",
      "n": 100,
      "clean_diverge": 7,
      "masked": 89,
      "exit_diverge": 0,
      "no_output": 4,
      "diverge_rate": 0.07,
      "wilson_low": 0.0343,
      "wilson_high": 0.1375,
      "seed": 42,
      "jobs": 3,
      "host": "local-0103-gem5",
      "gem5_note": "gem5 O3 model, not TSV110 RTL"
    },
    "D13": {
      "group": "D13",
      "mode": "bit",
      "n": 100,
      "clean_diverge": 22,
      "masked": 72,
      "exit_diverge": 0,
      "no_output": 6,
      "diverge_rate": 0.22,
      "wilson_low": 0.15,
      "wilson_high": 0.3107,
      "seed": 42,
      "jobs": 3,
      "host": "local-0103-gem5",
      "gem5_note": "gem5 O3 model, not TSV110 RTL"
    },
    "D_over_B": 3.143,
    "fisher_p": 0.004287767127721262,
    "verdict": "BEAT"
  },
  "struct": {
    "B": {
      "group": "B",
      "mode": "struct",
      "n": 100,
      "clean_diverge": 5,
      "masked": 79,
      "exit_diverge": 0,
      "no_output": 16,
      "diverge_rate": 0.05,
      "wilson_low": 0.0215,
      "wilson_high": 0.1118,
      "seed": 42,
      "jobs": 3,
      "host": "local-0103-gem5",
      "gem5_note": "gem5 O3 model, not TSV110 RTL"
    },
    "D13": {
      "group": "D13",
      "mode": "struct",
      "n": 100,
      "clean_diverge": 64,
      "masked": 32,
      "exit_diverge": 0,
      "no_output": 4,
      "diverge_rate": 0.64,
      "wilson_low": 0.5424,
      "wilson_high": 0.7273,
      "seed": 42,
      "jobs": 3,
      "host": "local-0103-gem5",
      "gem5_note": "gem5 O3 model, not TSV110 RTL"
    },
    "D_over_B": 12.8,
    "fisher_p": 5.633888033371357e-20,
    "verdict": "BEAT"
  }
}
```


### sim_B_bit.json
```json
{
  "group": "B",
  "mode": "bit",
  "n": 100,
  "clean_diverge": 7,
  "masked": 89,
  "exit_diverge": 0,
  "no_output": 4,
  "diverge_rate": 0.07,
  "wilson_low": 0.0343,
  "wilson_high": 0.1375,
  "seed": 42,
  "jobs": 3,
  "host": "local-0103-gem5",
  "gem5_note": "gem5 O3 model, not TSV110 RTL"
}
```


### sim_B_struct.json
```json
{
  "group": "B",
  "mode": "struct",
  "n": 100,
  "clean_diverge": 5,
  "masked": 79,
  "exit_diverge": 0,
  "no_output": 16,
  "diverge_rate": 0.05,
  "wilson_low": 0.0215,
  "wilson_high": 0.1118,
  "seed": 42,
  "jobs": 3,
  "host": "local-0103-gem5",
  "gem5_note": "gem5 O3 model, not TSV110 RTL"
}
```


### sim_D13_bit.json
```json
{
  "group": "D13",
  "mode": "bit",
  "n": 100,
  "clean_diverge": 22,
  "masked": 72,
  "exit_diverge": 0,
  "no_output": 6,
  "diverge_rate": 0.22,
  "wilson_low": 0.15,
  "wilson_high": 0.3107,
  "seed": 42,
  "jobs": 3,
  "host": "local-0103-gem5",
  "gem5_note": "gem5 O3 model, not TSV110 RTL"
}
```


### sim_D13_struct.json
```json
{
  "group": "D13",
  "mode": "struct",
  "n": 100,
  "clean_diverge": 64,
  "masked": 32,
  "exit_diverge": 0,
  "no_output": 4,
  "diverge_rate": 0.64,
  "wilson_low": 0.5424,
  "wilson_high": 0.7273,
  "seed": 42,
  "jobs": 3,
  "host": "local-0103-gem5",
  "gem5_note": "gem5 O3 model, not TSV110 RTL"
}
```


## exp03-corpus-hw-local

```json
{
  "result": {
    "sigsegv_noise": 0,
    "sigterm": 0,
    "runaway_noise": 0,
    "misbehave_noise": 0,
    "sdc_hits": 0,
    "sdc_details": [],
    "total_failed": 0,
    "scan_work_dir": "/tmp/sdc_scan_1788354603",
    "device": "local-0103",
    "max_cpus": 8,
    "duration_s": 1800,
    "corpus": "output/experiments/exp03-corpus-hw-local/corpus",
    "orch_rc": 0,
    "scan_wall_s": 1800,
    "v1_summary": {
      "issues_detected": 0,
      "play_count": 3840,
      "runaway_count": 0
    },
    "archived_log": "output/experiments/hw_scan_logs/local-0103_1788354603.scan.log"
  },
  "noise_fully_classified": true,
  "v1_cross_check": {
    "parse_failed_minus_runaway": 0,
    "v1_issues_detected": 0,
    "parse_runaway": 0,
    "v1_runaway_count": 0,
    "match": true
  },
  "verdict": "HW_SCAN_OK"
}
```


### hw_local-0103.json
```json
{
  "sigsegv_noise": 0,
  "sigterm": 0,
  "runaway_noise": 0,
  "misbehave_noise": 0,
  "sdc_hits": 0,
  "sdc_details": [],
  "total_failed": 0,
  "scan_work_dir": "/tmp/sdc_scan_1788354603",
  "device": "local-0103",
  "max_cpus": 8,
  "duration_s": 1800,
  "corpus": "output/experiments/exp03-corpus-hw-local/corpus",
  "orch_rc": 0,
  "scan_wall_s": 1800,
  "v1_summary": {
    "issues_detected": 0,
    "play_count": 3840,
    "runaway_count": 0
  },
  "archived_log": "output/experiments/hw_scan_logs/local-0103_1788354603.scan.log"
}
```


## exp04-remote-0101

```json
{
  "result": {
    "sigsegv_noise": 0,
    "sigterm": 0,
    "runaway_noise": 0,
    "misbehave_noise": 0,
    "sdc_hits": 0,
    "sdc_details": [],
    "total_failed": 0,
    "scan_work_dir": "/tmp/sdc_scan_1788360829",
    "device": "0101",
    "max_cpus": 8,
    "duration_s": 600,
    "corpus": "/sdc_corpus/corpus",
    "orch_rc": 0,
    "scan_wall_s": 601,
    "v1_summary": {
      "issues_detected": 0,
      "play_count": 1281,
      "runaway_count": 0
    },
    "archived_log": "output/experiments/hw_scan_logs/0101_1788360830.scan.log"
  },
  "verdict": "REMOTE_CHAIN_OK",
  "noise_fully_classified": true,
  "v1_cross_check": {
    "parse_failed_minus_runaway": 0,
    "v1_issues_detected": 0,
    "parse_runaway": 0,
    "v1_runaway_count": 0,
    "match": true
  },
  "probe": {
    "reachable": true,
    "arch": "aarch64",
    "cores": 126,
    "mem_gb": 29,
    "os": "NAME=\"openEuler\"",
    "specs_ok": true,
    "errors": [],
    "gem5": true
  },
  "deploy": {
    "device": "0101",
    "tools": {
      "snap_tool": "skip(md5 match)",
      "simple_fix_tool_main": "skip(md5 match)",
      "reading_runner_main_nolibc": "skip(md5 match)",
      "silifuzz_orchestrator_main": "skip(md5 match)",
      "silifuzz_platform_id": "skip(md5 match)"
    },
    "probe_output": {
      "snap_tool": "/etc/profile.d/mpich-aarch64.sh: 行 1: module: 未找到命令\nsnap_tool: Warning: SetProgramUsageMessage() never called",
      "simple_fix_tool_main": "/etc/profile.d/mpich-aarch64.sh: 行 1: module: 未找到命令\nsimple_fix_tool_main: Warning: SetProgramUsageMessage() never called",
      "reading_runner_main_nolibc": "/etc/profile.d/mpich-aarch64.sh: 行 1: module: 未找到命令\nI<DATE> <PID> runner_flags.cc:47] Usage: /sdc_tools/reading_runner_main_nolibc <flags>... [corpus file]",
      "silifuzz_orchestrator_main": "/etc/profile.d/mpich-aarch64.sh: 行 1: module: 未找到命令\nsilifuzz_orchestrator_main: Warning: SetProgramUsageMessage() never called",
      "silifuzz_platform_id": "/etc/profile.d/mpich-aarch64.sh: 行 1: module: 未找到命令\nsilifuzz_platform_id: Warning: SetProgramUsageMessage() never called"
    },
    "corpus": {
      "remote": "/sdc_corpus",
      "ok": false
    }
  }
}
```


### deploy.json
```json
{"device": "0101", "tools": {"snap_tool": "skip(md5 match)", "simple_fix_tool_main": "skip(md5 match)", "reading_runner_main_nolibc": "skip(md5 match)", "silifuzz_orchestrator_main": "skip(md5 match)", "silifuzz_platform_id": "skip(md5 match)"}, "probe_output": {"snap_tool": "/etc/profile.d/mpich-aarch64.sh: 行 1: module: 未找到命令\nsnap_tool: Warning: SetProgramUsageMessage() never called", "simple_fix_tool_main": "/etc/profile.d/mpich-aarch64.sh: 行 1: module: 未找到命令\nsimple_fix_tool_main: Warning: SetProgramUsageMessage() never called", "reading_runner_main_nolibc": "/etc/profile.d/mpich-aarch64.sh: 行 1: module: 未找到命令\nI<DATE> <PID> runner_flags.cc:47] Usage: /sdc_tools/reading_runner_main_nolibc <flags>... [corpus file]", "silifuzz_orchestrator_main": "/etc/profile.d/mpich-aarch64.sh: 行 1: module: 未找到命令\nsilifuzz_orchestrator_main: Warning: SetProgramUsageMessage() never called", "silifuzz_platform_id": "/etc/profile.d/mpich-aarch64.sh: 行 1: module: 未找到命令\nsilifuzz_platform_id: Warning: SetProgramUsageMessage() never called"}, "corpus": {"remote": "/sdc_corpus", "ok": false}}
```


### hw_0101.json
```json
{
  "sigsegv_noise": 0,
  "sigterm": 0,
  "runaway_noise": 0,
  "misbehave_noise": 0,
  "sdc_hits": 0,
  "sdc_details": [],
  "total_failed": 0,
  "scan_work_dir": "/tmp/sdc_scan_1788360829",
  "device": "0101",
  "max_cpus": 8,
  "duration_s": 600,
  "corpus": "/sdc_corpus/corpus",
  "orch_rc": 0,
  "scan_wall_s": 601,
  "v1_summary": {
    "issues_detected": 0,
    "play_count": 1281,
    "runaway_count": 0
  },
  "archived_log": "output/experiments/hw_scan_logs/0101_1788360830.scan.log"
}
```


### probe.json
```json
{
  "reachable": true,
  "arch": "aarch64",
  "cores": 126,
  "mem_gb": 29,
  "os": "NAME=\"openEuler\"",
  "specs_ok": true,
  "errors": [],
  "gem5": true
}
```


## exp05-crosslayer

```json
{
  "sim_rows": [
    {
      "group": "A",
      "sim_diverge_rate": 0.0333,
      "sim_masked_rate": 0.8333
    },
    {
      "group": "B",
      "sim_diverge_rate": 0.0,
      "sim_masked_rate": 0.9333
    },
    {
      "group": "D13",
      "sim_diverge_rate": 0.3,
      "sim_masked_rate": 0.6667
    },
    {
      "group": "c1_l2_eviction",
      "sim_diverge_rate": 0.32,
      "sim_masked_rate": 0.0,
      "proxy": "unicorn_T"
    },
    {
      "group": "c3_l3_128b",
      "sim_diverge_rate": 0.61,
      "sim_masked_rate": 0.0,
      "proxy": "unicorn_T"
    },
    {
      "group": "e1_carry_chain",
      "sim_diverge_rate": 0.76,
      "sim_masked_rate": 0.0,
      "proxy": "unicorn_T"
    },
    {
      "group": "e2_mul_extreme",
      "sim_diverge_rate": 0.755,
      "sim_masked_rate": 0.0,
      "proxy": "unicorn_T"
    },
    {
      "group": "e3_toggle_rate",
      "sim_diverge_rate": 0.64,
      "sim_masked_rate": 0.0,
      "proxy": "unicorn_T"
    },
    {
      "group": "f1_subnormal_nan",
      "sim_diverge_rate": 0.76,
      "sim_masked_rate": 0.0,
      "proxy": "unicorn_T"
    },
    {
      "group": "i1_icache_boundary",
      "sim_diverge_rate": 0.17,
      "sim_masked_rate": 0.0,
      "proxy": "unicorn_T"
    },
    {
      "group": "i2_branch_dense",
      "sim_diverge_rate": 0.32,
      "sim_masked_rate": 0.0,
      "proxy": "unicorn_T"
    },
    {
      "group": "l1_disambig",
      "sim_diverge_rate": 0.32,
      "sim_masked_rate": 0.0,
      "proxy": "unicorn_T"
    },
    {
      "group": "l2_dualagu_split",
      "sim_diverge_rate": 0.61,
      "sim_masked_rate": 0.0,
      "proxy": "unicorn_T"
    },
    {
      "group": "m1_tlb_thrash",
      "sim_diverge_rate": 0.0,
      "sim_masked_rate": 0.0,
      "proxy": "unicorn_T"
    },
    {
      "group": "m3_cross_page",
      "sim_diverge_rate": 0.61,
      "sim_masked_rate": 0.0,
      "proxy": "unicorn_T"
    }
  ],
  "hw_rows": [
    {
      "group": "c1_l2_eviction",
      "hw_throughput_per_s": 0.8,
      "hw_runaway_rate": 0.056666666666666664,
      "hw_misbehave_rate": 0.0,
      "hw_sdc": 0,
      "play_count": 480,
      "hw_failure_count": 35,
      "orch_rc": 0,
      "v1_runaway_count": 37,
      "v1_discrepancy": "v1 runaway_count=37 != 文本解析 34 (interleaved-log 欠计数, rank-insensitive; hw_runaway_rate 维持文本解析值)"
    },
    {
      "group": "c3_l3_128b",
      "hw_throughput_per_s": 2.04,
      "hw_runaway_rate": 0.0,
      "hw_misbehave_rate": 0.0,
      "hw_sdc": 0,
      "play_count": 1224,
      "hw_failure_count": 0,
      "orch_rc": 0,
      "v1_runaway_count": 0
    },
    {
      "group": "e1_carry_chain",
      "hw_throughput_per_s": 3.2717,
      "hw_runaway_rate": 0.0,
      "hw_misbehave_rate": 0.0,
      "hw_sdc": 0,
      "play_count": 1963,
      "hw_failure_count": 0,
      "orch_rc": 0,
      "v1_runaway_count": 0
    },
    {
      "group": "e2_mul_extreme",
      "hw_throughput_per_s": 3.28,
      "hw_runaway_rate": 0.0,
      "hw_misbehave_rate": 0.0,
      "hw_sdc": 0,
      "play_count": 1968,
      "hw_failure_count": 0,
      "orch_rc": 0,
      "v1_runaway_count": 0
    },
    {
      "group": "e3_toggle_rate",
      "hw_throughput_per_s": 3.26,
      "hw_runaway_rate": 0.0,
      "hw_misbehave_rate": 0.0,
      "hw_sdc": 0,
      "play_count": 1956,
      "hw_failure_count": 0,
      "orch_rc": 0,
      "v1_runaway_count": 0
    },
    {
      "group": "f1_subnormal_nan",
      "hw_throughput_per_s": 3.265,
      "hw_runaway_rate": 0.0,
      "hw_misbehave_rate": 0.0,
      "hw_sdc": 0,
      "play_count": 1959,
      "hw_failure_count": 0,
      "orch_rc": 0,
      "v1_runaway_count": 0
    },
    {
      "group": "i1_icache_boundary",
      "hw_throughput_per_s": 3.23,
      "hw_runaway_rate": 0.0,
      "hw_misbehave_rate": 0.0,
      "hw_sdc": 0,
      "play_count": 1938,
      "hw_failure_count": 0,
      "orch_rc": 0,
      "v1_runaway_count": 0
    },
    {
      "group": "i2_branch_dense",
      "hw_throughput_per_s": 3.0517,
      "hw_runaway_rate": 0.0,
      "hw_misbehave_rate": 0.0,
      "hw_sdc": 0,
      "play_count": 1831,
      "hw_failure_count": 0,
      "orch_rc": 0,
      "v1_runaway_count": 0
    },
    {
      "group": "l1_disambig",
      "hw_throughput_per_s": 2.26,
      "hw_runaway_rate": 0.0,
      "hw_misbehave_rate": 0.0,
      "hw_sdc": 0,
      "play_count": 1356,
      "hw_failure_count": 0,
      "orch_rc": 0,
      "v1_runaway_count": 0
    },
    {
      "group": "l2_dualagu_split",
      "hw_throughput_per_s": 2.1817,
      "hw_runaway_rate": 0.0,
      "hw_misbehave_rate": 0.0,
      "hw_sdc": 0,
      "play_count": 1309,
      "hw_failure_count": 0,
      "orch_rc": 0,
      "v1_runaway_count": 0
    },
    {
      "group": "m1_tlb_thrash",
      "hw_throughput_per_s": 1.0533,
      "hw_runaway_rate": 0.0,
      "hw_misbehave_rate": 0.0,
      "hw_sdc": 0,
      "play_count": 632,
      "hw_failure_count": 0,
      "orch_rc": 0,
      "v1_runaway_count": 0
    },
    {
      "group": "m3_cross_page",
      "hw_throughput_per_s": 1.6267,
      "hw_runaway_rate": 0.0,
      "hw_misbehave_rate": 0.0,
      "hw_sdc": 0,
      "play_count": 976,
      "hw_failure_count": 0,
      "orch_rc": 0,
      "v1_runaway_count": 0
    }
  ],
  "analysis": {
    "n": 12,
    "sim_key": "sim_diverge_rate",
    "hw_key": "hw_runaway_rate",
    "spearman_rho": -0.2219,
    "permutation_p": 0.74733,
    "verdict": "NOT_SIGNIFICANT(诚实记录)",
    "note": "12 组 sim 值为 Unicorn T 代理指标(T/200, 计划指定), 非 gem5 diverge 率; 组粒度执行健康度关联; gem5 O3 ≠ TSV110 RTL; 真SDC关联需检出样本后再做"
  }
}
```


### hw_rows.json
```json
[
  {
    "group": "c1_l2_eviction",
    "hw_throughput_per_s": 0.8,
    "hw_runaway_rate": 0.056666666666666664,
    "hw_misbehave_rate": 0.0,
    "hw_sdc": 0,
    "play_count": 480,
    "hw_failure_count": 35,
    "orch_rc": 0,
    "v1_runaway_count": 37,
    "v1_discrepancy": "v1 runaway_count=37 != 文本解析 34 (interleaved-log 欠计数, rank-insensitive; hw_runaway_rate 维持文本解析值)"
  },
  {
    "group": "c3_l3_128b",
    "hw_throughput_per_s": 2.04,
    "hw_runaway_rate": 0.0,
    "hw_misbehave_rate": 0.0,
    "hw_sdc": 0,
    "play_count": 1224,
    "hw_failure_count": 0,
    "orch_rc": 0,
    "v1_runaway_count": 0
  },
  {
    "group": "e1_carry_chain",
    "hw_throughput_per_s": 3.2717,
    "hw_runaway_rate": 0.0,
    "hw_misbehave_rate": 0.0,
    "hw_sdc": 0,
    "play_count": 1963,
    "hw_failure_count": 0,
    "orch_rc": 0,
    "v1_runaway_count": 0
  },
  {
    "group": "e2_mul_extreme",
    "hw_throughput_per_s": 3.28,
    "hw_runaway_rate": 0.0,
    "hw_misbehave_rate": 0.0,
    "hw_sdc": 0,
    "play_count": 1968,
    "hw_failure_count": 0,
    "orch_rc": 0,
    "v1_runaway_count": 0
  },
  {
    "group": "e3_toggle_rate",
    "hw_throughput_per_s": 3.26,
    "hw_runaway_rate": 0.0,
    "hw_misbehave_rate": 0.0,
    "hw_sdc": 0,
    "play_count": 1956,
    "hw_failure_count": 0,
    "orch_rc": 0,
    "v1_runaway_count": 0
  },
  {
    "group": "f1_subnormal_nan",
    "hw_throughput_per_s": 3.265,
    "hw_runaway_rate": 0.0,
    "hw_misbehave_rate": 0.0,
    "hw_sdc": 0,
    "play_count": 1959,
    "hw_failure_count": 0,
    "orch_rc": 0,
    "v1_runaway_count": 0
  },
  {
    "group": "i1_icache_boundary",
    "hw_throughput_per_s": 3.23,
    "hw_runaway_rate": 0.0,
    "hw_misbehave_rate": 0.0,
    "hw_sdc": 0,
    "play_count": 1938,
    "hw_failure_count": 0,
    "orch_rc": 0,
    "v1_runaway_count": 0
  },
  {
    "group": "i2_branch_dense",
    "hw_throughput_per_s": 3.0517,
    "hw_runaway_rate": 0.0,
    "hw_misbehave_rate": 0.0,
    "hw_sdc": 0,
    "play_count": 1831,
    "hw_failure_count": 0,
    "orch_rc": 0,
    "v1_runaway_count": 0
  },
  {
    "group": "l1_disambig",
    "hw_throughput_per_s": 2.26,
    "hw_runaway_rate": 0.0,
    "hw_misbehave_rate": 0.0,
    "hw_sdc": 0,
    "play_count": 1356,
    "hw_failure_count": 0,
    "orch_rc": 0,
    "v1_runaway_count": 0
  },
  {
    "group": "l2_dualagu_split",
    "hw_throughput_per_s": 2.1817,
    "hw_runaway_rate": 0.0,
    "hw_misbehave_rate": 0.0,
    "hw_sdc": 0,
    "play_count": 1309,
    "hw_failure_count": 0,
    "orch_rc": 0,
    "v1_runaway_count": 0
  },
  {
    "group": "m1_tlb_thrash",
    "hw_throughput_per_s": 1.0533,
    "hw_runaway_rate": 0.0,
    "hw_misbehave_rate": 0.0,
    "hw_sdc": 0,
    "play_count": 632,
    "hw_failure_count": 0,
    "orch_rc": 0,
    "v1_runaway_count": 0
  },
  {
    "group": "m3_cross_page",
    "hw_throughput_per_s": 1.6267,
    "hw_runaway_rate": 0.0,
    "hw_misbehave_rate": 0.0,
    "hw_sdc": 0,
    "play_count": 976,
    "hw_failure_count": 0,
    "orch_rc": 0,
    "v1_runaway_count": 0
  }
]
```


### sim_rows.json
```json
[
  {
    "group": "A",
    "sim_diverge_rate": 0.0333,
    "sim_masked_rate": 0.8333
  },
  {
    "group": "B",
    "sim_diverge_rate": 0.0,
    "sim_masked_rate": 0.9333
  },
  {
    "group": "D13",
    "sim_diverge_rate": 0.3,
    "sim_masked_rate": 0.6667
  },
  {
    "group": "c1_l2_eviction",
    "sim_diverge_rate": 0.32,
    "sim_masked_rate": 0.0,
    "proxy": "unicorn_T"
  },
  {
    "group": "c3_l3_128b",
    "sim_diverge_rate": 0.61,
    "sim_masked_rate": 0.0,
    "proxy": "unicorn_T"
  },
  {
    "group": "e1_carry_chain",
    "sim_diverge_rate": 0.76,
    "sim_masked_rate": 0.0,
    "proxy": "unicorn_T"
  },
  {
    "group": "e2_mul_extreme",
    "sim_diverge_rate": 0.755,
    "sim_masked_rate": 0.0,
    "proxy": "unicorn_T"
  },
  {
    "group": "e3_toggle_rate",
    "sim_diverge_rate": 0.64,
    "sim_masked_rate": 0.0,
    "proxy": "unicorn_T"
  },
  {
    "group": "f1_subnormal_nan",
    "sim_diverge_rate": 0.76,
    "sim_masked_rate": 0.0,
    "proxy": "unicorn_T"
  },
  {
    "group": "i1_icache_boundary",
    "sim_diverge_rate": 0.17,
    "sim_masked_rate": 0.0,
    "proxy": "unicorn_T"
  },
  {
    "group": "i2_branch_dense",
    "sim_diverge_rate": 0.32,
    "sim_masked_rate": 0.0,
    "proxy": "unicorn_T"
  },
  {
    "group": "l1_disambig",
    "sim_diverge_rate": 0.32,
    "sim_masked_rate": 0.0,
    "proxy": "unicorn_T"
  },
  {
    "group": "l2_dualagu_split",
    "sim_diverge_rate": 0.61,
    "sim_masked_rate": 0.0,
    "proxy": "unicorn_T"
  },
  {
    "group": "m1_tlb_thrash",
    "sim_diverge_rate": 0.0,
    "sim_masked_rate": 0.0,
    "proxy": "unicorn_T"
  },
  {
    "group": "m3_cross_page",
    "sim_diverge_rate": 0.61,
    "sim_masked_rate": 0.0,
    "proxy": "unicorn_T"
  }
]
```


## scheme.md 声明对照表

| scheme.md 声明 | 验证实验 | 状态 | 依据 |
|---|---|---|---|
| §3.1 A/B 基线数据可复现 (B/A ≥ 1.5×) | E1 (A/B bit-flip 各100次) | 未验证 | B/A=1.4 < 1.5× 预注册阈值 → NOT_REPRODUCED(诚实记录); 方向与 F3 (B=8.0% > A=3.9%) 一致, 100-run 样本 CI 宽 |
| §3.1 D13 bit-flip 3.00× | E2 bit (D13/B 各100次) | 部分验证 | BEAT: 3.143× (p=0.00429), 方向与 F4 (3.00×) 一致; 100-run 样本 (F4 为 500-run), 幅度未达 F4 精度 |
| §3.1 D13 structural 7.79× | E2 struct (D13/B 各100次) | 部分验证 | BEAT: 12.8× (p=5.6e-20), 方向与 F4 (7.79×) 一致; 100-run 样本 (F4 为 500-run), 幅度未达 F4 精度 |
| §4.2 真机执行能力 (Snapshot/Runner/Orchestrator) | E3 (本机 0103 真跑) | 已验证 | HW_SCAN_OK: 20 模板管线, 30min 扫描, SDC=0, play_count=3840, 噪声全分类 (segv/runaway/misbehave=0), v1 交叉校验 match |
| §4.3 L3 多板分布式 + 噪声分类 | E4 (0101 远程全链路演练) | 部分验证 | REMOTE_CHAIN_OK: 单远程板 (0101) 全链路 (注册→部署→扫描→回收) 通过; 多板并行未验证 (用户设备待凭据, Step 3 待用户) |
| §4.4 Sim→HW 统计关联 | E5 (12 组组粒度关联) | 未验证 | NOT_SIGNIFICANT: ρ=-0.2219, p=0.74733 → 诚实弱化版 (组粒度健康度 关联) 也未获支持; sim 面为 Unicorn T 代理指标混用, 非 gem5 diverge 率 |
| §4.2 进化引擎 (T 8→70, 8.8×) | F5 历史数据 (E5 用其 Unicorn 代理) | 已验证(引用) | F5 (T 8→70, 8.8×) 为本分支之前的历史证据 (tools/sdc_mutator/evolution_engine.py + paper2 program), 本次未重跑 → 引用而非复验; E5 中仅用其 Unicorn T 值作 sim 代理指标 |


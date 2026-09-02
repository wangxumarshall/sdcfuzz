#!/usr/bin/env python3
"""experiment_config 单元测试。运行: python3 tools/sdc_experiment/test_experiment_config.py"""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tools.sdc_experiment.experiment_config import ExperimentConfig, load_config, default_config

def test_default_config():
    c = default_config("exp01")
    assert c.experiment_id == "exp01"
    assert c.max_cpus <= 64, "MCE 红线: max_cpus 不得超过 64"
    assert c.roi == (0.2, 0.8)
    assert c.sweep_runs >= 1
    print("PASS test_default_config")

def test_load_config_yaml():
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write("experiment_id: exp99\nsweep_runs: 123\nmax_cpus: 8\n")
        path = f.name
    c = load_config(path)
    assert c.experiment_id == "exp99" and c.sweep_runs == 123 and c.max_cpus == 8
    # 未指定字段取默认
    assert c.roi == (0.2, 0.8)
    os.unlink(path)
    print("PASS test_load_config_yaml")

def test_config_serializable():
    c = default_config("exp01")
    d = json.loads(json.dumps(c.to_dict()))
    assert d["experiment_id"] == "exp01"
    print("PASS test_config_serializable")

if __name__ == "__main__":
    test_default_config(); test_load_config_yaml(); test_config_serializable()
    print("ALL PASS")

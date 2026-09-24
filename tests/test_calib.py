"""pytest 用例：与 test_jev_calib.py（脚本式 runner）等价，但可被 pytest/CI 收集。

背景：原 test_jev_calib.py 是脚本式断言（顶层 assert + print），
     `pytest test_jev_calib.py` 会 **收集 0 项却显示绿色** → 接 CI 会假绿。
     本文件把 5 项断言改写成真正的用例，CI 才有意义（不改动原脚本，保持向后兼容）。

跑法:  PYTHONPATH=.. pytest -q
"""
import os
import statistics
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jev_calib as jc  # noqa: E402

MOCK = {
    "model": "typesafe/jev-1.13-20260917",
    "answers": {
        "worth_outreach": {"type": "noul", "noul": 0.61},
        "seniority": {"type": "score", "score": 1.13, "confidence": 0.7},
    },
    "usage": {"input_tokens": 410, "output_tokens": 39, "cost": 1.722e-05},
}

RUNS = [
    {"noul": {"a": 0.60}, "cost": 1e-5, "in_tokens": 400, "latency": 1.0},
    {"noul": {"a": 0.62}, "cost": 1e-5, "in_tokens": 400, "latency": 1.2},
    {"noul": {"a": 0.61}, "cost": 1e-5, "in_tokens": 400, "latency": 1.1},
]


def test_parse_response():
    parsed = jc.parse_response(MOCK)
    assert parsed["noul"]["worth_outreach"] == 0.61
    assert parsed["score"]["seniority"] == 1.13
    assert parsed["confidence"]["seniority"] == 0.7
    assert parsed["cost"] == 1.722e-05
    assert parsed["in_tokens"] == 410


def test_aggregate_mean_std():
    agg = jc.aggregate(RUNS, threshold=0.05)
    assert abs(agg["a"]["mean"] - 0.61) < 1e-9
    assert abs(agg["a"]["std"] - statistics.pstdev([0.60, 0.62, 0.61])) < 1e-9
    assert agg["a"]["flips"] == 0
    assert abs(agg["_meta"]["avg_cost"] - 1e-5) < 1e-12


def test_flip_detection():
    runs2 = [
        {"noul": {"a": 0.10}, "cost": 1e-5, "in_tokens": 400, "latency": 1.0},
        {"noul": {"a": 0.85}, "cost": 1e-5, "in_tokens": 400, "latency": 1.0},
    ]
    agg2 = jc.aggregate(runs2, threshold=0.05)
    assert agg2["a"]["flips"] == 1, "漂移 0.75 > 0.05 应算翻转"
    assert agg2["a"]["max_delta"] == 0.75


def test_report_contains_key_fields():
    agg = jc.aggregate(RUNS, threshold=0.05)
    md = jc.report(agg, model="jev-test", runs=3)
    assert "jev-test" in md and "mean" in md and "flips" in md


def test_jevkit_integration(monkeypatch):
    """call_jev 走 jevkit SDK 层（mock Client.decide，不联网）。"""
    jevkit = pytest.importorskip("jevkit")
    calls = []

    def fake_decide(self, questions, state="", timeout=30):
        calls.append((questions, state))
        return {"model": "typesafe/jev-1.13",
                "answers": {"worth_outreach": {"type": "noul", "noul": 0.61}},
                "usage": {"input_tokens": 410, "output_tokens": 39, "cost": 1.722e-05}}

    monkeypatch.setattr(jevkit.Client, "decide", fake_decide)
    monkeypatch.setattr(jc, "_client", None, raising=False)
    parsed, latency = jc.call_jev({"lead": "x"}, {"worth_outreach": {"type": "noul"}}, api_key="sk-test")
    assert parsed["noul"]["worth_outreach"] == 0.61
    assert parsed["cost"] == 1.722e-05
    assert len(calls) == 1 and calls[0][1] == {"lead": "x"}, "state 未透传给 jevkit"
    assert latency >= 0
    monkeypatch.setattr(jc, "_client", None, raising=False)

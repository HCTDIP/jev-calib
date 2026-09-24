"""RED: jev-calib v0.1 测试（mock 响应，无网络）"""
import json, statistics
import jev_calib as jc

# --- 测试 1: mock 响应解析 ---
mock = {
    "model": "typesafe/jev-1.13-20260917",
    "answers": {
        "worth_outreach": {"type": "noul", "noul": 0.61},
        "seniority": {"type": "score", "score": 1.13, "confidence": 0.7},
    },
    "usage": {"input_tokens": 410, "output_tokens": 39, "cost": 1.722e-05},
}
parsed = jc.parse_response(mock)
assert parsed["noul"]["worth_outreach"] == 0.61, "noul 解析错误"
assert parsed["score"]["seniority"] == 1.13, "score 解析错误"
assert parsed["confidence"]["seniority"] == 0.7, "confidence 解析错误"
assert parsed["cost"] == 1.722e-05 and parsed["in_tokens"] == 410, "usage 解析错误"

# --- 测试 2: 聚合统计（mean/std/翻转率）---
runs = [
    {"noul": {"a": 0.60}, "cost": 1e-5, "in_tokens": 400, "latency": 1.0},
    {"noul": {"a": 0.62}, "cost": 1e-5, "in_tokens": 400, "latency": 1.2},
    {"noul": {"a": 0.61}, "cost": 1e-5, "in_tokens": 400, "latency": 1.1},
]
agg = jc.aggregate(runs, threshold=0.05)
assert abs(agg["a"]["mean"] - 0.61) < 1e-9, "mean 错误"
assert abs(agg["a"]["std"] - statistics.pstdev([0.60, 0.62, 0.61])) < 1e-9, "std 错误"
assert agg["a"]["flips"] == 0, "不该有翻转"
assert abs(agg["_meta"]["avg_cost"] - 1e-5) < 1e-12, "avg_cost 错误"

# --- 测试 3: 翻转检测（漂移 > 阈值）---
runs2 = [
    {"noul": {"a": 0.10}, "cost": 1e-5, "in_tokens": 400, "latency": 1.0},
    {"noul": {"a": 0.85}, "cost": 1e-5, "in_tokens": 400, "latency": 1.0},
]
agg2 = jc.aggregate(runs2, threshold=0.05)
assert agg2["a"]["flips"] == 1, "漂移 0.75 > 0.05 应算翻转"
assert agg2["a"]["max_delta"] == 0.75, "max_delta 错误"

# --- 测试 4: 报告生成 ---
md = jc.report(agg, model="jev-test", runs=3)
assert "jev-test" in md and "mean" in md and "flips" in md, "报告缺关键字段"

# --- 测试 5: jevkit 集成（call_jev 走 SDK 层，mock Client.decide）---
import jevkit
_calls = []
def fake_decide(self, questions, state="", timeout=30):
    _calls.append((questions, state))
    return {"model": "typesafe/jev-1.13",
            "answers": {"worth_outreach": {"type": "noul", "noul": 0.61}},
            "usage": {"input_tokens": 410, "output_tokens": 39, "cost": 1.722e-05}}
jevkit.Client.decide = fake_decide
jc._client = None  # reset lazy client
parsed, latency = jc.call_jev({"lead": "x"}, {"worth_outreach": {"type": "noul"}}, api_key="sk-test")
assert parsed["noul"]["worth_outreach"] == 0.61, "jevkit 集成解析错误"
assert parsed["cost"] == 1.722e-05, "jevkit 集成 cost 错误"
assert len(_calls) == 1 and _calls[0][1] == {"lead": "x"}, "state 未透传给 jevkit"
assert latency >= 0, "latency 应非负"
jc._client = None  # cleanup for后续

print("ALL 5 TESTS PASSED ✓")

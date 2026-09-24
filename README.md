# jev-calib

Calibration observability for [TypeSafe's Jev](https://docs.typesafe.ai) — the "System One" decision model. Runs the same state + questions N times, measures repeatability (mean/std), detects calibration drift (flip rate), and reports cost/latency. Code owns the workflow; Jev answers narrow judgments.

> Niche note: GitHub had **zero** results for "jev observability / calibration" as of 2026-09-22 — the first monitoring tool in the Jev ecosystem.

**v0.2**: the HTTP layer now reuses [jevkit](https://github.com/HCTDIP/jevkit) (the Jev ecosystem's Python SDK). Monitoring layer stays dependency-thin: parse → aggregate → report.

## Quick start

```sh
git clone https://github.com/HCTDIP/jevkit.git
git clone https://github.com/HCTDIP/jev-calib.git && cd jev-calib

export OPENROUTER_API_KEY=sk-or-v1-...
PYTHONPATH=../jevkit python3 jev_calib.py --config cases.json --runs 5          # live
PYTHONPATH=../jevkit python3 jev_calib.py --config cases.json --runs 5 --dry-run  # mock, no network
```

## What it measures

| Metric | Meaning |
|---|---|
| mean / std | per-question repeatability across N runs |
| max_delta / flips | calibration drift (max_delta > threshold → flip ⚠️) |
| total_cost / avg_latency | spend + latency per run |

Output: `calib_report.md` (Markdown, CI/issue-ready).

`--model` pins a version so you can compare calibration drift across Jev releases.

## Cases format (`cases.json`)

```json
[{"name": "lead-worth",
  "state": {"lead": {"title": "...", "points": 42}},
  "questions": {"worth_outreach": {"type": "noul", "instructions": "...", "criteria": {"true": "...", "false": "..."}}}}]
```

## Known Jev behaviors (measured)

- Repeats are tight, not exact (std ≈ 0.01 on simple nouls)
- Borderline cases flip (max_delta up to 0.75) — jev-lab observed the same
- OpenRouter adapter accepts strings only in `instructions`/`criteria`
- 3 runs over a 1-question state: ~$0.00004, ~0.9s

## Tests

```sh
PYTHONPATH=../jevkit python3 test_jev_calib.py   # 5 tests, mock responses, no network
```

MIT License.

---

## v0.2 变更（2026-09-25）

- **CI 上线**：`.github/workflows/ci.yml` —— 拉兄弟仓 jevkit → `pytest -q` → 脚本 runner → mock 校准冒烟；有 `OPENROUTER_API_KEY` secret 时再跑真调用。
- **修「假绿」**：原 `test_jev_calib.py` 是脚本式断言，`pytest` 收集 **0 项却显示绿色**（接 CI 会假绿）。
  现补 `tests/test_calib.py`（真用例）+ `conftest.py`（自动把 `../jevkit` 加进 `sys.path`）→ `pytest -q` 收集 **5 项，5 passed**。
- **漂移账本**：`track.py` + `calib_history.jsonl` —— 跑一轮 → 解析报告 → 入库 → 打印跨轮趋势与轮间 Δmean（单轮只证明"这一次稳"，跨轮才看得出有没有漂）。

## Jev decisions 调用形状（实测，v0.1 client 未覆盖）

三种问题类型**都必须带 `criteria`**，形状不同：

| type | criteria 形状 | 返回 |
|---|---|---|
| `noul` | `{"true": 描述, "false": 描述}` | `{"noul": 0.0~1.0}` |
| `score` | `[anchor, anchor, ...]`（数组） | `{"score": 期望锚点序号 0..N-1, "legend": {...}, "probabilities": {...}}` |
| `choice` | `{选项: 描述}`（键即选项，无需 `options`） | `{"choice": 键, "probabilities": {...}, "confidence": ...}` |

> ⚠️ `score.score` **不是 0–1 归一值**，是"期望锚点序号"（5 个锚点 → 0..4），用前必须 `/(N-1)` 归一化。
> ⚠️ 缺 `criteria` 直接 HTTP 400，报错 path 指向 `criteria`，可据此反推字段。

## 跨轮漂移实测（2026-09-22 → 09-25）

| 时间 | mean | std | max_delta | flips | 轮间 Δmean |
|---|---|---|---|---|---|
| 09-22 | 0.3733 | 0.0094 | 0.02 | 0 | — |
| 09-24 | 0.3700 | 0.0082 | 0.02 | 0 | -0.0033 |
| 09-25 | 0.3767 | 0.0094 | 0.02 | 0 | +0.0067 |

→ 三天跨度内 **无漂移**（Δ 全在 ±0.007，flips 全 0）。

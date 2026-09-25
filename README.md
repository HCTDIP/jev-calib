# jev-calib

> **Project: [Jeveto](https://github.com/HCTDIP/jeveto)** — 置信度门控的 Agent 决策层
> 生态三仓：**[jeveto](https://github.com/HCTDIP/jeveto)**（编排层）· **[jevkit](https://github.com/HCTDIP/jevkit)**（决策客户端）· **jev-calib**（决策监控 · 本仓）

Calibration observability for [TypeSafe's Jev](https://docs.typesafe.ai) — the "System One" decision model. Runs the same state + questions N times, measures repeatability (mean/std), detects calibration drift (flip rate), and reports cost/latency. Code owns the workflow; Jev answers narrow judgments.

> Niche note: GitHub had **zero** results for "jev observability / calibration" as of 2026-09-22 — the first monitoring tool in the Jev ecosystem.

**v0.2**: the HTTP layer reuses [jevkit](https://github.com/HCTDIP/jevkit) (the ecosystem's Python SDK). Monitoring layer stays dependency-thin: parse → aggregate → report.

---

## Quick start

```sh
git clone https://github.com/HCTDIP/jevkit.git
git clone https://github.com/HCTDIP/jev-calib.git && cd jev-calib

export OPENROUTER_API_KEY=sk-or-v1-...
python3 jev_calib.py --config cases.json --runs 5            # live（一次 ≈ $0.00004）
python3 jev_calib.py --config cases.json --runs 5 --dry-run  # mock，不联网
python3 track.py --report-only                               # 看跨轮漂移趋势（账本）
```

> 两仓并排 clone 即可，**不需要手动设 PYTHONPATH**（`conftest.py` / 导入守卫会自动找兄弟目录）。

## 三问（noul / score / choice）都能校准

`cases.json` 里每个 case 是 `{"name", "state", "questions"}`，`questions` 用 Jev 的类型化问题（**三种类型都必须带 `criteria`**）：

| type | `criteria` 形状 | 校准关注点 |
|---|---|---|
| `noul` | **record** `{"true": …, "false": …}` | 概率可重复性（mean/std）、是否在 0.5 附近翻转 |
| `score` | **array** `["锚点0", …]` | 返回的是**锚点序号 0..N-1**（不是 0–1），漂移看序号变化 |
| `choice` | **record** `{选项: 描述}` | 选中项是否稳定（flip = 换了选项） |

最小 case（noul）：
```json
[{"name":"lead-worth","state":"HN post: n8n automation, $2k budget",
  "questions":{"worth_outreach":{"type":"noul","instructions":"Is this lead worth outreach?",
    "criteria":{"true":"explicit budget + concrete need","false":"no signal"}}}}]
```
带 score + choice 的 case 见 `examples/cases_three_types.json`。

## What it measures

| Metric | Meaning |
|---|---|
| mean / std | per-question repeatability across N runs |
| max_delta / flips | calibration drift (max_delta > threshold → flip ⚠️) |
| cost / latency | per run, and totals |

## Drift ledger（跨轮账本）

单轮只证明"这一次稳"，**跨轮**才看得出有没有漂 —— `track.py` 把每次运行入账并打印趋势：

```sh
python3 track.py --runs 3          # 跑一轮 → 解析报告 → 入库 → 打印跨轮 Δmean
python3 track.py --report-only     # 只看趋势（不花钱）
```

实测（2026-09-22 → 09-25，5 轮）：mean 0.3733 → 0.3700 → 0.3767 → 0.3600，**Δ 全在 ±0.017 内、flips 全 0 → 无漂移**。

## 上游：判断用在哪

本仓只管"决策质量监控"。决策**怎么用**（三问 → GO/HOLD/DROP 闸门、证据留痕）见编排层 **[jeveto](https://github.com/HCTDIP/jeveto)** —— 其中公开战绩：蜜罐识别 **2/2 与人工尽调一致**、重复一致性 **4/4 flips=0**。

## v0.2 变更（2026-09-25）

- **CI 上线**：`.github/workflows/ci.yml` —— 拉兄弟仓 jevkit → `pytest -q` → 脚本 runner → mock 校准冒烟；有 `OPENROUTER_API_KEY` secret 时再跑真调用
- **修「假绿」**：原 `test_jev_calib.py` 是脚本式断言，`pytest` 收集 **0 项却显示绿色**（接 CI 会假绿）。现补 `tests/test_calib.py`（真用例）+ `conftest.py` → `pytest -q` 收集 **5 项全过**
- **漂移账本**：`track.py` + `calib_history.jsonl`
- **导入守卫**：`jev_calib.py` 自动找兄弟目录 `../jevkit`，裸跑即通

## Jev decisions 调用形状（实测）

三种类型**都必须带 `criteria`**：`noul`=record / `score`=array / `choice`=record（键即选项，无需 `options`）。
⚠️ `score.score` **不是 0–1**，是期望锚点序号（5 锚点 → 0..4），用前必须 `/(N-1)` 归一化。
⚠️ 缺 `criteria` 直接 HTTP 400，报错 path 指向 `criteria`，可据此反推字段。

## License

MIT · 姊妹仓 [jevkit](https://github.com/HCTDIP/jevkit) · [jeveto](https://github.com/HCTDIP/jeveto)

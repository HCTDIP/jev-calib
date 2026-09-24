"""jev-calib v0.2 — Jev 校准可观测性监控（observability layer）
监控 TypeSafe Jev 的校准声明：可重复性 / 漂移 / 翻转率 / 成本延迟。
客户端层直接复用 jevkit（github.com/HCTDIP/jevkit），不重复造轮子。
代码拥有工作流，模型只答窄判断（TypeSafe 原话）。
用法: python3 jev_calib.py --config cases.json --runs 5 [--dry-run]
"""
import json, time, statistics, os, argparse, datetime

try:
    from jevkit import Client
except ImportError:
    raise SystemExit("jevkit required: git clone https://github.com/HCTDIP/jevkit.git && PYTHONPATH=jevkit")

_client = None


def get_client(api_key=None, model=None):
    """懒加载 jevkit Client（monitoring 层不管理 HTTP，交给 SDK 层）。"""
    global _client
    if _client is None:
        _client = Client(api_key=api_key, model=model) if model else Client(api_key=api_key)
    return _client


def parse_response(resp):
    """解析 Jev Decisions 响应 -> {noul:{}, score:{}, confidence:{}, cost, in_tokens}"""
    out = {"noul": {}, "score": {}, "confidence": {}, "cost": 0.0, "in_tokens": 0}
    for k, a in (resp.get("answers") or {}).items():
        t = a.get("type")
        if t == "noul":
            out["noul"][k] = a.get("noul")
        elif t == "score":
            out["score"][k] = a.get("score")
            if "confidence" in a:
                out["confidence"][k] = a["confidence"]
    u = resp.get("usage") or {}
    out["cost"] = u.get("cost", 0.0)
    out["in_tokens"] = u.get("input_tokens", 0)
    return out


def call_jev(state, questions, api_key=None, model=None, timeout=60):
    """真调 Jev — 走 jevkit SDK。返回 (parsed, latency)"""
    client = get_client(api_key=api_key, model=model)
    t0 = time.time()
    resp = client.decide(questions, state=state, timeout=timeout)
    return parse_response(resp), time.time() - t0


def aggregate(runs, threshold=0.05):
    """聚合 N 次运行 -> 每问题 mean/std/flips/max_delta + 成本/延迟"""
    agg = {}
    if not runs:
        return agg
    keys = sorted(runs[0].get("noul", {}).keys())
    for k in keys:
        vals = [r["noul"][k] for r in runs if k in r.get("noul", {})]
        if not vals:
            continue
        max_delta = max(vals) - min(vals)
        flips = 1 if max_delta > threshold else 0
        agg[k] = {
            "mean": statistics.fmean(vals),
            "std": statistics.pstdev(vals) if len(vals) > 1 else 0.0,
            "min": min(vals), "max": max(vals),
            "max_delta": round(max_delta, 4),
            "flips": flips,
        }
    agg["_meta"] = {
        "runs": len(runs),
        "avg_cost": statistics.fmean(r["cost"] for r in runs),
        "total_cost": sum(r["cost"] for r in runs),
        "avg_in_tokens": statistics.fmean(r.get("in_tokens", 0) for r in runs),
        "avg_latency": statistics.fmean(r.get("latency", 0) for r in runs),
    }
    return agg


def report(agg, model="typesafe/jev-1.13", runs=0, title="jev-calib"):
    """聚合结果 -> Markdown 报告"""
    lines = [f"# {title}", "",
             f"> model: `{model}` · runs: {runs} · {datetime.datetime.now().isoformat(timespec='seconds')}", ""]
    meta = agg.get("_meta", {})
    lines.append(f"**总成本**: ${meta.get('total_cost', 0):.6f} · 平均延迟 {meta.get('avg_latency', 0):.2f}s · 平均输入 {meta.get('avg_in_tokens', 0):.0f} tokens")
    lines.append("")
    lines.append("| 问题 | mean | std | min | max | max_delta | flips |")
    lines.append("|---|---|---|---|---|---|---|")
    for k, v in agg.items():
        if k == "_meta":
            continue
        flag = " ⚠️" if v["flips"] else ""
        lines.append(f"| {k}{flag} | {v['mean']:.4f} | {v['std']:.4f} | {v['min']:.4f} | {v['max']:.4f} | {v['max_delta']} | {v['flips']} |")
    flips = [k for k, v in agg.items() if k != "_meta" and v["flips"]]
    if flips:
        lines.append("")
        lines.append(f"**⚠️ 校准漂移**: {', '.join(flips)} (max_delta > 阈值，borderline case 会翻转——jev-lab 已知现象)")
    else:
        lines.append("")
        lines.append("**✅ 无漂移**: 全部问题 max_delta ≤ 阈值")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="jev-calib — Jev 校准监控")
    ap.add_argument("--config", required=True, help="cases.json: [{name, state, questions}]")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--threshold", type=float, default=0.05)
    ap.add_argument("--model", default=None, help="pin model version to compare calibration drift across versions")
    ap.add_argument("--dry-run", action="store_true", help="用 mock 响应，不联网")
    ap.add_argument("--output", default="calib_report.md")
    args = ap.parse_args()

    cases = json.load(open(args.config, encoding="utf-8"))
    key = os.environ.get("OPENROUTER_API_KEY")
    all_md = []
    for case in cases:
        if args.dry_run or not key:
            # mock：固定基线 ± 微抖动，验证管线
            runs = []
            for i in range(args.runs):
                jitter = 0.01 * (i % 3)
                parsed = {"noul": {q: 0.61 + jitter for q in case["questions"]},
                          "cost": 1.7e-05, "in_tokens": 400, "latency": 1.2}
                runs.append(parsed)
            mode = "MOCK"
        else:
            runs = []
            for i in range(args.runs):
                try:
                    parsed, latency = call_jev(case["state"], case["questions"], api_key=key, model=args.model)
                    parsed["latency"] = latency
                    runs.append(parsed)
                except Exception as e:
                    print(f"[{case['name']}] run {i+1} 失败: {e}", flush=True)
            mode = "LIVE"
        agg = aggregate(runs, threshold=args.threshold)
        md = report(agg, model=args.model or "typesafe/jev-1.13", runs=len(runs), title=f"jev-calib · {case['name']} [{mode}]")
        all_md.append(md)
        print(f"[{case['name']}] {mode} {len(runs)} runs 完成", flush=True)

    out = "\n\n---\n\n".join(all_md)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"报告 → {args.output}")


if __name__ == "__main__":
    main()

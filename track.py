#!/usr/bin/env python3
"""jev_calib_track.py — jev-calib 漂移汇总层（副总指挥 / jev 生态巡检）

作用：跑一轮校准 → 解析报告 → 追加历史 → 打印跨轮漂移趋势。
这是 jev-calib 之上的一层"巡检验收"：单轮只证明这一次稳，跨轮才能看出有没有漂。

用法:
  export OPENROUTER_API_KEY=...           # live 模式需要；dry-run 不需要
  PYTHONPATH=../jevkit python3 jev_calib_track.py --runs 3            # live
  PYTHONPATH=../jevkit python3 jev_calib_track.py --runs 3 --dry-run  # mock
  PYTHONPATH=../jevkit python3 jev_calib_track.py --report-only       # 只看趋势

历史: jev_calib_history.jsonl（每行一次运行：ts/mode/runs/指标/成本/延迟）
"""
import argparse, json, os, re, subprocess, sys, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
CALIB = os.path.join(HERE, "jev-calib") if os.path.isdir(os.path.join(HERE, "jev-calib")) else HERE
HIST = os.path.join(HERE, "jev_calib_history.jsonl")
REPORT = os.path.join(CALIB, "calib_report.md")


def parse_report(path):
    """从 jev_calib 生成的 markdown 报告里抽出指标。返回 None 表示还没生成。"""
    if not os.path.exists(path):
        return None
    txt = open(path, encoding="utf-8").read()
    head = re.search(r"#\s*jev-calib\s*·\s*(\S+)\s*\[(\w+)\]", txt)
    meta = re.search(r"runs:\s*(\d+)\s*·\s*([\d\-T:]+)", txt)
    cost = re.search(r"总成本\*\*:\s*\$([\d.eE\-]+)\s*·\s*平均延迟\s*([\d.]+)s", txt)
    rows = []
    for line in txt.splitlines():
        m = re.match(r"\|\s*([\w\-]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*(\d+)\s*\|", line)
        if m:
            rows.append({"q": m.group(1), "mean": float(m.group(2)), "std": float(m.group(3)),
                         "min": float(m.group(4)), "max": float(m.group(5)),
                         "max_delta": float(m.group(6)), "flips": int(m.group(7))})
    if not rows:
        return None
    return {"case": head.group(1) if head else "?", "mode": head.group(2) if head else "?",
            "runs": int(meta.group(1)) if meta else None,
            "ran_at": meta.group(2) if meta else "",
            "cost": float(cost.group(1)) if cost else None,
            "latency": float(cost.group(2)) if cost else None,
            "metrics": rows}


def append_history(rec):
    with open(HIST, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_history():
    if not os.path.exists(HIST):
        return []
    out = []
    for l in open(HIST, encoding="utf-8"):
        l = l.strip()
        if l:
            try:
                out.append(json.loads(l))
            except Exception:
                pass
    return out


def trend(hist):
    """跨轮漂移：同一 case+mode 的 mean 序列 + 轮间 Δ。"""
    groups = {}
    for r in hist:
        groups.setdefault((r["case"], r["mode"]), []).append(r)
    lines = []
    for (case, mode), rs in groups.items():
        rs = sorted(rs, key=lambda r: r.get("ran_at") or "")
        lines.append(f"\n### {case} [{mode}] — {len(rs)} 轮")
        lines.append("| 时间 | runs | mean | std | max_delta | flips | 轮间 Δmean | 判定 |")
        lines.append("|---|---|---|---|---|---|---|---|")
        prev = None
        for r in rs:
            q = r["metrics"][0]
            d = "—" if prev is None else f"{q['mean']-prev:+.4f}"
            flag = "✅ 稳" if (prev is None or abs(q["mean"] - prev) < 0.05) else "⚠️ 漂移"
            lines.append(f"| {r.get('ran_at','?')} | {r.get('runs')} | {q['mean']:.4f} | {q['std']:.4f} | "
                         f"{q['max_delta']:.2f} | {q['flips']} | {d} | {flag} |")
            prev = q["mean"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--case", default="cases.json")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    a = ap.parse_args()

    if not a.report_only:
        env = dict(os.environ)
        env.setdefault("PYTHONPATH", os.path.abspath(os.path.join(HERE, "..", "jevkit")))
        cmd = [sys.executable, "jev_calib.py", "--config", a.case, "--runs", str(a.runs)]
        if a.dry_run:
            cmd.append("--dry-run")
        print("→ 跑:", " ".join(cmd))
        p = subprocess.run(cmd, cwd=CALIB, env=env, capture_output=True, text=True, timeout=900)
        tail = (p.stdout or "").strip().splitlines()[-3:]
        print("  " + " | ".join(tail) if tail else "  (无输出)")
        if p.returncode != 0:
            print("  stderr:", (p.stderr or "")[-300:])

    rec = parse_report(REPORT)
    if not rec:
        print("✗ 无法解析报告，跳过入库"); return 1
    rec["ts"] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    if not rec.get("ran_at"):
        rec["ran_at"] = rec["ts"]
    append_history(rec)
    hist = load_history()
    print(f"\n✓ 已入库（历史 {len(hist)} 轮）")
    print(trend(hist))
    # 结论
    last = hist[-1]["metrics"][0]
    verdict = "✅ 无漂移" if last["flips"] == 0 and last["max_delta"] <= 0.05 else "⚠️ 检出漂移"
    print(f"\n【巡检结论】case={hist[-1]['case']} mode={hist[-1]['mode']} :: {verdict} "
          f"(max_delta={last['max_delta']}, flips={last['flips']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

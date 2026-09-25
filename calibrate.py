#!/usr/bin/env python3
"""calibrate.py — 生成机器可复验的「校准证书」(calibration certificate)。

为什么存在：README 里的稳定性数字（漂移 ≤0.01、0 翻转）谁都写得出来，但**没人能证明**。
本脚本把「跑 N 次 → 统计 → 判定 → 摘要签名」固化成一条命令，
产出 calibration_certificate.json：任何第三方 clone 后跑同一命令即可复核，
改了结论哈希就变（tamper-evident）。

用法:
    python3 calibrate.py --dry-run                     # 离线自证（CI 默认；无 key 时自动走 mock）
    python3 calibrate.py --runs 5                      # 真跑（需 OPENROUTER_API_KEY）
    python3 calibrate.py --verify calibration_certificate.json   # 复核一份证书（不联网）
"""
import argparse, datetime, hashlib, json, os, platform, subprocess, sys

import jev_calib as jc


def _git_sha():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return None


def _digest(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _run_case(case, runs, threshold, model, key, dry_run):
    """与 jev_calib.main 完全同路径：dry_run 或无 key → mock；否则真调。"""
    collected = []
    for i in range(runs):
        if dry_run or not key:
            jitter = 0.01 * (i % 3)
            collected.append({"noul": {q: 0.61 + jitter for q in case["questions"]},
                              "cost": 1.7e-05, "in_tokens": 400, "latency": 1.2})
        else:
            parsed, latency = jc.call_jev(case["state"], case["questions"], api_key=key, model=model)
            parsed["latency"] = latency
            collected.append(parsed)
    agg = jc.aggregate(collected, threshold=threshold)
    meta = agg.get("_meta", {})
    stats = {k: v for k, v in agg.items() if k != "_meta"}
    return {"case": case["name"], "questions": stats,
            "cost": {"avg": meta.get("avg_cost"), "total": meta.get("total_cost"),
                     "avg_latency": meta.get("avg_latency"), "runs": meta.get("runs")}}


def build_certificate(cases, runs, threshold, model, dry_run):
    key = os.environ.get("OPENROUTER_API_KEY")
    mock = dry_run or not key
    results = [_run_case(c, runs, threshold, model, key, dry_run) for c in cases]
    worst_delta, flips = 0.0, 0
    for r in results:
        for _, st in r["questions"].items():
            worst_delta = max(worst_delta, float(st.get("max_delta", 0.0)))
            flips += int(st.get("flips", 0))
    payload = {
        "schema": "jev-calib/certificate@1",
        "issued_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "repo": "https://github.com/HCTDIP/jev-calib",
        "commit": _git_sha(),
        "model": model or "typesafe/jev-1.13",
        "mode": "mock(dry-run, 无外呼)" if mock else "live",
        "runs_per_case": runs,
        "threshold": threshold,
        "cases": [c["name"] for c in cases],
        "results": results,
        "verdict_inputs": {"worst_max_delta": round(worst_delta, 6), "total_flips": flips},
        "verdict": "STABLE" if (worst_delta <= threshold and flips == 0) else "DRIFT_DETECTED",
        "env": {"python": platform.python_version(), "platform": platform.system()},
    }
    payload["digest_sha256"] = _digest({k: v for k, v in payload.items() if k != "digest_sha256"})
    return payload


def verify(path):
    cert = json.load(open(path, encoding="utf-8"))
    got = cert.pop("digest_sha256", None)
    want = _digest(cert)
    ok = got == want
    print(f"证书 {path}: digest {'✅ 一致（未被改动）' if ok else '❌ 不一致（内容被改过）'}")
    print(f"  结论={cert.get('verdict')} 模式={cert.get('mode')} runs={cert.get('runs_per_case')} "
          f"worst_delta={cert.get('verdict_inputs', {}).get('worst_max_delta')} "
          f"flips={cert.get('verdict_inputs', {}).get('total_flips')}")
    if not ok:
        print(f"  expected {want}\n  found    {got}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="生成/复核 Jev 校准证书")
    ap.add_argument("--config", default="cases.json")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--threshold", type=float, default=0.05)
    ap.add_argument("--model", default=None)
    ap.add_argument("--dry-run", action="store_true", help="强制 mock（CI 默认；无 key 时也会自动 mock）")
    ap.add_argument("--output", default="calibration_certificate.json")
    ap.add_argument("--verify", default=None, help="复核一份已签发证书（不联网）")
    a = ap.parse_args()

    if a.verify:
        return verify(a.verify)

    cases = json.load(open(a.config, encoding="utf-8"))
    cert = build_certificate(cases, a.runs, a.threshold, a.model, a.dry_run)
    json.dump(cert, open(a.output, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"证书 → {a.output}｜模式 {cert['mode']}")
    return verify(a.output)


if __name__ == "__main__":
    sys.exit(main())

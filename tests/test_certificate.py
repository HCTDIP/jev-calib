"""校准证书测试：可生成、可复核、可发现篡改（全部离线）。"""
import json, os, subprocess, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _run(args, env=None):
    e = dict(os.environ); e.pop("OPENROUTER_API_KEY", None)
    if env:
        e.update(env)
    return subprocess.run([sys.executable, "calibrate.py"] + args, cwd=ROOT,
                          capture_output=True, text=True, env=e)


def test_certificate_generates_and_self_verifies(tmp_path):
    out = tmp_path / "cert.json"
    p = _run(["--runs", "3", "--output", str(out)])
    assert p.returncode == 0, p.stdout + p.stderr
    cert = json.loads(out.read_text(encoding="utf-8"))
    assert cert["schema"] == "jev-calib/certificate@1"
    assert cert["verdict"] in ("STABLE", "DRIFT_DETECTED")
    assert cert["mode"].startswith("mock")          # 无 key 必须走 mock，不许外呼
    assert cert["runs_per_case"] == 3
    assert cert["digest_sha256"]
    # 自检行出现在输出里
    assert "digest ✅ 一致" in p.stdout


def test_verify_detects_tampering(tmp_path):
    out = tmp_path / "cert.json"
    assert _run(["--output", str(out)]).returncode == 0
    cert = json.loads(out.read_text(encoding="utf-8"))
    cert["verdict"] = "STABLE_FAKE"                  # 篡改结论
    bad = tmp_path / "tampered.json"
    bad.write_text(json.dumps(cert, ensure_ascii=False), encoding="utf-8")
    p = _run(["--verify", str(bad)])
    assert p.returncode == 1
    assert "❌ 不一致" in p.stdout


def test_verify_accepts_untouched(tmp_path):
    out = tmp_path / "cert.json"
    assert _run(["--output", str(out)]).returncode == 0
    p = _run(["--verify", str(out)])
    assert p.returncode == 0
    assert "✅ 一致" in p.stdout

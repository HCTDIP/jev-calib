"""pytest 路径引导：让 `pytest -q` 在仓库里直接可跑，不必手动设 PYTHONPATH。

- 仓库自身（import jev_calib）
- 兄弟目录 ../jevkit（jev-calib v0.2 复用 jevkit 的 HTTP 层；CI 里由 workflow checkout 到同级）
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
for p in (ROOT, os.path.abspath(os.path.join(ROOT, "..", "jevkit"))):
    if p not in sys.path:
        sys.path.insert(0, p)

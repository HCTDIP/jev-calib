# PRD — jev-calib：Jev 校准可观测性监控工具
> v0.1 · 2026-09-21 · 空位实锤：GitHub "jev observability/calibration" 0 结果

## 核心功能
对 TypeSafe Jev（System One 决策模型）的校准声明做持续监控：
1. **可重复性**：同一 state+questions 跑 N 次，输出每问题的 mean/std/翻转率
2. **校准漂移**：对比两次运行（或与历史基线），标出 noul 变化 > 阈值的问题
3. **成本/延迟**：每次调用的 tokens/cost/延迟聚合
4. **报告**：Markdown + JSON 输出（可直接贴 issue / 进 CI）

## 用户流程
`python3 jev_calib.py --config cases.json --runs 10` → 逐 case 调 Jev → 聚合 → `calib_report.md`

## 边界
- 只监控不代理决策（Jev 干窄判断，代码拥有工作流——TypeSafe 原话）
- 需要 OPENROUTER_API_KEY；无 key 时 --dry-run 用 mock 响应（开发/CI 用）
- 不引入新框架，纯 Python 标准库

## 验收标准（v0.1）
- [ ] mock 模式 0 Error 跑通，报告生成
- [ ] 真跑 1 case × 3 runs，实数据落盘
- [ ] 翻转率/std 计算正确（测试覆盖）

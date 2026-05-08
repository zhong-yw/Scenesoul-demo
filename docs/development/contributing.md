# 贡献指南
> Status: [Implemented]  
> Last Reviewed: 2026-05-08

## 代码贡献流程

1. Fork / 新分支开发  
2. 本地运行测试：`pytest -q`  
3. 提交前确保文档状态标签正确（`[Implemented]/[TODO]/[Design]/[Future]`）  
4. 发起 PR，描述改动范围与验证结果

## 文档贡献规则

1. 任何“未编码功能”不得写入 `[Implemented]` 文档  
2. `[TODO]` 条目必须附 Issue 或 PR 链接  
3. `[Future]` 内容只能写到 `docs/roadmap/`  
4. 涉及行为变更时，需同步更新：
   - `docs/architecture/*`
   - `docs/guides/*`
   - `docs/api/*`


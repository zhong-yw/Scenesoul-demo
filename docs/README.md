# 文档总览（v0.6）
> Status: [Implemented]  
> Last Reviewed: 2026-05-08

本目录已按代码现状重构，遵循「代码驱动 + 状态透明」规则。  
文档状态标签定义如下：

- `[Implemented]`：代码已实现，可直接使用
- `[TODO]`：已规划但未编码，必须附追踪链接
- `[Design]`：方案确定但未落地（ADR/RFC）
- `[Future]`：远期规划，仅允许出现在 `roadmap/`

## 目录结构

| 目录 | 作用 |
|---|---|
| `architecture/` | 系统架构、模块关系、状态流 |
| `guides/` | 安装、配置、CLI/Web 使用指南 |
| `api/` | HTTP API 与 Python 入口参考 |
| `development/` | 开发环境、测试、贡献、TODO 与迁移映射 |
| `design/` | 未落地设计（ADR） |
| `roadmap/` | 中长期规划（Future） |

## 文档状态总览

| 文档 | 状态 | 当前可用性 |
|---|---|---|
| `architecture/system-architecture.md` | [Implemented] | 可用 |
| `architecture/runtime-state-flow.md` | [Implemented] | 可用 |
| `guides/quickstart.md` | [Implemented] | 可用 |
| `guides/configuration.md` | [Implemented] | 可用 |
| `guides/usage-cli-web.md` | [Implemented] | 可用 |
| `api/http-api.md` | [Implemented] | 可用 |
| `api/python-entrypoints.md` | [Implemented] | 可用 |
| `development/local-development.md` | [Implemented] | 可用 |
| `development/testing.md` | [Implemented] | 可用 |
| `development/contributing.md` | [Implemented] | 可用 |
| `development/docs-migration-map.md` | [Implemented] | 可用 |
| `development/todo-tracker.md` | [TODO] | 部分不可用（见追踪项） |
| `design/adr-0001-memory-runtime-integration.md` | [Design] | 未落地 |
| `design/adr-0002-scene-object-state-model.md` | [Design] | 未落地 |
| `roadmap/v0.7-to-v1.0.md` | [Future] | 规划中 |


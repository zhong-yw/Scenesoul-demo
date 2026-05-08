# 文档迁移映射表（旧 -> 新）
> Status: [Implemented]  
> Last Reviewed: 2026-05-08

## 迁移策略

- 旧文档全部完成审查并下线
- 内容按“实现/待办/设计/规划”重新归档
- 新结构以 `docs/README.md` 为入口

## 完整映射

| 旧文件 | 操作 | 新位置 |
|---|---|---|
| `docs/00-目录导航.md` | Merge | `docs/README.md` |
| `docs/01-项目概览/01-项目概览与架构总览.md` | Merge | `docs/architecture/system-architecture.md` |
| `docs/01-项目概览/02-技术栈与环境配置.md` | Merge | `docs/guides/configuration.md` |
| `docs/02-系统层/01-LLM客户端详细设计.md` | Merge | `docs/api/python-entrypoints.md` |
| `docs/02-系统层/02-Token估算与预算管理.md` | Merge | `docs/architecture/system-architecture.md` |
| `docs/03-大脑/01-BrainAgent核心设计.md` | Merge | `docs/architecture/system-architecture.md` |
| `docs/03-大脑/02-BrainContextBuilder详细设计.md` | Merge | `docs/architecture/system-architecture.md` |
| `docs/04-界说/01-NarratorAgent核心设计.md` | Merge | `docs/architecture/system-architecture.md` |
| `docs/04-界说/02-NarratorContextBuilder详细设计.md` | Merge | `docs/architecture/system-architecture.md` |
| `docs/05-记忆系统/01-大脑记忆系统-BrainMemory.md` | Move+Reclassify | `docs/design/adr-0001-memory-runtime-integration.md` |
| `docs/05-记忆系统/02-界说记忆系统-NarratorMemory.md` | Move+Reclassify | `docs/design/adr-0001-memory-runtime-integration.md` |
| `docs/05-记忆系统/03-记忆系统扩展蓝图-L2L3S2.md` | Move+Reclassify | `docs/roadmap/v0.7-to-v1.0.md` |
| `docs/06-世界系统/01-WorldBuilder与场景系统.md` | Merge | `docs/architecture/system-architecture.md` |
| `docs/06-世界系统/02-场景系统扩展蓝图.md` | Move+Reclassify | `docs/design/adr-0002-scene-object-state-model.md` |
| `docs/07-驱动力系统/01-情绪驱动力系统.md` | Merge | `docs/architecture/runtime-state-flow.md` |
| `docs/08-UI层/01-CLI渲染器详细设计.md` | Merge | `docs/guides/usage-cli-web.md` |
| `docs/09-核心循环/01-主循环与状态流转.md` | Merge | `docs/architecture/runtime-state-flow.md` |
| `docs/09-核心循环/02-Message系统设计.md` | Merge | `docs/architecture/runtime-state-flow.md` |
| `docs/10-协议/01-标记化输出协议.md` | Merge | `docs/architecture/runtime-state-flow.md` |
| `docs/11-时间系统/01-时间流逝与昼夜循环系统.md` | Merge | `docs/architecture/runtime-state-flow.md` |
| `docs/12-扩展蓝图/01-项目发展规划v0_1到v1_0.md` | Move+Reclassify | `docs/roadmap/v0.7-to-v1.0.md` |
| `docs/12-扩展蓝图/02-未来功能详细设计.md` | Move+Reclassify | `docs/roadmap/v0.7-to-v1.0.md` |
| `docs/12-扩展蓝图/03-技术债务与优化清单.md` | Move+Reclassify | `docs/development/todo-tracker.md` |
| `docs/12-扩展蓝图/04-优化与功能路线图-v0_6到v1_0.md` | Move+Reclassify | `docs/roadmap/v0.7-to-v1.0.md` |
| `docs/13-流程/01-用户交互全流程.md` | Merge | `docs/guides/usage-cli-web.md` |
| `docs/13-流程/02-初始化与启动流程.md` | Merge | `docs/guides/quickstart.md` |
| `docs/14-Profile配置系统/01-ProfileLoader设计.md` | Merge | `docs/guides/configuration.md` |
| `docs/14-Profile配置系统/02-Profile文件规范.md` | Merge | `docs/guides/configuration.md` |
| `docs/15-测试/01-测试方案.md` | Merge | `docs/development/testing.md` |
| `docs/00-历史存档/设计文档-项目计划书.md` | Delete | （规划信息已归入 `docs/roadmap/v0.7-to-v1.0.md`） |
| `docs/00-历史存档/设计文档-界说ContextBuilder.md` | Delete | （实现细节已归并到 `docs/architecture/system-architecture.md`） |
| `docs/00-历史存档/设计文档-大脑ContextBuilder.md` | Delete | （实现细节已归并到 `docs/architecture/system-architecture.md`） |
| `docs/00-历史存档/设计文档-大脑Agent架构灵感.md` | Delete | （历史灵感不再作为规范文档保留） |
| `docs/00-历史存档/备忘录.md` | Delete | （无当前实现价值） |

## 结果统计

- 旧文档：34
- 新文档：14
- 映射覆盖：100%


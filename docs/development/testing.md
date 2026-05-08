# 测试与质量基线
> Status: [Implemented]  
> Last Reviewed: 2026-05-08

## 运行测试

```bash
pytest -q
```

## 当前测试覆盖重点

| 测试文件 | 覆盖范围 |
|---|---|
| `tests/test_runtime.py` | v0.6 Runtime 流转 |
| `tests/test_main_loop.py` | CLI loop 包装行为 |
| `tests/test_web_server.py` | Web API 行为 |
| `tests/test_narrator_agent.py` | 界说输出/静默/tool_call |
| `tests/test_brain_agent.py` | 大脑独白/回复 |
| `tests/test_llm_client.py` | LLM client 与 fallback |
| `tests/test_world_builder.py` | scene.md 更新逻辑 |

## 质量约束（当前）

1. 文档只描述可从代码或测试验证到的行为  
2. 新增功能时需同步更新对应目录下文档状态标签  
3. 对未落地需求，禁止写入 `[Implemented]` 文档


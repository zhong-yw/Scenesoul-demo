# WorldBuilder 与场景系统

> **文档标识：** 06-世界系统/01-WorldBuilder与场景系统  
> **对应代码：** [world/world_builder.py](world/world_builder.py)  
> **版本：** v0.5（Message 系统重构）

---

## 一、概述

`WorldBuilder` 是场景和世界设定的调度器。它不直接持有数据，而是根据模式委派到不同的数据源：

- **profile 模式**（默认）— 委派 `ProfileLoader` 从 `profiles/` 下的 .md 文件加载
- **fallback 模式** — 从 `settings.json` 读取

v0.5 新增能力：
- **`update_scene()`** — 由界说通过 tool_call 调用，写入/更新 scene.md
- **`refresh_scene_cache()`** — 从 scene.md 重新加载场景缓存

---

## 二、类设计

```python
class WorldBuilder:
    def __init__(self, preset_name=None):
    def get_default_scene(self):
    def get_scene_collection(self):
    def refresh_scene_cache(self):
    def update_scene(self, scene_name, description):
    def build_scene(self, scene_name):
    def is_profile_mode(self):
    def get_profile_name(self):
```

### v0.5 新增属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `self._scene_collection` | dict | 场景缓存：{场景名: 完整描述}，每次 `update_scene()` 后刷新 |

---

## 三、update_scene() 设计

```python
def update_scene(self, scene_name, description):
    is_new = scene_name not in self._scene_collection
    
    if is_new:
        # 追加到 scene.md
        body += f"\n\n## {scene_name}\n{description}\n"
    else:
        # 在 body 中查找 ## scene_name，替换其 description
        # 保持 frontmatter 不变
        ...
    
    # 写回文件
    with open(scene_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    
    # 刷新缓存
    self.refresh_scene_cache()
    
    return {"success": True, "is_new": is_new}
```

### 调用链路

```
界说 LLM 输出:
  文本: [场景:书房] 你离开厨房，来到一间由老榆木书架围成的小书屋……
  tool_call: update_scene("书房", "...")

main.py:
  result = world.update_scene(scene_name, description)
  if result["success"]:
      # 场景列表已刷新
      # 下一轮 brain.internal_think() 时，
      # BrainContextBuilder._build_scene_list() 会读取到新场景

profile_loader:
  scene.md 被写入
  refresh_scene_cache() → ProfileLoader.get_scene_collection() 重新解析
```

### 场景描述替换策略

| 情况 | 行为 | 示例 |
|------|------|------|
| 新场景 | 追加到文件末尾 | `书房` 不存在 → 追加 `## 书房\n描述` |
| 已有场景 | 覆盖该场景的描述 | `厨房` 已存在且描述变化 → 替换描述文本 |
| 重复写相同内容 | 无副作用（覆盖相同文本） | 不影响运行 |

---

## 四、数据流

```
WorldBuilder(preset_name="library_den")
    ├── _detect_profile() → 检测 profiles/library_den/ 是否存在
    ├── __init__ → refresh_scene_cache()
    │   └── ProfileLoader.get_scene_collection("library_den")
    │       └── 解析 scene.md 所有 ## 标题 → {名称: 描述}
    │
    ├── get_default_scene()
    │   └── ProfileLoader.get_default_scene("library_den")
    │       └── 解析 scene.md → 返回 {name, description, time}
    │
    ├── update_scene("花园", "一片盛开的蔷薇花丛……")
    │   ├── 读取 scene.md
    │   ├── 追加或覆盖描述
    │   ├── 写回 scene.md
    │   └── refresh_scene_cache()
    │
    └── build_scene("花园")
        └── 从 _scene_collection 缓存中读取
```

---

## 五、settings.json

保留文件仅用于极简回退：

```json
{
  "default_scene": {
    "name": "卧室",
    "description": "一间温馨的卧室..."
  }
}
```

所有扩展配置迁移到 `profiles/` 下的 .md 文件。

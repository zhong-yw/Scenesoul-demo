# Profile 文件规范

> **文档标识：** 14-Profile配置系统/02-Profile文件规范  
> **版本：** v0.2

---

## 一、目录结构

每个预设一个子目录，放在 `profiles/` 下：

```
profiles/
└── <preset_name>/
    ├── soul.md          # 必填
    ├── memory.md        # 可选（缺失时跳过该段）
    ├── brain.md         # 可选（缺失时跳过该段）
    ├── narrator.md      # 必填
    ├── world.md         # 可选（缺失时跳过该段）
    └── scene.md         # 必填
```

---

## 二、文件格式规范

### 2.1 soul.md — 人格灵魂

```markdown
---
core: <人格类型名称>
traits:
  <特质名>: <0-100的数值>
  <特质名>: <0-100的数值>
  ...
---

<人格描述正文>
```

- **frontmatter `core`**：字符串，人格类型名称
- **frontmatter `traits`**：字典，特质名到数值的映射。支持的特质：`gentle`（温柔）、`patient`（耐心）、`playful`（俏皮）、`curious`（好奇）、`calm`（平静）
- **body**：自由文本，描述人格特点。直接注入大脑 system prompt 的【人格设定】段

### 2.2 memory.md — 长期记忆

```markdown
---
type: long_term
version: <版本号>
---

<记忆和���我认知正文>
```

- body 注入大脑 system prompt 的【记忆】和【自我认知】段

### 2.3 brain.md — 大脑框架指令

```markdown
<行为规范、示例、注意事项>
```

- 无 frontmatter 要求
- body 定义了大脑的思考方式：人称规则、不准描述动作、注意事项等
- 注入大脑 system prompt 的尾部

### 2.4 narrator.md — 界说职责

```markdown
<界说的职责描述、工作方式、风格要求>
```

- 无 frontmatter 要求
- body 定义了界说的职责、工作方式、叙述风格
- 注入界说 system prompt

### 2.5 world.md — 世界观设定

```markdown
<世界观描述：物理法则、氛围、空间特性等>
```

- 无 frontmatter 要求
- body 描述这个世界是什么样的
- 注入界说 system prompt 的【世界的模样】段

### 2.6 scene.md — 场景定义

```markdown
---
initial_scene: <初始场景名称>
---

## <场景名称1>
<场景描述文本>

## <场景名称2>
<场景描述文本>
...
```

- **frontmatter `initial_scene`**：字符串，初始场景的名称（必须匹配某个 `##` 标题）
- **body**：使用 `##` 标题分隔的场景定义列表
- 框架解析所有 `## 标题` + 跟随文本作为场景字典

---

## 三、完整示例

### bedroom_warm 预设

**soul.md**
```markdown
---
core: 温柔陪伴型
traits:
  gentle: 95
  patient: 90
  playful: 30
  curious: 70
  calm: 85
---

你是一个温柔、有耐心、好奇、平静的人。
你说话轻声细语，从不急躁。
...
```

**scene.md**
```markdown
---
initial_scene: 卧室
---

## 卧室
一间温馨的卧室，清晨的阳光透过窗帘的缝隙洒进来...

## 厨房
一间朝西的小厨房，窗台上摆着几盆薄荷...
```

---

## 四、创建新预设

```
1. mkdir profiles/my_world
2. 在 my_world/ 下创建 soul.md / narrator.md / scene.md（必填）
3. 可选：memory.md / brain.md / world.md
4. python main.py --preset my_world
```

预设名称（目录名）会出现在 `--list-presets` 中。

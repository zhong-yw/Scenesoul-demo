"""封装性检查：facade.py 不访问 stores 私有属性，memory/ 无 bare Exception。"""

import os
import re

MEMORY_DIR = os.path.join(os.path.dirname(__file__), "..", "memory")


def test_facade_no_private_access_on_stores():
    """facade.py 不应包含对 BrainMemory/NarratorMemory 实例的 ._ 访问。"""
    facade_path = os.path.join(MEMORY_DIR, "facade.py")
    with open(facade_path, "r", encoding="utf-8") as f:
        source = f.read()
    # 排除类定义内部的 self._ 访问（那是允许的）
    # 检查是否存在 brain_memory._ 或 narrator_memory._ 模式
    pattern = r"(?:brain_memory|narrator_memory)\._[a-z]"
    matches = re.findall(pattern, source)
    assert matches == [], f"facade.py contains private access on store instances: {matches}"


def test_memory_no_bare_exception():
    """memory/ 目录下不应有 except Exception 或 except (..., Exception, ...) 模式。"""
    for fname in os.listdir(MEMORY_DIR):
        if not fname.endswith(".py") or fname.startswith("__"):
            continue
        fpath = os.path.join(MEMORY_DIR, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            source = f.read()
        # 匹配 except Exception 和 except (...Exception...)
        bare = re.findall(r"except\s+Exception\b", source)
        assert bare == [], f"{fname} has bare 'except Exception': {bare}"
        broad = re.findall(r"except\s+\([^)]*Exception[^)]*\)", source)
        assert broad == [], f"{fname} has broad Exception in tuple: {broad}"

# 向后兼容 shim — 保持 `from memory.memory_system import ...` 可用
# 实际实现已拆分到 stores.py（BrainMemory/NarratorMemory）和 facade.py（MemorySystem）

from memory.stores import (  # noqa: F401
    BrainMemory, NarratorMemory,
    MEMORY_DIR, BRAIN_LOG_DIR, NARRATOR_LOG_DIR,
    _tail_lines, _RECENT_CACHE_SIZE,
)
from memory.facade import MemorySystem  # noqa: F401

__all__ = [
    "BrainMemory", "NarratorMemory", "MemorySystem",
    "MEMORY_DIR", "BRAIN_LOG_DIR", "NARRATOR_LOG_DIR",
]

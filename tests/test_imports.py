"""向后兼容 import 路径验证。"""

from memory.memory_system import BrainMemory, NarratorMemory, MemorySystem
from memory.memory_system import BRAIN_LOG_DIR, NARRATOR_LOG_DIR, _tail_lines
from memory.stores import BrainMemory as BM2, NarratorMemory as NM2
from memory.facade import MemorySystem as MS2


def test_brain_memory_import_identity():
    assert BrainMemory is BM2


def test_narrator_memory_import_identity():
    assert NarratorMemory is NM2


def test_memory_system_import_identity():
    assert MemorySystem is MS2


def test_constants_importable():
    assert isinstance(BRAIN_LOG_DIR, str)
    assert isinstance(NARRATOR_LOG_DIR, str)
    assert callable(_tail_lines)

"""SummaryBuilder — Brain / Narrator 差异化视图字符串化。

按 view 的白名单过滤、[回忆] 标记、关系字段注入、字符截断。
"""

from __future__ import annotations

from typing import Literal

from memory.inspector import id_key

BRAIN_ALLOWED_TYPES = frozenset({
    "brain_thought", "brain_reply", "user_input",
    "drives_update", "profile_memory", "relationship",
})

NARRATOR_ALLOWED_TYPES = frozenset({
    "scene_change", "scene_objects_update", "narrator_observe",
    "narrator_inject", "initial_scene",
})

NARRATOR_DROP_ORDER = ("narrator_observe", "scene_objects_update", "scene_change")


class SummaryBuilder:
    """差异化视图渲染器。"""

    def __init__(self, cfg, redactor=None):
        self._cfg = cfg
        self._redactor = redactor

    def render(
        self,
        view: Literal["brain", "narrator"],
        result,
        relationship=None,
    ) -> str:
        allowed = BRAIN_ALLOWED_TYPES if view == "brain" else NARRATOR_ALLOWED_TYPES
        max_chars = self._cfg.summary_max_chars

        # 按白名单过滤 + 去重
        seen_ids: set[str] = set()
        filtered: list = []
        for scored in result.entries:
            e = scored.entry
            if e.type not in allowed:
                continue
            eid = id_key(e)
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
            filtered.append(scored)

        # 渲染行
        lines: list[str] = []
        for scored in filtered:
            e = scored.entry
            prefix = "[回忆] " if id_key(e) in result.hit_by_context else ""
            lines.append(f"{prefix}[{e.type}] {e.content}")

        # Brain: 追加关系字段
        if view == "brain" and relationship:
            from memory.relationships import RelationshipStore
            pub = RelationshipStore.public_fields(relationship)
            for fname, fval in pub.items():
                lines.append(f"关系：{fname}={fval.value}")

        # 去重（按行内容）
        seen_lines: set[str] = set()
        deduped: list[str] = []
        for line in lines:
            if line not in seen_lines:
                seen_lines.add(line)
                deduped.append(line)
        lines = deduped

        # 截断到 max_chars
        text = "\n".join(lines)
        if len(text) <= max_chars:
            return text

        # 需要截断
        if view == "narrator":
            lines = self._truncate_narrator(lines, filtered, max_chars)
        else:
            lines = self._truncate_brain(lines, filtered, max_chars)

        return "\n".join(lines)

    def _truncate_narrator(self, lines, scored_list, max_chars):
        # 按 NARRATOR_DROP_ORDER 优先丢弃
        drop_scores: list[tuple[int, int, int]] = []  # (drop_priority, -significance, index)
        for i, scored in enumerate(scored_list):
            e = scored.entry
            if e.type in NARRATOR_DROP_ORDER:
                priority = NARRATOR_DROP_ORDER.index(e.type)
            else:
                priority = len(NARRATOR_DROP_ORDER)  # 不在丢弃列表中，最后丢
            drop_scores.append((priority, -scored.significance, i))

        drop_scores.sort()
        result = list(lines)
        for _, _, idx in sorted(drop_scores, key=lambda x: x[2], reverse=True):
            if len("\n".join(result)) <= max_chars:
                break
            result.pop(idx)
        return result

    def _truncate_brain(self, lines, scored_list, max_chars):
        # 按 significance 升序丢弃，profile_memory 最后丢
        drop_scores: list[tuple[int, int, int]] = []
        for i, scored in enumerate(scored_list):
            is_profile = scored.entry.type == "profile_memory"
            priority = 1 if is_profile else 0
            drop_scores.append((priority, scored.significance, i))

        drop_scores.sort()
        result = list(lines)
        for _, _, idx in sorted(drop_scores, key=lambda x: x[2], reverse=True):
            if len("\n".join(result)) <= max_chars:
                break
            result.pop(idx)
        return result

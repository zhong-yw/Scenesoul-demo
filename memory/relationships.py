"""RelationshipStore & PiiRedactor — v0.7 关系记忆与 PII 脱敏。

RelationshipStore 按 Profile + User 键持久化用户档案。
PiiRedactor 识别用户输入中的可记忆字段与 PII 片段。
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Mapping

logger = logging.getLogger(__name__)

_REL_ROOT = os.path.join(os.path.dirname(__file__), "relationships")


# ── Data Models ──

@dataclass
class RelationshipField:
    value: str
    updated_at: str
    private: bool = False


@dataclass
class RelationshipProfile:
    profile: str
    user_id: str
    fields: dict[str, RelationshipField] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class RedactionResult:
    redacted_text: str
    fields: dict[str, RelationshipField]
    pii_spans: tuple[tuple[int, int], ...]


# ── RelationshipStore ──

class RelationshipStore:
    """按 Profile + User 持久化关系档案。"""

    def __init__(self, cfg, root: str = _REL_ROOT, now: Callable[[], datetime] = datetime.now):
        self._cfg = cfg
        self._root = root
        self._now = now
        self._write_lock = threading.Lock()

    def path(self, profile: str, user_id: str) -> str:
        return os.path.join(self._root, profile, f"{user_id}.json")

    def load(self, profile: str, user_id: str) -> RelationshipProfile:
        if not self._cfg.relationship_enabled:
            return RelationshipProfile(profile=profile, user_id=user_id)
        p = self.path(profile, user_id)
        if not os.path.exists(p):
            return RelationshipProfile(profile=profile, user_id=user_id)
        try:
            with open(p, "r", encoding="utf-8") as f:
                obj = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("RelationshipStore.load: corrupted %s (%s), archiving", p, exc)
            self._archive_corrupted(p)
            return RelationshipProfile(profile=profile, user_id=user_id)

        fields = {}
        for fname, fdata in obj.get("fields", {}).items():
            if isinstance(fdata, dict):
                fields[fname] = RelationshipField(
                    value=fdata.get("value", ""),
                    updated_at=fdata.get("updated_at", ""),
                    private=fdata.get("private", False),
                )
        return RelationshipProfile(
            profile=obj.get("profile", profile),
            user_id=obj.get("user_id", user_id),
            fields=fields,
            created_at=obj.get("created_at", ""),
            updated_at=obj.get("updated_at", ""),
        )

    def save(self, rp: RelationshipProfile) -> None:
        if not self._cfg.relationship_enabled:
            return
        p = self.path(rp.profile, rp.user_id)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        fields_dict = {}
        for fname, fval in rp.fields.items():
            fields_dict[fname] = {
                "value": fval.value,
                "updated_at": fval.updated_at,
                "private": fval.private,
            }
        payload = {
            "profile": rp.profile,
            "user_id": rp.user_id,
            "fields": fields_dict,
            "created_at": rp.created_at,
            "updated_at": rp.updated_at,
        }
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)

    def merge(
        self,
        profile: str,
        user_id: str,
        new_fields: Mapping[str, RelationshipField],
    ) -> RelationshipProfile:
        if not self._cfg.relationship_enabled:
            return RelationshipProfile(profile=profile, user_id=user_id)
        with self._write_lock:
            rp = self.load(profile, user_id)
            now_str = self._now().isoformat()
            if not rp.created_at:
                rp.created_at = now_str

            changed = False
            for fname, new_fval in new_fields.items():
                existing = rp.fields.get(fname)
                if existing is not None and existing.value == new_fval.value:
                    continue
                rp.fields[fname] = RelationshipField(
                    value=new_fval.value,
                    updated_at=now_str,
                    private=new_fval.private,
                )
                changed = True

            if changed:
                rp.updated_at = now_str
            self.save(rp)
            return rp

    def mark_private(self, profile: str, user_id: str, field_name: str) -> None:
        if not self._cfg.relationship_enabled:
            return
        with self._write_lock:
            rp = self.load(profile, user_id)
            if field_name in rp.fields:
                rp.fields[field_name].private = True
                self.save(rp)

    @staticmethod
    def public_fields(rp: RelationshipProfile) -> dict[str, RelationshipField]:
        return {k: v for k, v in rp.fields.items() if not v.private}

    def _archive_corrupted(self, p: str) -> None:
        try:
            ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
            archive_dir = os.path.join(self._root, "_archive", ts, "corrupted")
            os.makedirs(archive_dir, exist_ok=True)
            dest = os.path.join(archive_dir, os.path.basename(p))
            if os.path.exists(p):
                os.replace(p, dest)
        except OSError:
            pass


# ── PiiRedactor ──

# 中文 PII 模板
_NAME_PATTERN = re.compile(r"我叫([一-鿿]{1,8})")
_PREF_PATTERN = re.compile(r"我喜欢([一-鿿\w]{1,20})")
_EMO_PATTERN = re.compile(r"我(?:今天|最近)有点([一-鿿]{1,10})")
_TOPIC_PATTERN = re.compile(r"我(?:总是|经常|一直)([一-鿿\w]{1,15})")

# 通用 PII
_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_PATTERN = re.compile(r"1[3-9]\d{9}")


class PiiRedactor:
    """识别并脱敏用户输入中的 PII。"""

    def __init__(self, now=None):
        self._now = now or datetime.now

    def process(self, text: str) -> RedactionResult:
        fields: dict[str, RelationshipField] = {}
        spans: list[tuple[int, int]] = []
        redacted = text
        now_str = self._now().isoformat()

        for pattern, field_name_tpl in [
            (_NAME_PATTERN, "name"),
            (_PREF_PATTERN, "preference_{val}"),
            (_EMO_PATTERN, "emotional_state"),
            (_TOPIC_PATTERN, "recurring_topic_{val}"),
        ]:
            for m in pattern.finditer(text):
                val = m.group(1).strip()
                if not val:
                    continue
                spans.append((m.start(), m.end()))

                if field_name_tpl == "name":
                    fname = "name"
                elif field_name_tpl == "emotional_state":
                    fname = "emotional_state"
                elif "{" in field_name_tpl:
                    slug = re.sub(r"[^a-zA-Z0-9一-鿿]", "_", val)[:20]
                    fname = field_name_tpl.replace("{val}", slug)
                else:
                    fname = field_name_tpl

                if fname not in fields:
                    fields[fname] = RelationshipField(value=val, updated_at=now_str)

        # 通用 PII（不提取为关系字段，只脱敏）
        for pattern in [_EMAIL_PATTERN, _PHONE_PATTERN]:
            for m in pattern.finditer(text):
                spans.append((m.start(), m.end()))

        # 从后向前替换以保持位置
        for start, end in sorted(spans, reverse=True):
            redacted = redacted[:start] + "<redacted>" + redacted[end:]

        return RedactionResult(
            redacted_text=redacted,
            fields=fields,
            pii_spans=tuple(spans),
        )

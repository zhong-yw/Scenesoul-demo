# 🌍 世界构造器

import json
import os

from world.scene_objects import SceneObjectStore


class WorldBuilder:
    """🌍 世界构造器 — 持有世界设定，支持 profile 模式

    v0.5:
    - 新增 update_scene() 接口：写入 scene.md
    - 新增 refresh_from_scene_md()：从 scene.md 重新加载场景缓存
    """

    def __init__(self, preset_name=None):
        self.settings_path = os.path.join(os.path.dirname(__file__), "settings.json")
        self.settings = self._load_settings()

        # 确定预设
        user_preset = preset_name or os.getenv("WORLD_PRESET", "") or "default"
        self.preset_name = user_preset
        self._profile_name = self._detect_profile(user_preset)

        # 场景缓存
        self._scene_collection = {}
        self.scene_objects = SceneObjectStore(profile_name=self._profile_name or "default")
        if self._profile_name:
            self.refresh_scene_cache()

    def _load_settings(self):
        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"default_scene": {"name": "白界", "description": "一片纯白的虚无。"}}

    def _detect_profile(self, name):
        if not name:
            return None
        try:
            from profiles.profile_loader import ProfileLoader
            return name if ProfileLoader.profile_exists(name) else None
        except (ImportError, AttributeError):
            return None

    def is_profile_mode(self):
        return self._profile_name is not None

    def get_profile_name(self):
        return self._profile_name

    def refresh_scene_cache(self):
        """从 scene.md 刷新场景缓存"""
        from profiles.profile_loader import ProfileLoader
        self._scene_collection = ProfileLoader.get_scene_collection(self._profile_name)

    def get_scene_collection(self):
        """获取所有场景（从缓存）"""
        if self._profile_name:
            return self._scene_collection
        return {}

    def get_default_scene(self):
        """获取初始场景"""
        if self._profile_name:
            from profiles.profile_loader import ProfileLoader
            return ProfileLoader.get_default_scene(self._profile_name)
        default = self.settings.get("default_scene", {})
        return {"name": default.get("name", "未知"), "description": default.get("description", ""), "time": ""}

    def update_scene(self, scene_name, description):
        """写入/更新 scene.md

        参数:
            scene_name: 场景名称
            description: 场景完整描述

        返回:
            {"success": True/False, "is_new": True/False}
            如果场景已存在则覆盖，不存在则追加。
        """
        if not self._profile_name:
            return {"success": False, "is_new": False}

        from profiles.profile_loader import ProfileLoader
        scene_path = ProfileLoader._profile_path(self._profile_name, "scene.md")

        # 读取原始内容
        if os.path.exists(scene_path):
            with open(scene_path, "r", encoding="utf-8") as f:
                original = f.read()
        else:
            original = ""

        # 解析 frontmatter
        import re
        match = re.match(r'^---\s*\n(.*?)\n---\s*\n?(.*)', original, re.DOTALL)
        if match:
            frontmatter_str = match.group(1)
            body = match.group(2)
        else:
            frontmatter_str = ""
            body = original

        # 检查场景是否已存在
        scene_pattern = re.compile(rf'^## {re.escape(scene_name)}\s*$', re.MULTILINE)
        is_new = not bool(scene_pattern.search(body))

        if is_new:
            # 追加
            if body.strip():
                body = body.rstrip() + "\n\n"
            body += f"## {scene_name}\n{description}\n"
        else:
            # 替换已有场景描述
            new_lines = []
            in_target = False
            after_header = False
            for line in body.split("\n"):
                if re.match(rf'^## {re.escape(scene_name)}\s*$', line):
                    in_target = True
                    after_header = True
                    new_lines.append(line)
                    continue
                if in_target:
                    if line.startswith("## "):
                        in_target = False
                        new_lines.append(line)
                    elif after_header:
                        after_header = False
                        new_lines.append(description)
                    continue
                new_lines.append(line)
            body = "\n".join(new_lines)

        # 写回文件
        if frontmatter_str:
            frontmatter_str = frontmatter_str.rstrip()
            new_content = f"---\n{frontmatter_str}\n---\n\n{body}"
        else:
            new_content = body

        with open(scene_path, "w", encoding="utf-8") as f:
            f.write(new_content.strip() + "\n")

        # 刷新缓存
        self.refresh_scene_cache()

        return {"success": True, "is_new": is_new}

    def apply_scene_object_ops(self, scene_name, operations):
        return self.scene_objects.apply_operations(scene_name, operations)

    def get_scene_object_snapshot(self, scene_name):
        return self.scene_objects.get_scene_snapshot(scene_name)

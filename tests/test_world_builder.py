"""WorldBuilder 测试"""

import json
from unittest.mock import MagicMock, patch

import pytest
from world.world_builder import WorldBuilder


TEST_SETTINGS = {
    "default_scene": {
        "name": "卧室",
        "description": "一间温馨的卧室。"
    },
    "personality": {
        "core": "温柔陪伴型",
        "traits": {"gentle": 95}
    }
}


@pytest.fixture
def world_builder(tmp_path):
    settings_dir = tmp_path / "world"
    settings_dir.mkdir()
    settings_file = settings_dir / "settings.json"
    with open(settings_file, "w", encoding="utf-8") as f:
        json.dump(TEST_SETTINGS, f, ensure_ascii=False)
    with patch("world.world_builder.os.path.dirname", return_value=str(settings_dir)):
        wb = WorldBuilder()
        wb.settings_path = str(settings_file)
        wb.settings = TEST_SETTINGS.copy()
        yield wb


class TestDefaultScene:
    """get_default_scene 测试"""

    def test_returns_dict(self, world_builder):
        scene = world_builder.get_default_scene()
        assert isinstance(scene, dict)
        assert "name" in scene
        assert "description" in scene

    def test_default_name(self, world_builder):
        scene = world_builder.get_default_scene()
        assert scene["name"] == "卧室"


class TestUpdateScene:
    """update_scene 测试"""

    def test_new_scene_appends(self, world_builder, tmp_path):
        """新场景追加到 scene.md"""
        scene_file = tmp_path / "scene.md"
        scene_file.write_text("---\ninitial_scene: 卧室\n---\n\n## 卧室\n一间卧室。\n", encoding="utf-8")

        world_builder._profile_name = "default"
        with patch("profiles.profile_loader.ProfileLoader._profile_path", return_value=str(scene_file)):
            result = world_builder.update_scene("厨房", "一间小厨房。")
            assert result["success"] is True
            assert result["is_new"] is True
            content = scene_file.read_text(encoding="utf-8")
            assert "厨房" in content
            assert "一间小厨房" in content

    def test_existing_scene_overwrites(self, world_builder, tmp_path):
        """已有场景被覆盖"""
        scene_file = tmp_path / "scene.md"
        scene_file.write_text("---\ninitial_scene: 卧室\n---\n\n## 卧室\n旧描述。\n", encoding="utf-8")

        world_builder._profile_name = "default"
        with patch("profiles.profile_loader.ProfileLoader._profile_path", return_value=str(scene_file)):
            result = world_builder.update_scene("卧室", "新描述。")
            assert result["success"] is True
            assert result["is_new"] is False
            content = scene_file.read_text(encoding="utf-8")
            assert "新描述。" in content
            assert "旧描述。" not in content

    def test_no_profile_returns_failure(self, world_builder):
        """无 profile 时返回失败"""
        wb = WorldBuilder()
        wb._profile_name = None
        result = wb.update_scene("厨房", "描述")
        assert result["success"] is False


class TestProfileMode:
    """default profile 模式测试"""

    def test_default_profile_active(self, world_builder):
        """未指定 preset 时默认使用 default profile"""
        assert world_builder.is_profile_mode() is True
        assert world_builder.get_profile_name() == "default"


class TestSceneObjects:
    def test_apply_scene_object_ops_delegates_store(self, world_builder):
        world_builder.scene_objects = MagicMock()
        world_builder.scene_objects.apply_operations.return_value = {"success": True}

        result = world_builder.apply_scene_object_ops("卧室", [{"op": "upsert", "id": "lamp", "patch": {"state": "亮"}}])

        assert result["success"] is True
        world_builder.scene_objects.apply_operations.assert_called_once()

    def test_get_scene_object_snapshot_delegates_store(self, world_builder):
        world_builder.scene_objects = MagicMock()
        world_builder.scene_objects.get_scene_snapshot.return_value = {"scene": "卧室", "objects": []}

        result = world_builder.get_scene_object_snapshot("卧室")

        assert result["scene"] == "卧室"
        world_builder.scene_objects.get_scene_snapshot.assert_called_once_with("卧室")

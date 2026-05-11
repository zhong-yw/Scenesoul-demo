"""SceneObjectStore 测试"""

from world.scene_objects import SceneObjectStore


def test_apply_operations_upsert_update_remove(tmp_path):
    store = SceneObjectStore(profile_name="test_profile", base_dir=str(tmp_path))

    result1 = store.apply_operations("厨房", [
        {"op": "upsert", "id": "kettle", "patch": {"name": "水壶", "state": "空"}},
        {"op": "upsert", "id": "window", "patch": {"name": "窗户", "state": "关闭"}},
    ])
    assert result1["success"] is True
    assert result1["version"] == 1
    assert len(result1["objects"]) == 2

    result2 = store.apply_operations("厨房", [
        {"op": "update", "id": "kettle", "patch": {"state": "满水"}},
        {"op": "remove", "id": "window"},
    ])
    assert result2["version"] == 2
    kettle = [o for o in result2["objects"] if o["id"] == "kettle"][0]
    assert kettle["state"] == "满水"
    assert all(o["id"] != "window" for o in result2["objects"])


def test_load_scene_snapshot_default(tmp_path):
    store = SceneObjectStore(profile_name="test_profile", base_dir=str(tmp_path))
    snapshot = store.get_scene_snapshot("卧室")
    assert snapshot["scene"] == "卧室"
    assert snapshot["version"] == 0
    assert snapshot["objects"] == []

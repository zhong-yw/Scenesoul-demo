import json
import os
from datetime import datetime


class SceneObjectStore:
    """场景对象状态存储（按 profile + scene 持久化 JSON 快照）。"""

    def __init__(self, profile_name=None, base_dir=None):
        root = base_dir or os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "memory",
            "scene_state",
        )
        self.profile_name = profile_name or "default"
        self.storage_dir = os.path.join(root, self.profile_name)
        os.makedirs(self.storage_dir, exist_ok=True)

    def _scene_path(self, scene_name):
        safe_name = scene_name.replace("\\", "_").replace("/", "_").strip() or "unknown"
        return os.path.join(self.storage_dir, f"{safe_name}.json")

    def load_scene_snapshot(self, scene_name):
        path = self._scene_path(scene_name)
        if not os.path.exists(path):
            return {
                "scene": scene_name,
                "version": 0,
                "updated_at": None,
                "objects": [],
                "recent_changes": [],
            }
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Invalid scene snapshot format: {path}")
        data.setdefault("scene", scene_name)
        data.setdefault("version", 0)
        data.setdefault("updated_at", None)
        data.setdefault("objects", [])
        data.setdefault("recent_changes", [])
        return data

    def _save_scene_snapshot(self, snapshot):
        path = self._scene_path(snapshot["scene"])
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)

    def apply_operations(self, scene_name, operations):
        if not isinstance(operations, list):
            raise ValueError("operations must be a list")

        snapshot = self.load_scene_snapshot(scene_name)
        objects = snapshot.get("objects", [])
        index = {obj.get("id"): obj for obj in objects if isinstance(obj, dict) and obj.get("id")}
        changed_ids = []
        changes = snapshot.get("recent_changes", [])
        now = datetime.now().isoformat()

        for op_item in operations:
            if not isinstance(op_item, dict):
                continue
            op = str(op_item.get("op", "")).strip().lower()
            obj_id = str(op_item.get("id", "")).strip()
            patch = op_item.get("patch", {})

            if not obj_id:
                continue
            if op not in ("upsert", "update", "remove"):
                continue

            if op == "remove":
                if obj_id in index:
                    objects = [obj for obj in objects if obj.get("id") != obj_id]
                    index.pop(obj_id, None)
                    changed_ids.append(obj_id)
                    changes.append({"time": now, "op": "remove", "id": obj_id})
                continue

            if not isinstance(patch, dict):
                continue

            if op == "update" and obj_id not in index:
                continue

            if obj_id not in index:
                index[obj_id] = {"id": obj_id}
                objects.append(index[obj_id])

            index[obj_id].update(patch)
            index[obj_id]["id"] = obj_id
            changed_ids.append(obj_id)
            changes.append({"time": now, "op": op, "id": obj_id, "patch": patch})

        if changed_ids:
            snapshot["objects"] = objects
            snapshot["version"] = int(snapshot.get("version", 0)) + 1
            snapshot["updated_at"] = now
            snapshot["recent_changes"] = changes[-20:]
            self._save_scene_snapshot(snapshot)

        return {
            "success": True,
            "scene": scene_name,
            "version": snapshot.get("version", 0),
            "objects": snapshot.get("objects", []),
            "changed": changed_ids,
            "recent_changes": snapshot.get("recent_changes", [])[-5:],
        }

    def get_scene_objects(self, scene_name):
        snapshot = self.load_scene_snapshot(scene_name)
        return snapshot.get("objects", [])

    def get_scene_snapshot(self, scene_name):
        return self.load_scene_snapshot(scene_name)

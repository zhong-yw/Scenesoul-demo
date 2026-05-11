import json
import os
import time

from context_builders import build_state_header
from profiles.profile_loader import ProfileLoader


class ScenesoulRuntime:
    """共享运行时：维护主状态流转，不依赖 CLI/Web 渲染。"""

    def __init__(self, brain, narrator, world, current_scene_name, profile_name="default"):
        self.brain = brain
        self.narrator = narrator
        self.world = world

        self.profile_name = profile_name or "default"
        self.brain_messages = []
        self.narrator_messages = []

        self.drives = ProfileLoader.get_initial_drives(self.profile_name)
        self.current_scene_name = current_scene_name
        self.user_present = False
        self.sleep_mode = False
        self.last_think_time = time.time()
        self.last_user_time = 0

        self.think_interval = int(os.getenv("THINK_INTERVAL", "10"))
        self.user_timeout = int(os.getenv("USER_TIMEOUT", "600"))
        self.memory_enabled = os.getenv("MEMORY_ENABLED", "1").strip().lower() not in ("0", "false", "off", "no")
        self.brain_memory = None
        self.narrator_memory = None
        if self.memory_enabled:
            self._init_memory()

    def _clamp_drives(self):
        for k, v in self.drives.items():
            self.drives[k] = max(-100, min(100, v))

    def _init_memory(self):
        try:
            from memory.memory_system import BrainMemory, NarratorMemory
            self.brain_memory = BrainMemory()
            self.narrator_memory = NarratorMemory()
            self._restore_state_from_logs()
            self._sync_memory_snapshots()
        except (OSError, ImportError) as e:
            # 记忆目录不可写或模块缺失：降级为无记忆模式，不影响核心流程
            import logging
            logging.getLogger(__name__).warning(
                "Memory init failed, running without memory: %s", e
            )
            self.memory_enabled = False
            self.brain_memory = None
            self.narrator_memory = None

    def _memory_is_ready(self):
        return self.memory_enabled and self.brain_memory is not None and self.narrator_memory is not None

    def _sync_memory_snapshots(self):
        if not self._memory_is_ready():
            return
        self.brain_memory.update_l1("current_scene", self.current_scene_name)
        self.brain_memory.update_l1("user_present", self.user_present)
        self.brain_memory.update_l1("drives", dict(self.drives))
        self.narrator_memory.s1["current_scene"] = self.current_scene_name

    def _log_brain_event(self, event_type, content, weight=1):
        if not self._memory_is_ready():
            return
        payload = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        self.brain_memory.log_l2(event_type, payload, emotion_weight=weight)

    def _log_narrator_event(self, event_type, description):
        if not self._memory_is_ready():
            return
        self.narrator_memory.log_event(event_type, description)

    def _build_recent_memory_summary(self, max_items=5):
        if not self._memory_is_ready():
            return ""

        # 拉取两边各 max_items 条，按时间戳合并 + 去空 + 取最近 max_items 条
        brain_logs = self.brain_memory.get_recent_logs(max_items)
        narrator_events = self.narrator_memory.get_recent_events(max_items)

        combined = []
        for e in brain_logs:
            content = str(e.get("content", "")).strip()
            if not content:
                continue
            combined.append((
                e.get("timestamp", ""),
                "大脑",
                e.get("type", "brain"),
                content,
            ))
        for e in narrator_events:
            content = str(e.get("description", "")).strip()
            if not content:
                continue
            combined.append((
                e.get("timestamp", ""),
                "界说",
                e.get("type", "event"),
                content,
            ))

        combined.sort(key=lambda x: x[0])  # 按时间戳升序；空戳会排到最前
        lines = [
            f"- [{src}/{etype}] {content[:80]}"
            for _, src, etype, content in combined[-max_items:]
        ]
        return "\n".join(lines)

    def _get_world_objects_status(self):
        default_snapshot = {
            "scene": self.current_scene_name,
            "version": 0,
            "objects": [],
            "recent_changes": [],
        }
        # 用 type() 而不是实例 hasattr：避免 MagicMock 自动生成属性导致测试中
        # 误以为 world 实现了 get_scene_object_snapshot。
        if not hasattr(type(self.world), "get_scene_object_snapshot"):
            return default_snapshot
        snapshot = self.world.get_scene_object_snapshot(self.current_scene_name)
        if not isinstance(snapshot, dict):
            return default_snapshot
        return {
            "scene": snapshot.get("scene", self.current_scene_name),
            "version": snapshot.get("version", 0),
            "objects": snapshot.get("objects", []),
            "recent_changes": snapshot.get("recent_changes", [])[-5:],
        }

    def _restore_state_from_logs(self):
        if not self._memory_is_ready():
            return

        recent_events = self.narrator_memory.get_recent_events(30)
        for entry in reversed(recent_events):
            desc = str(entry.get("description", "")).strip()
            if not desc:
                continue
            if "场景切换到" in desc:
                restored = desc.split("场景切换到", 1)[-1].strip("：: ")
                if restored:
                    self.current_scene_name = restored
                    break
            if desc.startswith("场景更新:"):
                restored = desc.split("场景更新:", 1)[-1].split("-", 1)[0].strip()
                if restored:
                    self.current_scene_name = restored
                    break

        recent_brain_logs = self.brain_memory.get_recent_logs(50)
        for entry in reversed(recent_brain_logs):
            if entry.get("type") != "drives_update":
                continue
            raw_content = entry.get("content", "")
            drives_payload = None
            if isinstance(raw_content, dict):
                drives_payload = raw_content
            elif isinstance(raw_content, str):
                try:
                    loaded = json.loads(raw_content)
                except json.JSONDecodeError:
                    loaded = None
                if isinstance(loaded, dict):
                    drives_payload = loaded
            if not isinstance(drives_payload, dict):
                continue
            for k, v in drives_payload.items():
                if isinstance(v, (int, float)):
                    self.drives[k] = v
            self._clamp_drives()
            break

    def brain_think(self):
        memory_summary = self._build_recent_memory_summary()
        thought = self.brain.internal_think(
            messages=self.brain_messages,
            drives=self.drives,
            current_scene_info={"name": self.current_scene_name, "description": ""},
            memory_summary=memory_summary,
        )
        self.brain_messages.append({"role": "assistant", "content": thought})
        self._log_brain_event("brain_thought", thought, weight=2)
        self._sync_memory_snapshots()
        return thought

    def brain_respond(self, user_input):
        memory_summary = self._build_recent_memory_summary()
        reply = self.brain.respond(
            messages=self.brain_messages,
            user_input=user_input,
            drives=self.drives,
            current_scene_info={"name": self.current_scene_name, "description": ""},
            memory_summary=memory_summary,
        )
        self.brain_messages.append({"role": "assistant", "content": reply})
        self._log_brain_event("brain_reply", reply, weight=2)
        self._sync_memory_snapshots()
        return reply

    def narrator_observe(self, brain_thought):
        self.narrator_messages.append({"role": "user", "content": brain_thought})
        prev_scene = self.current_scene_name
        result = self.narrator.observe(
            self.narrator_messages,
            memory_summary=self._build_recent_memory_summary(),
        )

        has_tool_updates = bool(
            result.get("tool_call")
            or result.get("drives_update")
            or result.get("scene_objects_update")
        )
        if not result.get("narration") and not has_tool_updates:
            result["scene_changed"] = False
            return result

        narrator_output = result.get("narration") or ""
        is_new_scene = False

        tool_calls_list = []
        if result.get("tool_call"):
            tc = result["tool_call"]
            tool_calls_list.append({
                "id": f"call_scene_{tc['scene_name']}",
                "type": "function",
                "function": {
                    "name": "update_scene",
                    "arguments": json.dumps(tc, ensure_ascii=False),
                }
            })
        if result.get("drives_update"):
            tool_calls_list.append({
                "id": "call_drives",
                "type": "function",
                "function": {
                    "name": "update_drives",
                    "arguments": json.dumps({"drives": result["drives_update"]}, ensure_ascii=False),
                }
            })
        if result.get("scene_objects_update"):
            tc = result["scene_objects_update"]
            tool_calls_list.append({
                "id": "call_scene_objects",
                "type": "function",
                "function": {
                    "name": "update_scene_objects",
                    "arguments": json.dumps(tc, ensure_ascii=False),
                }
            })

        if tool_calls_list:
            self.narrator_messages.append({
                "role": "assistant",
                "content": narrator_output,
                "tool_calls": tool_calls_list,
            })
            for tc in tool_calls_list:
                tc_name = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"])
                if tc_name == "update_scene":
                    wr = self.world.update_scene(args["scene_name"], args["description"])
                    if wr.get("success"):
                        self.current_scene_name = args["scene_name"]
                        is_new_scene = wr.get("is_new", False)
                        self._log_narrator_event("scene_change", f"场景切换到 {self.current_scene_name}")
                    else:
                        self._log_narrator_event("scene_change_failed", f"场景写入失败: {args.get('scene_name', '')}")
                    self.narrator_messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(wr, ensure_ascii=False),
                    })
                elif tc_name == "update_drives":
                    drives_update = args.get("drives", {})
                    self.drives.update(drives_update)
                    self._clamp_drives()
                    # 记录完整快照（而非增量），便于重启恢复
                    self._log_brain_event("drives_update", dict(self.drives), weight=2)
                    self.narrator_messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps({"success": True, "drives": self.drives}, ensure_ascii=False),
                    })
                elif tc_name == "update_scene_objects":
                    wr = self.world.apply_scene_object_ops(
                        args.get("scene_name", self.current_scene_name),
                        args.get("operations", []),
                    )
                    self._log_narrator_event(
                        "scene_objects_update",
                        f"对象状态更新: {args.get('scene_name', self.current_scene_name)} ({len(wr.get('changed', []))}项)",
                    )
                    self.narrator_messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(wr, ensure_ascii=False),
                    })
        else:
            self.narrator_messages.append({"role": "assistant", "content": narrator_output})
            if result.get("scene_name"):
                self.current_scene_name = result["scene_name"]

        state_header = build_state_header(self.drives, self.current_scene_name)
        content = f"{state_header}\n{narrator_output}" if narrator_output else state_header
        if is_new_scene and result.get("tool_call"):
            tc = result["tool_call"]
            if tc.get("description"):
                content += f"\n\n【{tc['scene_name']}】\n{tc['description']}"
        self.brain_messages.append({"role": "user", "content": content})
        if narrator_output:
            self._log_narrator_event("narrator_observe", narrator_output)
        self._sync_memory_snapshots()

        result["scene_changed"] = self.current_scene_name != prev_scene
        return result

    def narrator_inject_narration(self, narration):
        self.narrator_messages.append({"role": "assistant", "content": narration})
        state_header = build_state_header(self.drives, self.current_scene_name)
        self.brain_messages.append({"role": "user", "content": f"{state_header}\n{narration}"})
        self._log_narrator_event("narrator_inject", narration)
        self._sync_memory_snapshots()

    def start_initial_scene(self):
        self.narrator_messages.append({"role": "user", "content": ""})
        result = self.narrator.observe(
            self.narrator_messages,
            memory_summary=self._build_recent_memory_summary(),
        )
        if result.get("narration"):
            narrator_output = result["narration"]
            self.narrator_messages.append({"role": "assistant", "content": narrator_output})
            state_header = build_state_header(self.drives, self.current_scene_name)
            self.brain_messages.append({
                "role": "user",
                "content": f"{state_header}\n{narrator_output}",
            })
            self._log_narrator_event("initial_scene", narrator_output)
            self._sync_memory_snapshots()
            return [{"type": "narrator", "content": narrator_output}]

        initial_scene = self.world.get_default_scene()
        scene_desc = initial_scene.get("description", "")
        if not scene_desc:
            scene_desc = f"你来到了{self.current_scene_name}。"
        state_header = build_state_header(self.drives, self.current_scene_name)
        self.brain_messages.append({
            "role": "user",
            "content": f"{state_header}\n{scene_desc}",
        })
        self._log_narrator_event("initial_scene_fallback", scene_desc)
        self._sync_memory_snapshots()
        return []

    def run_inner_loop(self):
        thought = self.brain_think()
        events = [{"type": "thought", "content": thought}]

        result = self.narrator_observe(thought)
        if result.get("narration"):
            events.append({"type": "narrator", "content": result["narration"]})
        if result.get("scene_changed"):
            events.append({"type": "scene_change", "scene_name": self.current_scene_name})

        return {"thought": thought, "observe": result, "events": events}

    def handle_user_input(self, user_input):
        self.last_user_time = time.time()
        self.user_present = True
        prev_scene = self.current_scene_name
        self._log_brain_event("user_input", user_input, weight=2)

        if not self.narrator_messages:
            narration, new_scene, tool_call, drives_update, scene_objects_update = self.narrator.handle_user_arrival(
                self.narrator_messages,
                user_input,
                self.brain.last_thought,
                memory_summary=self._build_recent_memory_summary(),
            )
        else:
            narration, new_scene, tool_call, drives_update, scene_objects_update = self.narrator.handle_user_message(
                self.narrator_messages,
                user_input,
                self.brain.last_thought,
                memory_summary=self._build_recent_memory_summary(),
            )

        if tool_call:
            wr = self.world.update_scene(tool_call["scene_name"], tool_call["description"])
            if wr.get("success"):
                self.current_scene_name = tool_call["scene_name"]
                self._log_narrator_event("scene_change", f"场景切换到 {self.current_scene_name}")
            else:
                self._log_narrator_event("scene_change_failed", f"场景写入失败: {tool_call.get('scene_name', '')}")

        if drives_update:
            self.drives.update(drives_update)
            self._clamp_drives()
            # 记录完整快照（而非增量），便于重启恢复
            self._log_brain_event("drives_update", dict(self.drives), weight=2)

        if new_scene:
            self.current_scene_name = new_scene
            self._log_narrator_event("scene_change", f"场景切换到 {self.current_scene_name}")

        if scene_objects_update:
            wr = self.world.apply_scene_object_ops(
                scene_objects_update.get("scene_name", self.current_scene_name),
                scene_objects_update.get("operations", []),
            )
            self._log_narrator_event(
                "scene_objects_update",
                f"对象状态更新: {scene_objects_update.get('scene_name', self.current_scene_name)} ({len(wr.get('changed', []))}项)",
            )

        events = []
        if narration:
            self.narrator_inject_narration(narration)
            events.append({"type": "narrator", "content": narration})
        else:
            self.brain_messages.append({"role": "user", "content": user_input})

        if self.current_scene_name != prev_scene:
            events.append({"type": "scene_change", "scene_name": self.current_scene_name})

        reply = self.brain_respond(user_input)
        self.sleep_mode = False
        events.append({"type": "brain", "content": reply})
        self._sync_memory_snapshots()

        return {"reply": reply, "events": events}

    def handle_user_timeout(self):
        self.user_present = False
        events = [{"type": "system", "content": "用户安静地离开了……"}]

        leave_narration = self.narrator.handle_user_leave(
            self.narrator_messages,
            memory_summary=self._build_recent_memory_summary(),
        )
        if leave_narration:
            self.narrator_inject_narration(leave_narration)
            events.append({"type": "narrator", "content": leave_narration})
            self._log_narrator_event("user_leave", leave_narration)

        inner = self.run_inner_loop()
        events.extend(inner.get("events", []))
        self._sync_memory_snapshots()
        return {"events": events, "thought": inner.get("thought")}

    def _get_fatigue_value(self):
        fatigue_val = 0
        for k, v in self.drives.items():
            key = str(k)
            if "疲" in key or "fatigue" in key.lower():
                fatigue_val = max(fatigue_val, v)
        return fatigue_val

    def enter_sleep_mode(self):
        if self.sleep_mode:
            return None
        self.sleep_mode = True
        thought = "……（沉睡中，呼吸平稳）"
        if hasattr(self.brain, "ctx") and hasattr(self.brain.ctx, "internal_monologue"):
            self.brain.ctx.internal_monologue.append(thought)
        if hasattr(self.brain, "last_thought"):
            self.brain.last_thought = thought
        self.brain_messages.append({"role": "assistant", "content": thought})
        self.narrator_messages.append({"role": "user", "content": thought})
        self._log_brain_event("sleep", thought)
        self._sync_memory_snapshots()
        return thought

    def get_idle_action(self, now=None):
        now = now if now is not None else time.time()

        if self.user_present and now - self.last_user_time > self.user_timeout:
            return {"action": "user_timeout", "remaining": 0}

        if now - self.last_think_time < self.think_interval:
            return {"action": "wait", "remaining": self.think_interval - (now - self.last_think_time)}

        if self.user_present:
            return {"action": "wait", "remaining": self.think_interval}

        hour = time.localtime().tm_hour
        is_night = hour >= 21 or hour < 6
        fatigue_val = self._get_fatigue_value()

        if is_night and fatigue_val >= 80 and not self.sleep_mode:
            return {"action": "sleep", "remaining": 0}
        if not is_night or fatigue_val < 50:
            return {"action": "run_inner_loop", "remaining": 0}
        return {"action": "idle", "remaining": 0}

    def tick(self, now=None):
        now = now if now is not None else time.time()
        decision = self.get_idle_action(now=now)
        action = decision["action"]

        if action == "wait":
            return {"status": "wait", "remaining": decision["remaining"], "events": []}
        if action == "user_timeout":
            result = self.handle_user_timeout()
            self.last_think_time = now
            return {"status": "ok", "thought": result.get("thought"), "events": result.get("events", [])}
        if action == "sleep":
            thought = self.enter_sleep_mode()
            self.last_think_time = now
            events = [{"type": "thought", "content": thought}] if thought else []
            return {"status": "ok", "thought": thought, "events": events}
        if action == "run_inner_loop":
            self.sleep_mode = False
            result = self.run_inner_loop()
            self.last_think_time = now
            return {"status": "ok", "thought": result.get("thought"), "events": result.get("events", [])}

        self.last_think_time = now
        return {"status": "ok", "thought": None, "events": []}

    def get_status(self):
        return {
            "scene": self.current_scene_name,
            "last_thought": getattr(self.brain, "last_thought", ""),
            "drives": dict(self.drives),
            "user_present": self.user_present,
            "memory_summary": self._build_recent_memory_summary(max_items=3),
            "world": self._get_world_objects_status(),
        }


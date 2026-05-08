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

    def _clamp_drives(self):
        for k, v in self.drives.items():
            self.drives[k] = max(-100, min(100, v))

    def brain_think(self):
        thought = self.brain.internal_think(
            messages=self.brain_messages,
            drives=self.drives,
            current_scene_info={"name": self.current_scene_name, "description": ""},
        )
        self.brain_messages.append({"role": "assistant", "content": thought})
        return thought

    def brain_respond(self, user_input):
        reply = self.brain.respond(
            messages=self.brain_messages,
            user_input=user_input,
            drives=self.drives,
            current_scene_info={"name": self.current_scene_name, "description": ""},
        )
        self.brain_messages.append({"role": "assistant", "content": reply})
        return reply

    def narrator_observe(self, brain_thought):
        self.narrator_messages.append({"role": "user", "content": brain_thought})
        prev_scene = self.current_scene_name
        result = self.narrator.observe(self.narrator_messages)

        if not result.get("narration"):
            result["scene_changed"] = False
            return result

        narrator_output = result["narration"]
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
                    elif args.get("scene_name"):
                        self.current_scene_name = args["scene_name"]
                    self.narrator_messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(wr, ensure_ascii=False),
                    })
                elif tc_name == "update_drives":
                    drives_update = args.get("drives", {})
                    self.drives.update(drives_update)
                    self._clamp_drives()
                    self.narrator_messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps({"success": True, "drives": self.drives}, ensure_ascii=False),
                    })
        else:
            self.narrator_messages.append({"role": "assistant", "content": narrator_output})
            if result.get("scene_name"):
                self.current_scene_name = result["scene_name"]

        state_header = build_state_header(self.drives, self.current_scene_name)
        content = f"{state_header}\n{narrator_output}"
        if is_new_scene and result.get("tool_call"):
            tc = result["tool_call"]
            if tc.get("description"):
                content += f"\n\n【{tc['scene_name']}】\n{tc['description']}"
        self.brain_messages.append({"role": "user", "content": content})

        result["scene_changed"] = self.current_scene_name != prev_scene
        return result

    def narrator_inject_narration(self, narration):
        self.narrator_messages.append({"role": "assistant", "content": narration})
        state_header = build_state_header(self.drives, self.current_scene_name)
        self.brain_messages.append({"role": "user", "content": f"{state_header}\n{narration}"})

    def start_initial_scene(self):
        self.narrator_messages.append({"role": "user", "content": ""})
        result = self.narrator.observe(self.narrator_messages)
        if result.get("narration"):
            narrator_output = result["narration"]
            self.narrator_messages.append({"role": "assistant", "content": narrator_output})
            state_header = build_state_header(self.drives, self.current_scene_name)
            self.brain_messages.append({
                "role": "user",
                "content": f"{state_header}\n{narrator_output}",
            })
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

        if not self.narrator_messages:
            narration, new_scene, tool_call, drives_update = self.narrator.handle_user_arrival(
                self.narrator_messages, user_input, self.brain.last_thought
            )
        else:
            narration, new_scene, tool_call, drives_update = self.narrator.handle_user_message(
                self.narrator_messages, user_input, self.brain.last_thought
            )

        if tool_call:
            wr = self.world.update_scene(tool_call["scene_name"], tool_call["description"])
            if wr.get("success"):
                self.current_scene_name = tool_call["scene_name"]

        if drives_update:
            self.drives.update(drives_update)
            self._clamp_drives()

        if new_scene:
            self.current_scene_name = new_scene

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

        return {"reply": reply, "events": events}

    def handle_user_timeout(self):
        self.user_present = False
        events = [{"type": "system", "content": "用户安静地离开了……"}]

        leave_narration = self.narrator.handle_user_leave(self.narrator_messages)
        if leave_narration:
            self.narrator_inject_narration(leave_narration)
            events.append({"type": "narrator", "content": leave_narration})

        inner = self.run_inner_loop()
        events.extend(inner.get("events", []))
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
            "drives": self.drives,
            "user_present": self.user_present,
        }


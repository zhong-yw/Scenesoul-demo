import argparse
import os
import sys
import time
import json
import threading
import queue

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

from llm_client import LLMClient
from brain.brain_agent import BrainAgent
from narrator.narrator_agent import NarratorAgent
from ui.cli_renderer import CliRenderer
from world.world_builder import WorldBuilder
from context_builders import build_state_header

THINK_INTERVAL = int(os.getenv("THINK_INTERVAL", "10"))
USER_TIMEOUT = int(os.getenv("USER_TIMEOUT", "600"))


# ── Windows 控制台输入（兼容 IME） ──

def _init_console_input():
    """初始化 Windows 控制台输入 API（兼容拼音等 IME）"""
    try:
        import ctypes
        from ctypes import wintypes

        STD_INPUT_HANDLE = -10
        KEY_EVENT = 0x01

        class KEY_EVENT_RECORD(ctypes.Structure):
            _fields_ = [
                ("bKeyDown", wintypes.BOOL),
                ("wRepeatCount", wintypes.WORD),
                ("wVirtualKeyCode", wintypes.WORD),
                ("wVirtualScanCode", wintypes.WORD),
                ("uChar", wintypes.WCHAR),
                ("dwControlKeyState", wintypes.DWORD),
            ]

        class INPUT_RECORD(ctypes.Structure):
            _fields_ = [
                ("EventType", wintypes.WORD),
                ("Event", KEY_EVENT_RECORD),
            ]

        _handle = ctypes.windll.kernel32.GetStdHandle(STD_INPUT_HANDLE)
        _input_record = INPUT_RECORD()
        _events_read = wintypes.DWORD()
        _events_available = wintypes.DWORD()

        VK_MAP = {
            0x25: "K",   # Left
            0x27: "M",   # Right
            0x24: "G",   # Home
            0x23: "O",   # End
            0x2E: "S",   # Delete
        }

        def kbhit():
            ctypes.windll.kernel32.GetNumberOfConsoleInputEvents(
                _handle, ctypes.byref(_events_available))
            return _events_available.value > 0

        def getwch():
            ctypes.windll.kernel32.ReadConsoleInputW(
                _handle, ctypes.byref(_input_record), 1, ctypes.byref(_events_read))
            if _input_record.EventType == KEY_EVENT and _input_record.Event.bKeyDown:
                ch = _input_record.Event.uChar
                if ch:
                    return ch
                vk = _input_record.Event.wVirtualKeyCode
                if vk in VK_MAP:
                    return "\x00" + VK_MAP[vk]
            return None

        return kbhit, getwch
    except Exception:
        return None, None


_kbhit, _getwch = _init_console_input()


def parse_args():
    parser = argparse.ArgumentParser(description="白界 · Scenesoul 虚拟生命")
    parser.add_argument("--preset", "-p", help="选择预设（profiles 目录名）")
    parser.add_argument("--list-presets", action="store_true", help="列出所有可用预设")
    parser.add_argument("--debug", action="store_true", help="显示界说原始 LLM 输出")
    return parser.parse_args()


def list_presets():
    from profiles.profile_loader import ProfileLoader
    presets = ProfileLoader.get_available_profiles()
    print("\n可用世界预设（Markdown 配置）：\n")
    for p in presets:
        print(f"  {p['id']}")
        print(f"    名称：{p['label']}")
        print(f"    配置：profiles/{p['id']}/ 下的 6 个 .md 文件\n")
    if presets:
        print(f"使用方式：python main.py --preset {presets[0]['id']}\n")
    else:
        print("  (无可用预设，请创建 profiles/<名称>/ 目录)\n")
    sys.exit(0)


# ── 后台任务函数 ──

def _background_task(loop, task):
    """在后台线程执行 LLM 调用，结果放入 loop._result_queue"""
    task_type = task["type"]
    try:
        if task_type == "handle_user_input":
            _task_handle_user_input(loop, task["user_input"])
        elif task_type == "run_inner_loop":
            _task_run_inner_loop(loop)
        elif task_type == "handle_user_timeout":
            _task_handle_user_timeout(loop)
        loop._result_queue.put({"type": task_type, "success": True})
    except Exception as e:
        loop._result_queue.put({"type": task_type, "success": False, "error": str(e)})


def _task_handle_user_input(loop, user_input):
    """后台：用户输入处理（2 次 LLM 调用）

    流程：界说编织 → 大脑回答 → 停，等待用户下次输入
    不调用 narrator_observe()，让循环停下来等用户。
    """
    prev_scene = loop.current_scene_name

    # Phase 1: 界说编织用户消息融入场景
    loop.renderer.show_thinking("界说正在编织场景...")
    if not loop.narrator_messages:
        narration, new_scene, tool_call, drives_update = loop.narrator.handle_user_arrival(
            loop.narrator_messages, user_input, loop.brain.last_thought
        )
    else:
        narration, new_scene, tool_call, drives_update = loop.narrator.handle_user_message(
            loop.narrator_messages, user_input, loop.brain.last_thought
        )

    # 处理 tool_call（创建/更新场景）
    if tool_call:
        wr = loop.world.update_scene(tool_call["scene_name"], tool_call["description"])
        if wr.get("success"):
            loop.current_scene_name = tool_call["scene_name"]

    # 处理驱动力更新
    if drives_update:
        loop.drives.update(drives_update)
        for k, v in loop.drives.items():
            loop.drives[k] = max(-100, min(100, v))

    if new_scene:
        loop.current_scene_name = new_scene
    if narration:
        loop.narrator_inject_narration(narration)
    else:
        loop.brain_messages.append({"role": "user", "content": user_input})

    if loop.current_scene_name != prev_scene:
        loop.renderer.print_scene_change(loop.current_scene_name)

    # Phase 2: 大脑回应
    loop.renderer.show_thinking("大脑正在思考回应...")
    loop.brain_respond(user_input)
    loop.sleep_mode = False


def _task_run_inner_loop(loop):
    """后台：大脑内心独白 + 界说观测（2 次 LLM 调用）"""
    loop.renderer.show_thinking("大脑正在思考...")
    thought = loop.brain_think()

    loop.renderer.show_thinking("界说正在观测...")
    loop.narrator_observe(thought)


def _task_handle_user_timeout(loop):
    """后台：用户超时处理"""
    loop.user_present = False
    loop.renderer.print_system("用户安静地离开了……")

    loop.renderer.show_thinking("界说正在描述离开...")
    leave_narration = loop.narrator.handle_user_leave(loop.narrator_messages)
    if leave_narration:
        loop.narrator_inject_narration(leave_narration)

    # 大脑继续思考
    _task_run_inner_loop(loop)


class ScenesoulLoop:
    """白界主循环 — 管理双消息列表和驱动流程"""

    def __init__(self, brain, narrator, world, renderer, current_scene_name, profile_name="default"):
        self.brain = brain
        self.narrator = narrator
        self.world = world
        self.renderer = renderer

        # 双消息列表
        self.brain_messages = []
        self.narrator_messages = []

        # 状态 — 从 soul.md traits 读取初始驱动力
        from profiles.profile_loader import ProfileLoader
        self.drives = ProfileLoader.get_initial_drives(profile_name)
        self.current_scene_name = current_scene_name
        self.user_present = False
        self.sleep_mode = False
        self.last_think_time = time.time()
        self.last_user_time = 0

        # 后台任务状态
        self.processing = False
        self._task_queue = queue.Queue()
        self._result_queue = queue.Queue()

    # ── 任务提交与结果排空 ──

    def _submit_task(self, task):
        """启动后台线程执行 LLM 任务"""
        self.processing = True
        t = threading.Thread(target=_background_task, args=(self, task), daemon=True)
        t.start()

    def _drain_results(self):
        """主线程每轮调用：检查后台任务完成状态，处理排队输入"""
        while not self._result_queue.empty():
            try:
                result = self._result_queue.get_nowait()
            except queue.Empty:
                break
            self.renderer.clear_thinking()
            self.processing = False
            if not result.get("success"):
                self.renderer.print_system(f"处理出错: {result.get('error', '未知错误')}")

        # 处理排队的用户输入
        if not self.processing and not self._task_queue.empty():
            try:
                queued = self._task_queue.get_nowait()
                self._submit_task({"type": "handle_user_input", "user_input": queued})
            except queue.Empty:
                pass

    # ── 原子操作（无 LLM 调用） ──

    def brain_think(self):
        """大脑内心独白 → 追加到 brain_messages"""
        thought = self.brain.internal_think(
            messages=self.brain_messages,
            drives=self.drives,
            current_scene_info={"name": self.current_scene_name, "description": ""},
        )
        self.renderer.print_brain_thought(thought)
        self.brain_messages.append({"role": "assistant", "content": thought})
        return thought

    def brain_respond(self, user_input):
        """大脑回应 → 追加到 brain_messages"""
        reply = self.brain.respond(
            messages=self.brain_messages,
            user_input=user_input,
            drives=self.drives,
            current_scene_info={"name": self.current_scene_name, "description": ""},
        )
        self.renderer.print_brain_thought(reply)
        self.brain_messages.append({"role": "assistant", "content": reply})
        return reply

    def narrator_observe(self, brain_thought):
        """界说观测 → 处理输出 + tool_call + 拼接状态 → 追加到两个列表"""
        self.narrator_messages.append({"role": "user", "content": brain_thought})
        prev_scene = self.current_scene_name
        result = self.narrator.observe(self.narrator_messages)

        if not result.get("narration"):
            return result

        narrator_output = result["narration"]
        is_new_scene = False

        # ── 收集所有 tool_calls ──
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

        # ── 处理 tool_calls ──
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
                    for k, v in self.drives.items():
                        self.drives[k] = max(-100, min(100, v))
                    self.narrator_messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps({"success": True, "drives": self.drives}, ensure_ascii=False),
                    })
        else:
            self.narrator_messages.append({"role": "assistant", "content": narrator_output})
            if result.get("scene_name"):
                self.current_scene_name = result["scene_name"]

        # ── 写入大脑消息列表 ──
        state_header = build_state_header(self.drives, self.current_scene_name)
        content = f"{state_header}\n{narrator_output}"

        if is_new_scene and result.get("tool_call"):
            tc = result["tool_call"]
            if tc.get("description"):
                content += f"\n\n【{tc['scene_name']}】\n{tc['description']}"

        self.brain_messages.append({"role": "user", "content": content})
        self.renderer.print_narration(narrator_output)

        if self.current_scene_name != prev_scene:
            self.renderer.print_scene_change(self.current_scene_name)

        return result

    def narrator_inject_narration(self, narration):
        """将界说的旁白直接追加到两个列表"""
        self.narrator_messages.append({"role": "assistant", "content": narration})
        state_header = build_state_header(self.drives, self.current_scene_name)
        self.brain_messages.append({
            "role": "user",
            "content": f"{state_header}\n{narration}",
        })
        self.renderer.print_narration(narration)

    def start_initial_scene(self):
        """初始场景触发（同步，启动时调用）"""
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
            self.renderer.print_narration(narrator_output)
        else:
            initial_scene = self.world.get_default_scene()
            scene_desc = initial_scene.get("description", "")
            if not scene_desc:
                scene_desc = f"你来到了{self.current_scene_name}。"
            state_header = build_state_header(self.drives, self.current_scene_name)
            self.brain_messages.append({
                "role": "user",
                "content": f"{state_header}\n{scene_desc}",
            })

    # ── 提交后台任务的包装器 ──

    def run_inner_loop(self):
        """提交内心独白任务到后台"""
        if self.processing:
            return
        self._submit_task({"type": "run_inner_loop"})

    def handle_user_timeout(self):
        """提交超时处理任务到后台"""
        if self.processing:
            return
        self._submit_task({"type": "handle_user_timeout"})

    def handle_user_input(self, user_input):
        """用户输入：立即更新状态 + 提交后台任务"""
        self.last_user_time = time.time()
        self.user_present = True
        self.renderer.print_user_message(user_input)

        if self.processing:
            self._task_queue.put(user_input)
            self.renderer.print_system("消息已排队，等待当前任务完成...")
            return

        self._submit_task({"type": "handle_user_input", "user_input": user_input})


def run_cli(preset_name=None, debug=False):
    renderer = CliRenderer()
    renderer.start()

    import __main__
    __main__._renderer = renderer

    renderer.print_system("正在唤醒大脑和界说……")

    world = WorldBuilder(preset_name=preset_name)
    profile_name = world.get_profile_name() or "default"

    if world.is_profile_mode():
        renderer.print_system(f"使用预设：{profile_name}")
    else:
        renderer.print_system("使用默认配置")

    llm = LLMClient()

    # ── 初始化 Agent ──
    brain = BrainAgent(llm, profile_name=profile_name)
    narrator = NarratorAgent(llm, profile_name=profile_name)
    narrator.debug = debug

    __main__._brain = brain
    __main__._narrator = narrator

    # ── 构建初始场景 ──
    initial_scene = world.get_default_scene()
    current_scene_name = initial_scene.get("name", "卧室")

    # 显示世界设定
    from profiles.profile_loader import ProfileLoader
    _, world_body = ProfileLoader.load_world(profile_name)
    if world_body:
        renderer.print_system(world_body)
    renderer.print_scene_change(current_scene_name)
    scene_desc = initial_scene.get("description", "")
    if scene_desc:
        renderer.print_system(scene_desc)

    # ── 初始化主循环 ──
    loop = ScenesoulLoop(brain, narrator, world, renderer, current_scene_name, profile_name=profile_name)
    __main__._loop = loop

    # ── 初始触发（同步） ──
    loop.start_initial_scene()
    loop.run_inner_loop()
    loop.last_think_time = time.time()

    # ── 主循环 ──
    POLL_INTERVAL = 0.05
    try:
        while renderer.running:
            # 1. 排空后台任务结果
            loop._drain_results()

            # 2. 键盘输入
            if _kbhit and _getwch:
                while _kbhit():
                    ch = _getwch()
                    if not ch:
                        continue
                    renderer.handle_key(ch)
                    if renderer.input_submitted:
                        user_text = renderer.get_submitted_text()
                        if user_text.startswith("/"):
                            renderer.execute_command(user_text)
                        elif user_text:
                            loop.handle_user_input(user_text)
                            loop.last_think_time = time.time()

            now = time.time()

            # 3. 用户超时检测
            if not loop.processing and loop.user_present and now - loop.last_user_time > USER_TIMEOUT:
                loop.handle_user_timeout()
                loop.last_think_time = now

            # 4. 定时内心独白
            if not loop.processing and not loop.user_present and now - loop.last_think_time >= THINK_INTERVAL:
                hour = time.localtime().tm_hour
                is_night = hour >= 21 or hour < 6

                # 查找疲劳相关驱动力（支持中英文键名）
                fatigue_val = 0
                for k, v in loop.drives.items():
                    if "疲" in k or "fatigue" in k.lower():
                        fatigue_val = max(fatigue_val, v)

                if is_night and fatigue_val >= 80 and not loop.sleep_mode:
                    loop.sleep_mode = True
                    renderer.print_system("夜深了，大脑渐渐进入沉睡……")
                    thought = "……（沉睡中，呼吸平稳）"
                    brain.ctx.internal_monologue.append(thought)
                    brain.last_thought = thought
                    renderer.print_brain_thought(thought)
                    loop.brain_messages.append({"role": "assistant", "content": thought})
                    loop.narrator_messages.append({"role": "user", "content": thought})
                    loop.last_think_time = now - THINK_INTERVAL * 2
                elif not is_night or fatigue_val < 50:
                    loop.sleep_mode = False
                    loop.run_inner_loop()
                loop.last_think_time = now

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        renderer.shutdown()
        sys.exit(0)

    renderer.shutdown()


if __name__ == "__main__":
    args = parse_args()
    if args.list_presets:
        list_presets()
    run_cli(preset_name=args.preset, debug=args.debug)

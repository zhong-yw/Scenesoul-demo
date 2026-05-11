import argparse
import os
import sys
import time
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
from runtime.scenesoul_runtime import ScenesoulRuntime


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
    parser.add_argument("--web", action="store_true", help="启动 Web UI 模式")
    parser.add_argument("--host", default="0.0.0.0", help="Web UI 监听地址（仅 --web 有效）")
    parser.add_argument("--port", type=int, default=5000, help="Web UI 端口（仅 --web 有效）")
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
    """后台：用户输入处理"""
    loop.renderer.show_thinking("正在处理用户输入...")
    loop.handle_user_input_sync(user_input)


def _task_run_inner_loop(loop):
    """后台：大脑内心独白 + 界说观测（2 次 LLM 调用）"""
    loop.renderer.show_thinking("大脑正在思考...")
    thought = loop.brain_think()

    loop.renderer.show_thinking("界说正在观测...")
    loop.narrator_observe(thought)


def _task_handle_user_timeout(loop):
    """后台：用户超时处理"""
    loop.renderer.show_thinking("正在处理用户超时...")
    loop.handle_user_timeout_sync()


class ScenesoulLoop:
    """白界 CLI 控制器 — 负责后台任务调度 + 事件渲染

    职责明确：
    - 持有 Runtime（状态流转核心）和 Renderer（终端渲染）
    - 管理后台 LLM 任务的提交、排队、结果处理
    - 将 Runtime 产出的事件渲染到终端

    状态访问：直接通过 loop.runtime.* 读写，不做代理转发。
    """

    def __init__(self, brain, narrator, world, renderer, current_scene_name, profile_name="default"):
        self.renderer = renderer

        # 共享 Runtime（CLI/Web 共用）
        self.runtime = ScenesoulRuntime(
            brain=brain,
            narrator=narrator,
            world=world,
            current_scene_name=current_scene_name,
            profile_name=profile_name,
        )

        # 后台任务状态
        self.processing = False
        self._task_queue = queue.Queue()
        self._result_queue = queue.Queue()

    # ── 兼容属性（供测试和外部代码平滑迁移，后续可移除） ──

    @property
    def brain_messages(self):
        return self.runtime.brain_messages

    @property
    def narrator_messages(self):
        return self.runtime.narrator_messages

    @property
    def drives(self):
        return self.runtime.drives

    @property
    def current_scene_name(self):
        return self.runtime.current_scene_name

    @property
    def user_present(self):
        return self.runtime.user_present

    # ── 后台任务调度 ──

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

    # ── 事件渲染 ──

    def _render_events(self, events):
        """将 Runtime 事件列表渲染到终端"""
        for event in events:
            event_type = event.get("type")
            content = event.get("content", "")
            if event_type in ("thought", "brain"):
                self.renderer.print_brain_thought(content)
            elif event_type == "narrator":
                self.renderer.print_narration(content)
            elif event_type == "scene_change":
                self.renderer.print_scene_change(
                    event.get("scene_name", self.runtime.current_scene_name)
                )
            elif event_type == "system":
                self.renderer.print_system(content)

    # ── Runtime 操作 + 渲染（同步，供后台线程调用） ──

    def brain_think(self):
        """大脑内心独白（同步）"""
        thought = self.runtime.brain_think()
        self.renderer.print_brain_thought(thought)
        return thought

    def narrator_observe(self, brain_thought):
        """界说观测（同步）"""
        result = self.runtime.narrator_observe(brain_thought)
        if result.get("narration"):
            self.renderer.print_narration(result["narration"])
        if result.get("scene_changed"):
            self.renderer.print_scene_change(self.runtime.current_scene_name)
        return result

    def start_initial_scene(self):
        """初始场景触发（同步，启动时调用）"""
        events = self.runtime.start_initial_scene()
        self._render_events(events)

    def handle_user_input_sync(self, user_input):
        """处理用户输入（同步，后台线程调用）"""
        result = self.runtime.handle_user_input(user_input)
        self._render_events(result.get("events", []))
        return result

    def handle_user_timeout_sync(self):
        """处理用户超时（同步，后台线程调用）"""
        result = self.runtime.handle_user_timeout()
        self._render_events(result.get("events", []))
        return result

    # ── 异步任务提交（主线程调用，不阻塞） ──

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
        self.runtime.last_user_time = time.time()
        self.runtime.user_present = True
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

    # ── 构建初始场景（default 作为 Runtime 构造参数） ──
    initial_scene = world.get_default_scene()
    default_scene_name = initial_scene.get("name", "卧室")

    # ── 初始化主循环（Runtime 内部会从日志恢复 scene / drives） ──
    loop = ScenesoulLoop(brain, narrator, world, renderer, default_scene_name, profile_name=profile_name)
    __main__._loop = loop
    rt = loop.runtime

    # ── 显示世界设定 + 真实（恢复后）场景 ──
    from profiles.profile_loader import ProfileLoader
    _, world_body = ProfileLoader.load_world(profile_name)
    if world_body:
        renderer.print_system(world_body)
    renderer.print_scene_change(rt.current_scene_name)
    # 只有当仍然停留在 default 场景时才展示其描述，避免与恢复场景冲突
    if rt.current_scene_name == default_scene_name:
        scene_desc = initial_scene.get("description", "")
        if scene_desc:
            renderer.print_system(scene_desc)

    # ── 初始触发（同步） ──
    loop.start_initial_scene()
    loop.run_inner_loop()
    rt.last_think_time = time.time()

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
                            rt.last_think_time = time.time()

            now = time.time()

            # 3. Runtime 决策（超时 / 定时思考 / 睡眠）
            if not loop.processing:
                decision = rt.get_idle_action(now=now)
                action = decision.get("action")
                if action == "user_timeout":
                    loop.handle_user_timeout()
                    rt.last_think_time = now
                elif action == "run_inner_loop":
                    rt.sleep_mode = False
                    loop.run_inner_loop()
                    rt.last_think_time = now
                elif action == "sleep":
                    renderer.print_system("夜深了，大脑渐渐进入沉睡……")
                    thought = rt.enter_sleep_mode()
                    if thought:
                        renderer.print_brain_thought(thought)
                    rt.last_think_time = now
                elif action == "idle":
                    rt.last_think_time = now

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        renderer.shutdown()
        sys.exit(0)

    renderer.shutdown()


if __name__ == "__main__":
    args = parse_args()
    if args.list_presets:
        list_presets()
    if args.web:
        from ui.web_server import start_web
        start_web(host=args.host, port=args.port, preset_name=args.preset, debug=args.debug)
    else:
        run_cli(preset_name=args.preset, debug=args.debug)

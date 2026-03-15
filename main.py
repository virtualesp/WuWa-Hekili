import sys
import os
import time

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

# 导入 UI
from ui.start_menu import StartMenu
from ui.overlay_window import HekiliOverlay
from ui.settings_window import SettingsWindow
from ui.routine_uploader import RoutineUploaderWindow
from ui.routine_selector import RoutineSelector  # 确保导入了选择器

# 导入逻辑核心
from utils.asset_manager import AssetManager
from utils.input_listener import InputListener
from utils.logger import log
from core.preset.director import Director
import json


class HekiliApp:
    def __init__(self, app_instance):
        self.app = app_instance
        self.is_active = False
        self.overlay = None
        self.director = None
        self.input_thread = None
        self.heartbeat_timer = None

        self.menu = StartMenu()
        self.settings_win = SettingsWindow()
        self.uploader_win = RoutineUploaderWindow()
        self.selector_win = RoutineSelector()  # 初始化选择器

        self._connect_signals()

    def _connect_signals(self):
        self.menu.open_settings.connect(self.settings_win.show)
        self.menu.open_upload.connect(self.uploader_win.show)
        # 点击"流程选择" -> 显示选择器
        self.menu.open_select.connect(self.selector_win.show)

        # 选择器选中后 -> 启动核心
        self.selector_win.routine_selected.connect(self.start_execution)

        self.settings_win.config_saved.connect(self.on_config_reload)

        self.selector_win.edit_requested.connect(self.uploader_win.load_existing_routine)

    def run(self):
        log.info("============== 🚀 Hekili 启动 ==============")
        self.menu.show()
        return self.app.exec()

    def refresh_ui(self, is_advance=False):
        if self.overlay and self.director:
            data = self.director.get_visual_data(preview_count=3)
            self.overlay.update_ui(data, is_advance=is_advance)

    def stop_execution(self):
        """停止战斗悬浮窗，返回主菜单"""
        log.info("🛑 正在停止悬浮窗，返回主菜单...")

        # 1. 停止一切后台活动
        self.is_active = False
        if self.heartbeat_timer:
            self.heartbeat_timer.stop()
        if self.input_thread:
            self.input_thread.stop()
            self.input_thread.wait()  # 等待线程安全关闭
            self.input_thread = None

        # 2. 关闭悬浮窗
        if self.overlay:
            self.overlay.close()
            self.overlay.deleteLater()
            self.overlay = None
            self.director = None

        # 3. 显示主菜单
        self.menu.show()

    def start_execution(self, json_path):
        """加载 JSON 并启动核心"""
        log.info(f"正在加载流程: {json_path}")

        # 加载 JSON 剧本
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        base_dir = os.path.dirname(os.path.abspath(__file__))
        assets_path = os.path.join(base_dir, "assets", "assets")
        asset_mgr = AssetManager(assets_path)

        # 实例化导演
        self.director = Director(
            team_config={int(k): v for k, v in data["team_config"].items()},
            opener_script=data["opener_script"],
            loop_script=data["loop_script"],
            start_char_index=data["initial_char_index"],
            asset_mgr=asset_mgr
        )

        self.overlay = HekiliOverlay()
        self.overlay.open_settings_signal.connect(self.settings_win.show)
        self.overlay.return_to_menu_signal.connect(self.stop_execution)
        self.overlay.show()

        self.menu.hide()

        self.input_thread = InputListener()
        self.input_thread.action_detected.connect(self.on_action_detected)

        def on_device_switched(device_name):
            # is_advance=False 意味着不播放滑动动画，只是原地更换角落里的按键图标
            self.refresh_ui(is_advance=False)

        self.input_thread.device_switched.connect(on_device_switched)

        self.input_thread.start()

        self.refresh_ui(is_advance=False)
        log.info("✅ 悬浮窗已就绪，按启动键(X)激活...")

    def on_action_detected(self, action_name, is_down):
        # 无论是否激活，只要按下回退键，立刻执行回退并结束本次监听
        if is_down and action_name == "rollback":
            if self.director.rollback():
                self.refresh_ui(is_advance=False)
            return

        # 如果脚本还没启动，我们只等发令枪
        if not self.is_active:
            if is_down and action_name == "start_trigger":
                self.is_active = True
                log.info("🚀 [System] 脚本正式激活！")

                self.director.reset()
                self.refresh_ui(is_advance=False)
                if len(self.overlay.widgets) > 1:
                    self.overlay.widgets[1].setStyleSheet(
                        "ActionWidget { border: 4px solid #00FF00; background-color: rgba(0, 0, 0, 180); border-radius: 8px; }")
            # 未激活时，所有其他按键全被这里的 return 拦截丢弃
            return

        # 能走到这里的，一定是“已经激活了”，并且“不是回退键”的动作
        if self.director.input_received(action_name, is_down):
            self.refresh_ui(is_advance=True)


    def on_config_reload(self):
        if self.input_thread and self.input_thread.isRunning():
            self.input_thread.reload_mapping()
        if self.overlay:
            self.refresh_ui(is_advance=False)

    def cleanup(self):
        if self.input_thread:
            self.input_thread.stop()


if __name__ == "__main__":
    if getattr(sys, 'frozen', False):
        os.chdir(os.path.dirname(sys.executable))
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    controller = HekiliApp(app)
    ret_code = controller.run()
    controller.cleanup()
    sys.exit(ret_code)
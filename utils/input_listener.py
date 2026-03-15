import pygame
import keyboard
import ctypes
import time
from PySide6.QtCore import QThread, Signal
from utils.config_manager import config
from utils.logger import log


class InputListener(QThread):
    action_detected = Signal(str, bool)
    device_switched = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = True
        self.joystick = None
        self.last_device_switch_time = 0  # 热切换防抖冷却

        self.button_id_to_action = {}
        self.hat_val_to_action = {}
        self.axis_id_to_action = {}
        self.axis_states = {}

        self.key_to_action = {}
        self.mouse_to_action = {}
        self.mouse_states = {"left": False, "right": False, "middle": False}
        self._raw_mouse_left = False

        self._build_lookup_table()

    def _build_lookup_table(self):
        log.info("🔍 --- 正在构建双端智能输入映射表 ---")

        action_map_xbox = config.get("keymaps.xbox", {})

        ctrl_buttons = config.get("controller.buttons", {})
        ctrl_axes = config.get("controller.axes", {})
        ctrl_hats = config.get("controller.hats", {})

        for action, filename in action_map_xbox.items():
            if not filename: continue

            # 核心提取
            core_key = \
            filename.replace("xbox_button_color_", "").replace("xbox_button_", "").replace("xbox_", "").split(".")[
                0].lower()

            if core_key in ctrl_buttons:
                self.button_id_to_action[int(ctrl_buttons[core_key])] = action
            elif core_key in ctrl_axes:
                self.axis_id_to_action[ctrl_axes[core_key]] = action
            elif core_key in ctrl_hats:
                self.hat_val_to_action[ctrl_hats[core_key]] = action
            else:
                # 💡 终极暴力保底：如果解析出错了，直接强行比对字符串
                if "dpad_up" in filename:
                    self.hat_val_to_action["0,1"] = action
                elif "dpad_down" in filename:
                    self.hat_val_to_action["0,-1"] = action
                elif "dpad_left" in filename:
                    self.hat_val_to_action["-1,0"] = action
                elif "dpad_right" in filename:
                    self.hat_val_to_action["1,0"] = action
                else:
                    log.warning(f"⚠️ 手柄映射异常: 无法识别图片名 '{filename}'")

            # 将提取出的核心键匹配到对应的硬件 ID 上
            if core_key in ctrl_buttons:
                self.button_id_to_action[ctrl_buttons[core_key]] = action
            elif core_key in ctrl_axes:
                self.axis_id_to_action[ctrl_axes[core_key]] = action
            elif core_key in ctrl_hats:
                self.hat_val_to_action[ctrl_hats[core_key]] = action
            else:
                log.warning(f"⚠️ 手柄映射异常: 无法识别图片名 '{filename}' 中的按键 '{core_key}'")

        action_map_kb = config.get("keymaps.keyboard", {})
        for action, filename in action_map_kb.items():
            if not filename: continue

            if filename.startswith("key_") or filename.startswith("keyboard_"):
                # "keyboard_f" -> "f", "key_space" -> "space"
                real_key = filename.replace("key_", "").replace("keyboard_", "").split("_")[0]
                self.key_to_action[real_key.lower()] = action

            elif filename.startswith("mouse_"):
                if "left" in filename:
                    self.mouse_to_action["left"] = action
                elif "right" in filename:
                    self.mouse_to_action["right"] = action
                elif "middle" in filename:
                    self.mouse_to_action["middle"] = action

        log.info(
            f"🎮 监听就绪: 手柄({len(self.button_id_to_action)}键/{len(self.axis_id_to_action)}轴) | 键盘({len(self.key_to_action)}键) | 鼠标({len(self.mouse_to_action)}键)")

    def reload_mapping(self):
        log.info("🔄[Listener] 正在重载按键映射...")
        self.button_id_to_action.clear()
        self.hat_val_to_action.clear()
        self.axis_id_to_action.clear()
        self.key_to_action.clear()
        self.mouse_to_action.clear()
        self._build_lookup_table()

    def _switch_device_mode(self, device_name):
        current = config.get("settings.current_device")
        if current != device_name:
            current_time = time.time()
            # 💡 防抖锁：0.5秒内禁止重复切换设备
            if current_time - self.last_device_switch_time < 0.5:
                return

            log.info(f"🔄 检测到输入源切换: {current} -> {device_name}")
            config.update_setting("settings.current_device", device_name)
            self.device_switched.emit(device_name)  # 👈 刚才报错的罪魁祸首修好了
            self.last_device_switch_time = current_time

    def _on_keyboard_event(self, event):
        if not self.running: return
        action = self.key_to_action.get(event.name.lower())
        if action:
            if event.event_type == "down":
                self._switch_device_mode("keyboard")
                self.action_detected.emit(action, True)
            elif event.event_type == "up":
                self.action_detected.emit(action, False)

    def run(self):
        pygame.init()
        pygame.joystick.init()
        keyboard.hook(self._on_keyboard_event)
        log.info("🎮 [Listener] 全局监听已启动...")

        mouse_vk_codes = {"left": 0x01, "right": 0x02, "middle": 0x04}

        while self.running:
            # === 1. 鼠标底层轮询 ===
            for btn_name, vk_code in mouse_vk_codes.items():
                action = self.mouse_to_action.get(btn_name)
                state = ctypes.windll.user32.GetAsyncKeyState(vk_code)
                is_pressed = (state & 0x8000) != 0
                was_pressed = self.mouse_states[btn_name]

                if is_pressed and not was_pressed:
                    self.mouse_states[btn_name] = True
                    if action:
                        self._switch_device_mode("keyboard")
                        self.action_detected.emit(action, True)
                elif not is_pressed and was_pressed:
                    self.mouse_states[btn_name] = False
                    if action:
                        self.action_detected.emit(action, False)

            # === 2. 手柄逻辑 ===
            if pygame.joystick.get_count() > 0 and self.joystick is None:
                try:
                    self.joystick = pygame.joystick.Joystick(0)
                    self.joystick.init()
                    log.info(f"✅ [Listener] 已连接手柄: {self.joystick.get_name()}")
                except:
                    pass

            if self.joystick:
                for event in pygame.event.get():
                    if event.type == pygame.JOYBUTTONDOWN:
                        action = self.button_id_to_action.get(event.button)
                        if action:
                            self._switch_device_mode("xbox")
                            self.action_detected.emit(action, True)

                    elif event.type == pygame.JOYBUTTONUP:
                        action = self.button_id_to_action.get(event.button)
                        if action: self.action_detected.emit(action, False)

                    elif event.type == pygame.JOYAXISMOTION:
                        action = self.axis_id_to_action.get(event.axis)
                        if action:
                            val = event.value
                            was_pressed = self.axis_states.get(event.axis, False)
                            if val > 0.6: self._switch_device_mode("xbox")
                            if val > 0.6 and not was_pressed:
                                self.axis_states[event.axis] = True
                                self.action_detected.emit(action, True)
                            elif val < 0.3 and was_pressed:
                                self.axis_states[event.axis] = False
                                self.action_detected.emit(action, False)

                    elif event.type == pygame.JOYHATMOTION:
                        val_str = f"{event.value[0]},{event.value[1]}"
                        action = self.hat_val_to_action.get(val_str)
                        if action:
                            self._switch_device_mode("xbox")
                            self.action_detected.emit(action, True)

            self.msleep(5)

    def stop(self):
        self.running = False
        keyboard.unhook_all()
        pygame.quit()
        self.wait()
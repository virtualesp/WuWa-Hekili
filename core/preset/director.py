import time
from utils.config_manager import config
from utils.logger import log


class Director:
    def __init__(self, team_config, opener_script, loop_script, start_char_index, asset_mgr):
        self.team = team_config
        self.opener = opener_script
        self.loop = loop_script
        self.asset_mgr = asset_mgr

        self.is_in_opener = True if self.opener else False
        self.step_index = 0
        self.current_char_idx = start_char_index

        # 状态机变量
        self.is_holding = False
        self.expected_release_action = None

        # 💡 核心修复：历史状态栈 (用于完美回退)
        # 存储格式: (step_index, is_in_opener, current_char_idx)
        self.history_stack = []

    def get_current_script(self):
        return self.opener if self.is_in_opener else self.loop

    def get_visual_data(self, preview_count=3):
        """获取[历史, 当前, 预告1, 预告2]"""
        result = []
        current_script = self.get_current_script()
        if not current_script: return []

        total_steps = len(current_script)
        # 这里的预览逻辑需要非常严谨地模拟角色切换
        virtual_char_idx = self.current_char_idx

        for i in range(-1, preview_count):
            idx = (self.step_index + i)

            # 处理历史记录预览
            if i == -1:
                if not self.history_stack:
                    result.append({"icon_path": None, "btn_path": None, "desc": "START", "is_history": True})
                    continue
                else:
                    # 从栈顶取上一个真实的状态
                    h_idx, h_opener, h_char = self.history_stack[-1]
                    prev_action = (self.opener if h_opener else self.loop)[h_idx]

                    # 确定历史图标应该属于谁
                    # 如果历史动作是 intro，图标显示的是目标角色
                    display_name = self.team.get(h_char, "Unknown")
                    icon_path = self.asset_mgr.get_icon_path(display_name, prev_action["type"],
                                                             prev_action.get("variant"))
                    result.append({
                        "desc": prev_action.get("desc", ""),
                        "icon_path": icon_path,
                        "btn_path": None,
                        "is_current": False,
                        "is_history": True
                    })
                    continue

            # 处理当前和未来预览
            idx = idx % total_steps
            action = current_script[idx]

            # 💡 关键：预测未来的角色变化
            display_char_idx = virtual_char_idx
            target_idx_arg = None
            if action["type"] == "intro":
                next_c = action.get("next_char")
                if next_c:
                    display_char_idx = next_c
                    if i >= 0: virtual_char_idx = next_c  # 更新后续步骤的预测基准
                    target_idx_arg = next_c

            char_name = self.team.get(display_char_idx, "Unknown")
            icon_path = self.asset_mgr.get_icon_path(char_name, action["type"], action.get("variant"),
                                                     action.get("force_general", False), action.get("custom_icon"))
            btn_path = self.asset_mgr.get_button_path(action["type"], target_index=target_idx_arg)

            result.append({
                "desc": action.get("desc", ""),
                "icon_path": icon_path,
                "btn_path": btn_path,
                "variant": action.get("variant"),
                "char_name": char_name,
                "is_current": (i == 0),
                "is_history": False
            })
        return result

    def input_received(self, input_action, is_down):
        current_script = self.get_current_script()
        if not current_script or self.step_index >= len(current_script): return False

        expected_action = current_script[self.step_index]
        expected_type = expected_action.get("type")

        # 匹配检查
        is_match = False
        if expected_type == "intro":
            if input_action == f"intro_{expected_action.get('next_char')}": is_match = True
        elif input_action == expected_type or (expected_type == "heavy" and input_action == "basic"):
            is_match = True

        # 💡 逻辑分流：哪些动作需要“松开触发”，哪些“按下即触发”？
        # 只有 普攻(basic)、技能(skill)、大招(ult) 建议用松开触发来处理合轴
        # 切人(intro)、闪避(dodge)、跳跃(jump) 必须按下即触发，否则卡手
        is_instant = expected_type in ["intro", "dodge", "jump"]

        if is_down:
            if is_match:
                if is_instant:
                    log.info(f"⚡ 瞬发动作匹配: {input_action}")
                    self.advance()
                    return True
                else:
                    if not self.is_holding:
                        self.is_holding = True
                        self.expected_release_action = input_action
                        log.debug(f"⏳ 缓冲动作确认: {input_action}，等待松开...")
            return False
        else:
            # 松开逻辑
            if self.is_holding and input_action == self.expected_release_action:
                self.is_holding = False
                log.info(f"➡️ 缓冲动作完成: {input_action}")
                self.advance()
                return True
            return False

    def advance(self):
        """推进时保存历史"""
        current_script = self.get_current_script()

        # 1. 存入历史栈 (存入的是当前还没变之前的状态)
        self.history_stack.append((self.step_index, self.is_in_opener, self.current_char_idx))
        if len(self.history_stack) > 20: self.history_stack.pop(0)  # 最多记20步

        # 2. 执行逻辑变更
        current_action = current_script[self.step_index]
        if current_action.get("type") == "intro":
            next_char = current_action.get("next_char")
            if next_char: self.current_char_idx = next_char

        self.step_index += 1
        if self.is_in_opener and self.step_index >= len(self.opener):
            self.is_in_opener = False
            self.step_index = 0
        elif not self.is_in_opener and self.step_index >= len(self.loop):
            self.step_index = 0

    def rollback(self):
        """从历史栈恢复状态"""
        if not self.history_stack:
            log.warning("⚠️ 已经回退到头了，无法再回退")
            return False

        self.is_holding = False
        # 弹出最后一次保存的状态
        prev_step, prev_opener, prev_char = self.history_stack.pop()

        self.step_index = prev_step
        self.is_in_opener = prev_opener
        self.current_char_idx = prev_char

        log.info(f"⏪ 回退成功：回到角色 {self.team.get(self.current_char_idx)}，步骤 {self.step_index}")
        return True

    def reset(self):
        self.step_index = 0
        self.is_in_opener = True if self.opener else False
        self.is_holding = False
        self.history_stack.clear()
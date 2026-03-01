import re
import json
import unittest


class GenericScriptParser:
    def __init__(self, team_mapping, action_mapping=None, macros=None):
        """
        初始化泛式解析器
        :param team_mapping: 角色简称映射，例如 {"爱": (1, "Aalto"), "莫": (2, "Moning")}
        :param action_mapping: 字母映射规则 (可选)
        :param macros: 宏指令映射 (可选)
        """
        self.team_mapping = team_mapping
        self.macros = macros or {}

        # 默认的按键行为映射字典 (泛式核心)
        self.action_mapping = action_mapping or {
            'a': {"type": "basic", "desc": "A 普攻"},
            'z': {"type": "basic", "variant": "heavy", "desc": "Z 重击"},
            'e': {"type": "skill", "desc": "E 技能"},
            'r': {"type": "ult", "desc": "R 大招"},
            'q': {"type": "echo", "desc": "Q 声骸"},
            'f': {"type": "skill", "variant": "forte", "desc": "F 处决"},  # 新增的 f 键
            'd': {"type": "dodge", "desc": "闪避"},
            's': {"type": "dodge", "desc": "闪避"},
        }

        # 引擎启动：根据你提供的字典，动态生成正则提取规则
        self._build_regex()

    def _build_regex(self):
        char_keys = list(self.team_mapping.keys())
        macro_keys = list(self.macros.keys())
        action_keys = "".join(self.action_mapping.keys())

        # 按长度降序，防止短词吃掉长词 (比如"嘉贝"和"嘉")
        char_keys.sort(key=len, reverse=True)
        macro_keys.sort(key=len, reverse=True)

        parts = [r'\(.*?变奏.*?\)', r'（.*?变奏.*?）', r'切']
        if macro_keys:
            parts.extend([re.escape(k) for k in macro_keys])
        if char_keys:
            parts.extend([re.escape(k) for k in char_keys])

        # 动态拼接动作字母:[azerqfd]\d*
        parts.append(rf'[{action_keys}A-Z]\d*')

        # 编译最终的正则表达式
        self.pattern = re.compile("|".join(parts), re.IGNORECASE)

    def parse(self, text, start_char_id=1):
        """解析文本为剧本字典列表"""
        tokens = self.pattern.findall(text)
        result = []
        current_char_id = start_char_id

        for token in tokens:
            t = token.lower()
            if t == '切': continue

            # 1. 宏指令展开
            if token in self.macros:
                result.extend(self.macros[token])
                continue

            # 2. 角色切换 (支持带"变奏"或直接写名字)
            is_char_switch = False
            for char_key, (cid, cname) in self.team_mapping.items():
                if char_key in token:
                    if cid != current_char_id:
                        desc_prefix = "变奏" if "变奏" in token else "切"
                        result.append({"type": "intro", "next_char": cid, "desc": f"{desc_prefix}-{cname}"})
                        current_char_id = cid
                    is_char_switch = True
                    break
            if is_char_switch: continue

            # 3. 战斗动作解析 (提取首字母)
            action_letter = t[0]
            if action_letter in self.action_mapping:
                # 深拷贝，防止修改基础字典
                action_dict = dict(self.action_mapping[action_letter])

                # 处理后面的数字 (如 a1, e2)
                if len(t) > 1:
                    num = t[1:]
                    if action_letter == 'a' and num == '1':
                        action_dict["force_general"] = True
                        action_dict["desc"] += " (通用)"
                    elif "variant" not in action_dict:
                        action_dict["variant"] = num
                        action_dict["desc"] += f"_{num}"

                result.append(action_dict)

        return result

    def export_to_file(self, opener_str, loop_str, output_path="../configs"):
        """导出为标准的 Python 剧本文件"""
        opener_data = self.parse(opener_str)
        loop_data = self.parse(loop_str)

        def format_list(data_list):
            return "\n".join([f"    {json.dumps(item, ensure_ascii=False)}," for item in data_list])

        # 动态生成 TEAM_CONFIG 字符串
        team_config_lines = []
        for char_key, (cid, cname) in self.team_mapping.items():
            team_config_lines.append(f"    {cid}: \"{cname}\", # {char_key}")
        team_config_str = "\n".join(team_config_lines)

        content = f"""# ==========================================
# 🤖 自动生成的泛式连招剧本
# ==========================================

TEAM_CONFIG = {{
{team_config_str}
}}

INITIAL_CHAR_INDEX = 1

OPENER_SCRIPT =[
{format_list(opener_data)}
]

LOOP_SCRIPT = [
{format_list(loop_data)}
]
"""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"🎉 泛式剧本成功生成: {output_path}")


if __name__ == '__main__':
    print("\n--- 开始解析你提供的【爱莫琳】新轴 ---")

    # 🌟 在这里定义你的泛式翻译字典！
    TEAM_DICT = {
        "爱弥斯": (1, "Aemeath"),  # 假设 1号位 是秋水(Aalto)或者别的叫“爱”的角色
        "莫宁": (2, "Moning"),  # 2号位 莫宁
        "琳奈": (3, "Lynae")  # 3号位 琳奈
    }

    raw_opener = "爱aaaa莫aaazraaaezq琳re爱aaaa琳zaaaaq爱aafqreaaaaezraaaa"
    raw_loop = "莫raaaezq琳re爱aaaa琳zaaaaq爱aafqreaaaaezraaaa"

    parser = GenericScriptParser(team_mapping=TEAM_DICT)
    parser.export_to_file(raw_opener, raw_loop, "../configs/team_ai_mo_lin.py")
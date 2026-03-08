import re
import json
import os


class GenericScriptParser:
    def __init__(self, team_mapping):
        self.team_mapping = team_mapping

        # 角色名称简称映射字典
        self.char_lookup = {}
        for full_zh_name, data in self.team_mapping.items():
            cid, en_name, aliases = data
            # 记录全名
            self.char_lookup[full_zh_name] = (cid, en_name, full_zh_name)
            # 记录简称
            for alias in aliases:
                self.char_lookup[alias] = (cid, en_name, full_zh_name)

        # 基础动作字母映射
        self.action_mapping = {
            'a': "basic",
            'e': "skill",
            'r': "ult",
            'q': "echo",
            'j': "jump",
            'z': "basic",  # z 默认处理为重击变体
            'f': "skill",  # f 默认处理为回路变体
            'd': "dodge",
            's': "dodge"
        }

        self._build_regex()

    def _build_regex(self):
        # 提取所有可能的名字/简称，并按长度降序排列 (防止"爱"吃掉"爱弥斯")
        char_keys = sorted(list(self.char_lookup.keys()), key=len, reverse=True)
        action_keys = "".join(self.action_mapping.keys())

        # 正则：匹配变奏、所有的角色名/简称、或者 [动作字母][数字]
        parts = [
            r'\(.*?变奏.*?\)', r'（.*?变奏.*?）', r'切',
            "|".join([re.escape(k) for k in char_keys]),
            rf'[{action_keys}]\d*'  # 匹配 a, a1, e2, z1 等
        ]
        self.pattern = re.compile("|".join(parts), re.IGNORECASE)

    def parse(self, text, start_char_id=1):
        tokens = self.pattern.findall(text)
        result = []
        current_char_id = start_char_id

        # 同样按长度排序，保证匹配时优先匹配长词
        sorted_char_keys = sorted(list(self.char_lookup.keys()), key=len, reverse=True)

        for token in tokens:
            t = token.lower()
            if t == '切': continue

            # 1. 角色切换逻辑
            is_char_switch = False
            for char_key in sorted_char_keys:
                if char_key in t:
                    cid, en_name, full_zh_name = self.char_lookup[char_key]

                    if cid != current_char_id:
                        prefix = "变奏" if "变奏" in t else "切"
                        # 💡 改进：UI的描述(desc)里现在可以显示角色的【中文全名】了，更好看！
                        result.append({"type": "intro", "next_char": cid, "desc": f"{prefix}-{full_zh_name}"})
                        current_char_id = cid
                    is_char_switch = True
                    break
            if is_char_switch: continue

            # 2. 动作解析逻辑：拆分 [字母] 和 [数字]
            match = re.match(rf'([a-z])(\d*)', t)
            if not match: continue

            letter, num = match.groups()
            action_type = self.action_mapping.get(letter)
            if not action_type: continue

            # 组装基础字典
            action_dict = {
                "type": action_type,
                "desc": token.upper()
            }

            variant_parts = []
            if letter == 'z': variant_parts.append("heavy")
            if letter == 'f': variant_parts.append("forte")

            if num:
                if letter == 'a' and num == '1':
                    action_dict["force_general"] = True
                    variant_parts.append("1")
                else:
                    variant_parts.append(num)

            if variant_parts:
                action_dict["variant"] = "_".join(variant_parts)

            result.append(action_dict)

        return result

    def export_to_file(self, opener_str, loop_str, filename, folder="../configs"):
        # 1. 处理路径
        if not os.path.exists(folder):
            os.makedirs(folder)

        if not filename.endswith(".py"):
            filename += ".py"

        full_path = os.path.join(folder, filename)

        # 2. 解析数据
        opener_data = self.parse(opener_str)
        loop_data = self.parse(loop_str)

        def format_list(data_list):
            return "\n".join([f"    {json.dumps(item, ensure_ascii=False)}," for item in data_list])

        # 3. 动态生成 TEAM_CONFIG 字符串 (带有中文全名注释)
        team_config_lines = []
        for full_zh_name, data in self.team_mapping.items():
            cid, en_name, _ = data
            team_config_lines.append(f"    {cid}: \"{en_name}\", # {full_zh_name}")
        team_config_str = "\n".join(team_config_lines)

        content = f"""# ==========================================
# 🤖 自动生成的连招剧本 (支持多重别名版)
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
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"🎉 剧本生成成功！文件位置: {os.path.abspath(full_path)}")

if __name__ == '__main__':
    print("\n--- 开始解析带有【简称】的新轴 ---")

    # 🌟 核心升级：字典格式改为 -> "全名": (槽位, "英文/文件夹名", ["简称1", "简称2"])
    TEAM_DICT = {
        "爱弥斯": (1, "Aemeath", ["爱", "爱弥"]),
        "莫宁": (2, "Moning", ["莫"]),
        "琳奈": (3, "Lynae", ["琳"])
    }

    # 你可以混用简称和全名，甚至带括号，解析器都能认出来！
    raw_opener = "爱aaaa莫aaaz1r2a2a2a2e2z2q琳re爱aaaa琳z2a2a2a2a3q爱aafqreaaaaezraaaa（变奏莫宁）"
    raw_loop = "莫raaaezq琳re爱aaaa琳zaaaaq爱aafqreaaaaezraaaa"

    # 执行转换
    parser = GenericScriptParser(team_mapping=TEAM_DICT)
    parser.export_to_file(raw_opener, raw_loop, "team_ai_mo_lin.py")
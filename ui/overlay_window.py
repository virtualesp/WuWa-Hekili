from PySide6.QtWidgets import QMainWindow, QWidget, QMenu, QApplication
from PySide6.QtCore import Qt, QPoint, Signal, QPropertyAnimation, QParallelAnimationGroup, QEasingCurve, QRect
from PySide6.QtGui import QAction

from ui.widgets import ActionWidget
from utils.config_manager import config


class HekiliOverlay(QMainWindow):
    open_settings_signal = Signal()
    return_to_menu_signal = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("WuWa Hekili Overlay")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        old_x = config.get("settings.window_x", 100)
        old_y = config.get("settings.window_y", 100)
        self.setGeometry(old_x, old_y, 400, 150)
        self._drag_pos = QPoint()

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # 💡 核心动画参数定义：5个槽位的位置和透明度
        self.widgets = []
        self.anim_group = None
        self.exiting_widget = None

        # [位置-1] 历史动作 (最左侧，黑白/变小)
        self.POS_HIS = QRect(-20, 36, 48, 48)  # 放在最左边偏下的位置
        self.OP_HIS = 0.4  # 很暗
        # [位置0] 准备飞出的位置
        self.POS_OUT = QRect(10, 20, 80, 80)
        self.OP_OUT = 0.0
        # [位置1] 当前技能 (最大)
        self.POS_CUR = QRect(40, 20, 80, 80)  # 整体往右移一点，给历史留位置
        self.OP_CUR = 1.0
        # [位置2] 下一个技能
        self.POS_NXT = QRect(140, 28, 64, 64)
        self.OP_NXT = 0.8
        # [位置3] 未来技能
        self.POS_FUT = QRect(220, 36, 48, 48)
        self.OP_FUT = 0.6
        # [位置4] 备用进场位置
        self.POS_IN = QRect(290, 44, 32, 32)
        self.OP_IN = 0.0

    def update_ui(self, visual_data, is_advance=False, is_rollback=False):
        """
        :param is_rollback: 如果是回退，执行反向动画或直接刷新
        """
        while len(visual_data) < 4:
            visual_data.append({})

        # 如果有正在进行的动画，打断它
        if self.anim_group and self.anim_group.state() == QParallelAnimationGroup.State.Running:
            self.anim_group.stop()
            # ... 强制对齐逻辑 (包含历史槽位) ...

        if not is_advance or is_rollback:
            # 瞬间重排 (含历史槽位)
            for w in self.widgets: w.deleteLater()
            self.widgets.clear()

            # 渲染 4 个槽位 (0:历史, 1:当前, 2:下一个, 3:再下一个)
            for i, pos, op in [
                (0, self.POS_HIS, self.OP_HIS),
                (1, self.POS_CUR, self.OP_CUR),
                (2, self.POS_NXT, self.OP_NXT),
                (3, self.POS_FUT, self.OP_FUT)
            ]:
                w = ActionWidget(self.central_widget)
                w.set_data(visual_data[i])
                w.setGeometry(pos)
                w.graphicsEffect().setOpacity(op)
                w.update_style(visual_data[i].get("variant"), i == 1)
                w.show()
                self.widgets.append(w)
        else:
            # === 滑动动画 ===
            w_his = self.widgets[0]  # 原来的历史
            w_out = self.widgets[1]  # 原来的当前 -> 变成历史
            w_cur = self.widgets[2]  # 原来的下一个 -> 变成当前
            w_nxt = self.widgets[3]  # 原来的未来 -> 变成下一个

            w_fut = ActionWidget(self.central_widget)
            w_fut.set_data(visual_data[3])
            w_fut.setGeometry(self.POS_IN)
            w_fut.graphicsEffect().setOpacity(self.OP_IN)
            w_fut.show()

            self.exiting_widget = w_his  # 最老的历史飞出屏幕
            self.widgets = [w_out, w_cur, w_nxt, w_fut]

            # 重新设数据，防止变体状态不对
            w_out.set_data(visual_data[0])  # 更新历史格子
            w_cur.set_data(visual_data[1])
            w_nxt.set_data(visual_data[2])

            w_out.update_style(visual_data[0].get("variant"), False)
            w_cur.update_style(visual_data[1].get("variant"), True)

            self.anim_group = QParallelAnimationGroup(self)
            easing = QEasingCurve.Type.OutExpo
            duration = 250  # 稍微调快一点动画

            def add_anim(widget, end_geo, end_op):
                # 几何平移 + 尺寸缩放 动画
                anim_geo = QPropertyAnimation(widget, b"geometry")
                anim_geo.setDuration(duration)
                anim_geo.setEndValue(end_geo)
                anim_geo.setEasingCurve(easing)
                self.anim_group.addAnimation(anim_geo)

                # 透明度渐变动画
                anim_op = QPropertyAnimation(widget.graphicsEffect(), b"opacity")
                anim_op.setDuration(duration)
                anim_op.setEndValue(end_op)
                anim_op.setEasingCurve(easing)
                self.anim_group.addAnimation(anim_op)

            # 分配动画目标
            add_anim(w_his, QRect(-50, 36, 32, 32), 0.0)  # 历史飞走
            add_anim(w_out, self.POS_HIS, self.OP_HIS)  # 当前变历史
            add_anim(w_cur, self.POS_CUR, self.OP_CUR)  # 前进
            add_anim(w_nxt, self.POS_NXT, self.OP_NXT)  # 前进
            add_anim(w_fut, self.POS_FUT, self.OP_FUT)  # 进场

            self.anim_group.finished.connect(self._on_anim_finished)
            self.anim_group.start()

    def _on_anim_finished(self):
        """动画结束时的垃圾回收"""
        if self.exiting_widget:
            self.exiting_widget.deleteLater()
            self.exiting_widget = None

    # ... 右键菜单与鼠标拖拽逻辑保持不变 (复制你原来的即可) ...
    def show_context_menu(self, pos):
        menu = QMenu(self)

        settings_action = QAction("⚙️ 按键设置", self)
        settings_action.triggered.connect(lambda: self.open_settings_signal.emit())
        menu.addAction(settings_action)

        # ✨ 新增：返回主菜单按钮
        return_action = QAction("🔙 停止并返回主菜单", self)
        return_action.triggered.connect(lambda: self.return_to_menu_signal.emit())
        menu.addAction(return_action)

        menu.addSeparator()  # 加一条分割线

        exit_action = QAction("❌ 彻底退出程序", self)
        exit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(exit_action)

        menu.setStyleSheet("QMenu { background-color: white; border: 1px solid gray; }")
        menu.exec(self.mapToGlobal(pos))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            current_pos = self.pos()
            config.update_setting("settings.window_x", current_pos.x())
            config.update_setting("settings.window_y", current_pos.y())
            event.accept()
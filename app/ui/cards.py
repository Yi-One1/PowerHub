"""设备卡片：一块玻璃 + 电量控件 + 名称 + 状态。"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from ..core.model import Snapshot
from . import theme
from . import glass
from .gauge import BatteryGauge
from .glass import GlassSurface


class StatusLine(QWidget):
    """状态点 + 状态文字，颜色随状态变化。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._text = "未同步"
        self._color = theme.TEXT_TERTIARY
        self._text_color = theme.TEXT_SECONDARY
        self.setFixedHeight(16)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_text_color(self, color: str | QColor) -> None:
        """卡片底色变深时，状态文字要跟着加深，否则灰字糊在灰底上。"""
        value = color.name() if isinstance(color, QColor) else color
        if value == self._text_color:
            return
        self._text_color = value
        self.update()

    def set_status(self, text: str, color: str) -> None:
        if text == self._text and color == self._color:
            return
        self._text = text
        self._color = color
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        font = theme.font(10.5, 500)
        painter.setFont(font)
        fm = QFontMetrics(font)
        text_width = fm.horizontalAdvance(self._text)
        dot = 5.0
        total = dot + 5 + text_width
        left = (self.width() - total) / 2
        center_y = self.height() / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._color))
        painter.drawEllipse(QRectF(left, center_y - dot / 2, dot, dot))
        painter.setPen(QColor(self._text_color))
        painter.drawText(
            QRectF(left + dot + 5, 0, text_width + 2, self.height()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            self._text,
        )
        painter.end()


class DeviceCard(GlassSurface):
    def __init__(
        self,
        device_id: str,
        display_name: str,
        type_label: str,
        color: str,
        style: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(
            parent,
            radius=24,
            alpha=0.42,
            interactive=True,
            # 卡片叠在外壳上：只透出一点点桌面，否则会因为重复画背景而比周围更暗
            backdrop_weight=0.32,
        )
        self.device_id = device_id
        self.type_label = type_label
        self._color = color
        self.set_tint(color, 0.10)
        # 设备色太浅时，靠压深卡片底色来衬托它 —— 图形颜色一律不动
        self.set_contrast_foreground(color)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(152)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(4)

        self.gauge = BatteryGauge(style, color, self)
        layout.addWidget(self.gauge, 0, Qt.AlignmentFlag.AlignHCenter)

        self.name_label = QLabel(display_name, self)
        self.name_label.setFont(theme.font(12.5, 600))
        self.name_label.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; background: transparent;")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setFixedHeight(18)
        layout.addWidget(self.name_label)

        self.status = StatusLine(self)
        layout.addWidget(self.status)

        self._snapshot: Optional[Snapshot] = None
        self._text_tone: Optional[tuple[int, int, int]] = None

    def set_display_name(self, name: str) -> None:
        self.name_label.setText(name)

    # -- 更新 ---------------------------------------------------------------
    def apply_snapshot(self, snapshot: Snapshot, low_threshold: int) -> None:
        self._snapshot = snapshot
        display_level = snapshot.display_level
        display_charging = snapshot.display_charging
        alert = (
            snapshot.online
            and snapshot.level is not None
            and snapshot.level <= low_threshold
            and not snapshot.charging
        )
        self.gauge.set_state(display_level, display_charging, snapshot.online, alert)
        status = snapshot.status_text(low_threshold)
        if not snapshot.online:
            color = theme.TEXT_TERTIARY
        elif display_charging:
            color = theme.OK
        elif display_level is None:
            color = theme.TEXT_TERTIARY
        elif alert:
            color = theme.DANGER
        else:
            color = self._color
        self.status.set_status(status, color)

        level_text = "--" if display_level is None else f"{display_level}%"
        self.setToolTip(
            f"{self.name_label.text()}（{self.type_label}）\n"
            f"电量：{level_text} · {status}\n"
            f"数据源：{snapshot.source_label}\n"
            f"{snapshot.detail or '—'}"
        )

    def set_color(self, color: str) -> None:
        self._color = color
        self.set_tint(color, 0.10)
        self.set_contrast_foreground(color)
        self.gauge.set_color(color)
        self._text_tone = None

    def set_style(self, style: str) -> None:
        self.gauge.set_style(style)

    @property
    def color(self) -> str:
        """当前生效的强调色（测试与调试用）。"""
        return self._color

    # -- 文字随底色 ---------------------------------------------------------
    def face_after_shade(self) -> QColor:
        """卡片压深之后的实际底色（近似）。"""
        face = glass.face_color(
            shell_alpha=0.74,
            card_alpha=self.base_alpha,
            backdrop_weight=self.backdrop_weight,
        )
        shade = self.contrast_shade()
        keep = 1.0 - shade
        return QColor(int(face.red() * keep), int(face.green() * keep), int(face.blue() * keep))

    def sync_text_contrast(self) -> None:
        """按卡片实际底色校正名称与状态文字。

        压深底色是为了衬托设备色，但深卡片上的灰字会跟着糊掉 ——
        文字颜色也跟着底色走，保证两边都看得清。
        结果按底色缓存：底色（随壁纸、悬停态变化）不变就不重算，
        避免每帧都做一轮二分搜索。
        """
        face = self.face_after_shade()
        signature = (face.red(), face.green(), face.blue())
        if signature == self._text_tone:
            return
        self._text_tone = signature

        name_color = theme.ensure_contrast(theme.TEXT_PRIMARY, face, 4.5)
        self.name_label.setStyleSheet(f"color: {name_color.name()}; background: transparent;")
        self.status.set_text_color(theme.ensure_contrast(theme.TEXT_SECONDARY, face, 4.5))

    def paintEvent(self, event) -> None:  # noqa: N802
        self.sync_text_contrast()
        super().paintEvent(event)

    @property
    def style(self) -> str:
        return self.gauge.style

    def refresh_name(self, display_name: str, type_label: str) -> None:
        self.type_label = type_label
        self.name_label.setText(display_name)

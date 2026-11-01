"""电量显示控件：环形 / 条形 / 数字三种样式，颜色跟随外设类型。"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QConicalGradient, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from . import glass, theme

STYLE_HEIGHT = {"ring": 84, "bar": 44, "number": 58}
GAUGE_MIN_CONTRAST = 3.0
# 渐变亮端的提亮幅度上限；底色越亮，实际提亮越少（见 _bright_end）
GRADIENT_LIGHTEN = 0.42
# 环境阴影：设备色与底色对比不足时，在图形底下垫几层半透明深色，把轮廓"托"出来。
# 这是不改颜色、也不动卡片底色的前提下让浅色可见的唯一办法。
# 每项是 (比笔触额外加宽的像素, 黑色不透明度)：由外到内逐层加深，叠出柔边。
SHADOW_LAYERS = ((7.0, 11), (4.5, 16), (2.2, 22))
# 对比低于 3:1 才开始加阴影；低于 1:1 给满强度
SHADOW_START_CONTRAST = 3.0
SHADOW_FULL_CONTRAST = 1.0


def _bolt_path(center: QPointF, size: float) -> QPainterPath:
    path = QPainterPath()
    half = size / 2
    path.moveTo(center.x() + half * 0.18, center.y() - half)
    path.lineTo(center.x() - half * 0.55, center.y() + half * 0.12)
    path.lineTo(center.x() - half * 0.05, center.y() + half * 0.12)
    path.lineTo(center.x() - half * 0.22, center.y() + half)
    path.lineTo(center.x() + half * 0.58, center.y() - half * 0.14)
    path.lineTo(center.x() + half * 0.06, center.y() - half * 0.14)
    path.closeSubpath()
    return path


class BatteryGauge(QWidget):
    def __init__(
        self,
        style: str = "ring",
        color: str = theme.ACCENT_BLUE,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._style = style if style in STYLE_HEIGHT else "ring"
        self._color = color
        self._level: Optional[int] = None
        self._charging: Optional[bool] = None
        self._online = False
        self._alert = False
        height = STYLE_HEIGHT[self._style]
        self.setFixedHeight(height)
        if self._style == "ring":
            self.setFixedWidth(height)
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        else:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    # -- 状态 ---------------------------------------------------------------
    def set_state(self, level: Optional[int], charging: Optional[bool], online: bool, alert: bool = False) -> None:
        self._level = level
        self._charging = charging
        self._online = online
        self._alert = alert
        self.update()

    def set_color(self, color: str) -> None:
        self._color = color
        self.update()

    @property
    def style(self) -> str:
        return self._style

    @property
    def color(self) -> str:
        return self._color

    def set_style(self, style: str) -> None:
        if style not in STYLE_HEIGHT or style == self._style:
            return
        self._style = style
        height = STYLE_HEIGHT[style]
        self.setFixedHeight(height)
        if style == "ring":
            self.setFixedWidth(height)
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        else:
            self.setMinimumWidth(0)
            self.setMaximumWidth(16777215)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        if self._style == "ring":
            return QSize(84, 84)
        return QSize(150, STYLE_HEIGHT[self._style])

    # -- 绘制 ---------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # 卡片实际底色：设备色可能与它太接近（纯白卡片 + 纯白设备色），
        # 下面三种样式都用 ensure_contrast 兜一层，颜色原值不动、只是深浅按需调整
        face = glass.face_color()
        if self._style == "ring":
            self._paint_ring(painter, face)
        elif self._style == "bar":
            self._paint_bar(painter, face)
        else:
            self._paint_number(painter, face)
        painter.end()

    def _visible_color(self, face: QColor) -> QColor:
        """设备色原样返回。

        可见性由**卡片背景**负责（DeviceCard 会按需要把底色压深），
        图形本身一律用用户选的颜色，不做任何压暗/提亮。
        face 参数保留是为了调用点统一，后续若要做别的前景适配也方便。
        """
        return QColor(self._color)

    def _bright_end(self, base: QColor, face: QColor) -> QColor:
        """渐变亮端。

        底色越亮，越不能额外往白里提，否则亮端会与卡片底色糊在一起
        （实测纯白卡片上 lighten(0.42) 后对比只剩 1.82:1）。
        这里只是收敛"提亮幅度"，不改设备色本身。
        """
        room = 1.0 - theme.relative_luminance(face)
        ratio = GRADIENT_LIGHTEN * max(0.0, min(1.0, room))
        return theme.lighten(base.name(), ratio)

    def _shadow_strength(self, face: QColor) -> float:
        """需要多强的环境阴影（0 = 不用，1 = 满强度）。

        由设备色与底色的对比缺口决定：纯白几乎看不见 → 满强度，
        浅黄浅绿本来能看出形 → 只给轻档，够清楚的颜色 → 完全不加。
        """
        if self._charging_placeholder:
            return 0.0
        ratio = theme.contrast_ratio(self._color, face)
        if ratio >= SHADOW_START_CONTRAST:
            return 0.0
        span = max(1e-6, SHADOW_START_CONTRAST - SHADOW_FULL_CONTRAST)
        return max(0.0, min(1.0, (SHADOW_START_CONTRAST - ratio) / span))

    def _stroke_shadow(self, painter: QPainter, path: QPainterPath, strength: float) -> None:
        """沿 path 由外向内地描几层半透明黑，形成一圈柔和阴影。"""
        if strength <= 0.0:
            return
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for extra, alpha in SHADOW_LAYERS:
            pen = QPen(QColor(0, 0, 0, int(round(alpha * strength))), extra)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.strokePath(path, pen)

    def _arc_shadow(self, painter: QPainter, arc_rect: QRectF, thickness: float, ratio: float, strength: float) -> None:
        """环形的阴影：与环同一条弧，只是更粗、半透明。"""
        if strength <= 0.0:
            return
        for extra, alpha in SHADOW_LAYERS:
            pen = QPen(QColor(0, 0, 0, int(round(alpha * strength))), thickness + extra)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawArc(arc_rect, 90 * 16, int(-360 * 16 * ratio))

    @property
    def _dim(self) -> bool:
        return not self._online or (self._level is None and not self._charging)

    @property
    def _charging_placeholder(self) -> bool:
        """电量被隐藏但正在充电（例如迈从充电占位符 50%）。"""
        return self._charging and self._level is None

    def _paint_ring(self, painter: QPainter, face: QColor) -> None:
        rect = QRectF(self.rect()).adjusted(6, 6, -6, -6)
        thickness = 7.0
        arc_rect = rect.adjusted(thickness / 2, thickness / 2, -thickness / 2, -thickness / 2)
        ratio = 0.0 if self._level is None else max(0.0, min(1.0, self._level / 100.0))

        if self._charging_placeholder:
            # 充电占位符：整环绿色
            ratio = 1.0
            color = QColor(theme.OK)
        else:
            color = self._visible_color(face)

        if self._alert and not self._charging and ratio > 0 and not self._charging_placeholder:
            glow = QColor(theme.DANGER)
            glow.setAlphaF(0.16)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(rect.adjusted(2, 2, -2, -2))

        track = QColor(color if not self._dim else theme.TEXT_TERTIARY)
        track.setAlphaF(0.16 if not self._dim else 0.12)
        pen = QPen(track, thickness)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(arc_rect)

        if ratio > 0:
            # 浅色设备色在浅底上没有轮廓，先垫一圈柔和阴影把它托出来（颜色本身不动）
            self._arc_shadow(painter, arc_rect, thickness, ratio, self._shadow_strength(face))
            gradient = QConicalGradient(arc_rect.center(), 90)
            base = color
            gradient.setColorAt(0.0, base)
            gradient.setColorAt(0.55, self._bright_end(color, face))
            gradient.setColorAt(1.0, base)
            pen = QPen(QBrush(gradient), thickness)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawArc(arc_rect, 90 * 16, int(-360 * 16 * ratio))

        # 中心内容：电量被隐藏且充电时显示绿色闪电，否则显示数字
        if self._charging_placeholder:
            text = "\u26a1"
            font_num = theme.font(30, 600, theme.NUMBER_FAMILIES, -0.8)
        else:
            text = "--" if self._level is None else str(self._level)
            font_num = theme.font(25, 600, theme.NUMBER_FAMILIES, -0.8)
        font_pct = theme.font(11, 600)
        fm_num = QFontMetricsF(font_num)
        fm_pct = QFontMetricsF(font_pct)
        num_width = fm_num.horizontalAdvance(text)
        # 电量可读时一律带 % 符号（含充电中），与其它设备保持一致；
        # 充电占位符的 ⚡ 由上方分支处理，不会走到这里
        has_suffix = self._level is not None
        suffix_width = fm_pct.horizontalAdvance("%") + 1.5 if has_suffix else 0.0
        total = num_width + suffix_width
        left = rect.center().x() - total / 2
        baseline = rect.center().y() + (fm_num.ascent() - fm_num.descent()) / 2
        painter.setFont(font_num)
        painter.setPen(QColor(theme.TEXT_PRIMARY if not self._dim else theme.TEXT_TERTIARY))
        painter.drawText(QPointF(left, baseline), text)
        if has_suffix:
            painter.setFont(font_pct)
            painter.setPen(QColor(theme.TEXT_TERTIARY))
            painter.drawText(QPointF(left + num_width + 1.5, baseline), "%")

    def _paint_bar(self, painter: QPainter, face: QColor) -> None:
        rect = QRectF(self.rect())
        bar_height = 9.0
        bar = QRectF(rect.left(), rect.center().y() - bar_height / 2 + 5, rect.width(), bar_height)
        radius = bar_height / 2
        color = QColor(theme.OK) if self._charging_placeholder else self._visible_color(face)
        track = QColor(color if not self._dim else theme.TEXT_TERTIARY)
        track.setAlphaF(0.16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(bar, radius, radius)

        strength = self._shadow_strength(face)
        if strength > 0.0 and not self._charging_placeholder:
            fill_width = max(bar_height, bar.width() * (0.0 if self._level is None else max(0.0, min(1.0, self._level / 100.0))))
            shadow_path = QPainterPath()
            shadow_path.addRoundedRect(
                QRectF(bar.left(), bar.top(), fill_width, bar.height()), radius, radius
            )
            self._stroke_shadow(painter, shadow_path, strength)

        if self._charging_placeholder:
            fill = bar
        else:
            ratio = 0.0 if self._level is None else max(0.0, min(1.0, self._level / 100.0))
            fill = QRectF(bar.left(), bar.top(), max(bar_height, bar.width() * ratio), bar.height())
        if self._charging_placeholder or (self._level is not None and self._level > 0):
            gradient = QLinearGradient(fill.topLeft(), fill.topRight())
            gradient.setColorAt(0.0, color)
            gradient.setColorAt(1.0, self._bright_end(color, face))
            painter.setBrush(QBrush(gradient))
            painter.drawRoundedRect(fill, radius, radius)

        text = "\u26a1" if self._charging_placeholder else ("--" if self._level is None else str(self._level))
        painter.setFont(theme.font(17, 600, theme.NUMBER_FAMILIES, -0.4))
        painter.setPen(QColor(theme.TEXT_PRIMARY if not self._dim else theme.TEXT_TERTIARY))
        painter.drawText(
            QRectF(rect.left(), rect.top() - 4, rect.width(), 22),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            text + ("%" if self._level is not None and not self._charging_placeholder else ""),
        )

    def _paint_number(self, painter: QPainter, face: QColor) -> None:
        rect = QRectF(self.rect())
        color = QColor(theme.OK) if self._charging_placeholder else self._visible_color(face)
        if self._charging_placeholder:
            text = "\u26a1"
            font_num = theme.font(38, 600, theme.NUMBER_FAMILIES, -1.2)
        else:
            text = "--" if self._level is None else str(self._level)
            font_num = theme.font(34, 600, theme.NUMBER_FAMILIES, -1.2)
        painter.setFont(font_num)
        fm = QFontMetricsF(font_num)
        num_width = fm.horizontalAdvance(text)
        painter.setPen(QColor(theme.TEXT_PRIMARY if not self._dim else theme.TEXT_TERTIARY))
        painter.drawText(
            QRectF(rect.left(), rect.top() - 2, num_width + 4, rect.height() - 4),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            text,
        )
        if not self._charging_placeholder:
            painter.setFont(theme.font(12, 600))
            if self._level is not None:
                # 电量可读时统一带 %，充电状态交给下方状态行说明
                painter.setPen(QColor(theme.TEXT_TERTIARY))
                painter.drawText(
                    QRectF(rect.left() + num_width + 2, rect.center().y() + 2, 20, 16),
                    int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                    "%",
                )
            elif self._charging:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(theme.OK))
                painter.drawPath(_bolt_path(QPointF(rect.left() + num_width + 14, rect.center().y()), 11))

        ratio = 1.0 if self._charging_placeholder else (0.0 if self._level is None else max(0.0, min(1.0, self._level / 100.0)))
        underline = QRectF(rect.left(), rect.bottom() - 6, rect.width(), 3)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(60, 60, 67, 24))
        painter.drawRoundedRect(underline, 1.5, 1.5)
        if ratio > 0:
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(underline.left(), underline.top(), underline.width() * ratio, underline.height()), 1.5, 1.5)

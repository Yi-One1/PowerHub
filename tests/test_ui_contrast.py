"""对比度兜底：设备色与卡片底色太接近时要自动压暗/提亮。

用户能把设备颜色选到接近纯白，而卡片背景可能就是白的 —— 这时"忠实还原所选颜色"
和"看得见"冲突，一律以看得见为先，配置里存的原色不动。
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap

from app.ui import glass, theme

WHITE = QColor("#FFFFFF")


# --------------------------------------------------------------------------- #
# theme.ensure_contrast
# --------------------------------------------------------------------------- #
def test_contrast_ratio_matches_wcag_reference():
    """> 黑白对比是 21:1，同色是 1:1。"""
    assert theme.contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0, abs=0.1)
    assert theme.contrast_ratio("#FFFFFF", "#FFFFFF") == pytest.approx(1.0, abs=0.01)
    # 顺序无关
    assert theme.contrast_ratio("#FFFFFF", "#000000") == pytest.approx(21.0, abs=0.1)


def test_white_on_white_is_pushed_down_to_visible():
    out = theme.ensure_contrast("#FFFFFF", WHITE, 3.0)

    assert theme.contrast_ratio(out, WHITE) >= 3.0
    assert out.name() != "#ffffff", "纯白必须被压暗，否则等于没改"
    # 压到中灰即可，不必推到纯黑
    assert out.lightnessF() > 0.3


def test_visible_colors_are_left_alone():
    """本来就够清楚的颜色一个字都不许动，否则会误伤全站配色。"""
    for color in ("#0A84FF", "#1C1C1E", "#FF453A"):
        out = theme.ensure_contrast(color, WHITE, 3.0)
        assert out.name() == color.lower(), f"{color} 本来达标，却被改成了 {out.name()}"


def test_hue_is_preserved_when_adjusting():
    """压暗只动明度，色相不变 —— 浅黄仍要看起来是黄，不能变成灰。"""
    for source in ("#FFE066", "#C7F5D8"):
        out = theme.ensure_contrast(source, WHITE, 3.0)
        src_hue = QColor(source).hue()
        out_hue = out.hue()
        assert abs(src_hue - out_hue) <= 2, f"{source} 的色相从 {src_hue} 漂到了 {out_hue}"
        assert theme.contrast_ratio(out, WHITE) >= 3.0


def test_dark_background_pushes_color_brighter():
    dark = QColor("#1A1A1A")
    out = theme.ensure_contrast("#1C1C1E", dark, 3.0)

    assert theme.contrast_ratio(out, dark) >= 3.0
    assert out.lightnessF() > QColor("#1C1C1E").lightnessF(), "深底上应该往亮推，不是偷偷压暗"


def test_achromatic_color_survives_adjustment():
    """纯白/纯灰没有色相（hue = -1），这条路上不能崩。"""
    out = theme.ensure_contrast(QColor(255, 255, 255), WHITE, 3.0)
    assert theme.contrast_ratio(out, WHITE) >= 3.0


# --------------------------------------------------------------------------- #
# glass.face_color：卡片实际底色
# --------------------------------------------------------------------------- #
def test_face_color_is_white_without_backdrop(qapp):
    glass.clear_backdrop()
    assert glass.face_color().name() == "#ffffff"


def test_face_color_brightens_on_dark_backdrop(qapp):
    """深色壁纸下三层白纱叠起来仍应接近白 —— 这正是灰字还能读的前提。"""
    from app.ui.backdrop import BackdropPalette

    glass.set_backdrop(None, BackdropPalette(QColor("#101010"), 0.02, 0.0, False))
    try:
        face = glass.face_color()
        assert theme.relative_luminance(face) > 0.7, "深壁纸下卡片底色不该跟着变暗"
    finally:
        glass.clear_backdrop()


def test_face_color_follows_light_backdrop(qapp):
    from app.ui.backdrop import BackdropPalette

    glass.set_backdrop(None, BackdropPalette(QColor("#FAFAFA"), 0.95, 0.0, False))
    try:
        assert theme.relative_luminance(glass.face_color()) > 0.8
    finally:
        glass.clear_backdrop()


# --------------------------------------------------------------------------- #
# BatteryGauge：白色卡片上的白环必须看得见
# --------------------------------------------------------------------------- #
def _ring_band(image, radius_min: float = 28.0, radius_max: float = 37.0) -> list[QColor]:
    """取环形笔迹所在圆环带上的不透明像素（中心 42,42，半径 84）。"""
    size = image.width()
    center = size / 2
    band: list[QColor] = []
    for y in range(size):
        for x in range(size):
            distance = ((x - center) ** 2 + (y - center) ** 2) ** 0.5
            if radius_min <= distance <= radius_max:
                pixel = image.pixelColor(x, y)
                if pixel.alpha() > 160:
                    band.append(pixel)
    return band


def _render(gauge, width: int | None = None) -> "QPixmap":
    """把控件画到透明画布上。

    必须显式打开 WA_TranslucentBackground：否则 QWidget.render 会先用调色板
    把整块画布填成不透明灰（默认 239,239,239），统计像素时满屏都是"背景"，
    对比度全部失真。真实卡片里控件的背景由父级玻璃面板绘制，本来就是透明的。
    """
    gauge.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    size = gauge.sizeHint()
    gauge.resize(width or size.width(), size.height())
    pixmap = QPixmap(gauge.size())
    pixmap.fill(Qt.GlobalColor.transparent)
    gauge.render(pixmap)
    return pixmap


def _drop_contrast(image, band: list[QColor]) -> float:
    """环带上最"隐形"的那批像素与白底的对比（取 10% 分位，避开抗锯齿边缘）。"""
    ratios = sorted(theme.contrast_ratio(pixel, WHITE) for pixel in band)
    return ratios[int(len(ratios) * 0.10)]


@pytest.mark.parametrize("color", ["#FFFFFF", "#F5F5F7", "#FFE066", "#C7F5D8"])
def test_ring_is_visible_on_white_card(qapp, color):
    """白色卡片上，接近白的设备色也必须画出看得见的环。"""
    glass.clear_backdrop()
    from app.ui.gauge import BatteryGauge

    gauge = BatteryGauge("ring", color)
    gauge.set_state(72, False, True, False)
    image = _render(gauge).toImage()

    band = _ring_band(image)
    assert band, "环带上应当有像素"
    assert _drop_contrast(image, band) >= 2.2, f"{color} 的环在白卡片上太淡"


def test_ring_keeps_device_color_when_already_visible(qapp):
    """蓝色环本来就清楚，不能被对比度逻辑顺手压暗。"""
    glass.clear_backdrop()
    from app.ui.gauge import BatteryGauge

    gauge = BatteryGauge("ring", "#0A84FF")
    gauge.set_state(72, False, True, False)
    image = _render(gauge).toImage()

    band = _ring_band(image)
    # 蓝色笔迹的像素里蓝分量应明显高于红分量
    bluish = [p for p in band if p.blue() > p.red() + 60]
    assert len(bluish) > len(band) * 0.5, "蓝色环不该被改成灰调"


@pytest.mark.parametrize("color", ["#FFFFFF", "#F5F5F7", "#FFE066", "#C7F5D8"])
def test_bar_is_visible_on_white_card(qapp, color):
    """条形同理：白色卡片上不能出现"白底白条"。"""
    glass.clear_backdrop()
    from app.ui.gauge import BatteryGauge

    gauge = BatteryGauge("bar", color)
    gauge.set_state(72, False, True, False)
    image = _render(gauge, width=150).toImage()

    # 条形在竖直中部偏下：取填充段（左侧 60%）那一带的像素
    pixels: list[QColor] = []
    for y in range(image.height()):
        for x in range(int(image.width() * 0.15), int(image.width() * 0.55)):
            pixel = image.pixelColor(x, y)
            if pixel.alpha() > 160:
                pixels.append(pixel)
    assert pixels, "条形区域应当有像素"
    ratios = sorted(theme.contrast_ratio(pixel, WHITE) for pixel in pixels)
    assert ratios[int(len(ratios) * 0.10)] >= 2.2, f"{color} 的条在白卡片上太淡"

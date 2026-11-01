"""设备色太浅时的可见性方案。

取舍：设备色**一个像素都不改**，卡片底色也保持"白 + 设备色淡染"的原样，
只给环形/条形垫一圈按对比缺口自动调节的柔和阴影，把浅色轮廓托出来。
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
# 对比度量（阴影强度全靠它）
# --------------------------------------------------------------------------- #
def test_contrast_ratio_matches_wcag_reference():
    assert theme.contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0, abs=0.1)
    assert theme.contrast_ratio("#FFFFFF", "#FFFFFF") == pytest.approx(1.0, abs=0.01)
    assert theme.contrast_ratio("#FFFFFF", "#000000") == pytest.approx(21.0, abs=0.1)


def test_relative_luminance_orders_colors():
    assert theme.relative_luminance("#000000") < 0.01
    assert theme.relative_luminance("#FFFFFF") == pytest.approx(1.0, abs=0.01)
    assert theme.relative_luminance("#FFE066") > theme.relative_luminance("#0A84FF")


# --------------------------------------------------------------------------- #
# glass.face_color：卡片实际底色
# --------------------------------------------------------------------------- #
def test_face_color_is_white_without_backdrop(qapp):
    glass.clear_backdrop()
    assert glass.face_color().name() == "#ffffff"


def test_face_color_brightens_on_dark_backdrop(qapp):
    """深色壁纸下三层白纱叠起来仍接近白 —— 这是灰字还能读的前提。"""
    from app.ui.backdrop import BackdropPalette

    glass.set_backdrop(None, BackdropPalette(QColor("#101010"), 0.02, 0.0, False))
    try:
        assert theme.relative_luminance(glass.face_color()) > 0.7
    finally:
        glass.clear_backdrop()


# --------------------------------------------------------------------------- #
# 阴影强度：按对比缺口自动调节
# --------------------------------------------------------------------------- #
def _strength(color: str, style: str = "ring", background=WHITE) -> float:
    from app.ui.gauge import BatteryGauge

    gauge = BatteryGauge(style, color)
    gauge.set_state(72, False, True, False)
    return gauge._shadow_strength(background)


@pytest.mark.parametrize("color", ["#FFFFFF", "#F5F5F7", "#FFE066", "#C7F5D8"])
def test_light_colors_ask_for_shadow(color):
    """浅色设备色必须加阴影，否则白底白环。"""
    assert _strength(color) >= 0.5, f"{color} 应当需要明显阴影"


@pytest.mark.parametrize("color", ["#0A84FF", "#1C1C1E", "#FF453A"])
def test_visible_colors_get_no_shadow(color):
    """本来就清楚的颜色一点阴影都不加，保持原来的观感。"""
    assert _strength(color) == 0.0


def test_whiter_color_gets_stronger_shadow():
    """越接近白，缺口越大，阴影越重 —— 不能一刀切。"""
    assert _strength("#FFFFFF") > _strength("#FFE066")


def test_charging_placeholder_skips_shadow():
    """充电占位（绿色环）本来就醒目，不需要阴影。"""
    from app.ui.gauge import BatteryGauge

    gauge = BatteryGauge("ring", "#FFFFFF")
    gauge.set_state(None, True, True, False)
    assert gauge._shadow_strength(WHITE) == 0.0


# --------------------------------------------------------------------------- #
# 实际渲染：阴影真的画出来了
# --------------------------------------------------------------------------- #
def _render_gauge(color: str, style: str = "ring", width: int = 150):
    from app.ui.gauge import BatteryGauge

    gauge = BatteryGauge(style, color)
    gauge.set_state(72, False, True, False)
    gauge.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    hint = gauge.sizeHint()
    gauge.resize(width if style != "ring" else hint.width(), hint.height())
    pixmap = QPixmap(gauge.size())
    pixmap.fill(Qt.GlobalColor.transparent)
    gauge.render(pixmap)
    return pixmap.toImage()


def _gray_shadow_pixels(image, spread: int = 14) -> int:
    """统计"灰色、且比纯白暗"的像素。

    阴影是中性灰（色差很小），而设备色本身带明显色相 —— 用"通道差异小"
    就能把阴影和蓝色/绿色环本体区分开，避免把深色环误判成阴影。
    """
    count = 0
    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixelColor(x, y)
            if pixel.alpha() < 100:
                continue
            if max(pixel.red(), pixel.green(), pixel.blue()) - min(
                pixel.red(), pixel.green(), pixel.blue()
            ) > spread:
                continue
            if 0.62 <= theme.relative_luminance(pixel) <= 0.97:
                count += 1
    return count


def test_white_ring_gets_visible_outline(qapp):
    """纯白环在白底上：靠阴影画出轮廓，必须有相当数量的深色像素。"""
    glass.clear_backdrop()
    assert _gray_shadow_pixels(_render_gauge("#FFFFFF")) > 80, "白色环没有阴影，等于隐形"


def test_blue_ring_has_no_shadow_halo(qapp):
    """蓝色环本来清楚，不该被阴影糊出一圈脏边。"""
    glass.clear_backdrop()
    assert _gray_shadow_pixels(_render_gauge("#0A84FF")) == 0, "蓝色环被加了多余的灰色阴影"


def test_light_bar_gets_visible_outline(qapp):
    """条形同理。"""
    glass.clear_backdrop()
    assert _gray_shadow_pixels(_render_gauge("#FFFFFF", style="bar", width=150)) > 100, "白色条没有阴影"


def test_gauge_keeps_device_color_untouched(qapp):
    """图形颜色必须是用户选的原色，不能被任何逻辑改写。"""
    glass.clear_backdrop()
    from app.ui.gauge import BatteryGauge

    for color in ("#FFFFFF", "#FFE066", "#C7F5D8", "#0A84FF"):
        gauge = BatteryGauge("ring", color)
        gauge.set_state(72, False, True, False)
        assert gauge.color == color


# --------------------------------------------------------------------------- #
# 卡片淡染
# --------------------------------------------------------------------------- #
def test_card_tint_is_stronger_than_before(qapp):
    """卡片上的设备色淡染要比原来的 0.10 更明显，浅色设备色才留得下痕迹。"""
    from app.ui.cards import CARD_TINT_ALPHA, DeviceCard

    assert CARD_TINT_ALPHA >= 0.14, "淡染太淡，浅色设备色在卡片上看不出来"

    card = DeviceCard("d", "设备", "鼠标", "#FFE066", "ring")
    assert card.tint_alpha == pytest.approx(CARD_TINT_ALPHA)


def test_card_background_stays_light(qapp):
    """卡片底色必须保持"白 + 淡染"，绝不能为了对比把它压成灰。"""
    from app.core.model import Snapshot
    from app.ui.cards import DeviceCard

    glass.clear_backdrop()
    for color in ("#FFFFFF", "#FFE066", "#C7F5D8"):
        card = DeviceCard("d", "设备", "鼠标", color, "ring")
        card.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        card.setFixedSize(196, 152)
        card.apply_snapshot(Snapshot(device_id="d", level=72, charging=False, online=True), 20)
        card.show()
        qapp.processEvents()
        # 画到白底上：卡片本身是半透明玻璃，只看 alpha 反映不出真实观感
        pixmap = QPixmap(card.size())
        pixmap.fill(Qt.GlobalColor.white)
        card.render(pixmap)
        face = pixmap.toImage().pixelColor(170, 30)

        assert theme.relative_luminance(face) > 0.85, f"{color} 的卡片底色被压暗成了 {face.name()}"

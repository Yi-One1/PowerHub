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
# 策略：设备色一律不改，改的是卡片底衬
# --------------------------------------------------------------------------- #
def test_shade_zero_when_already_visible():
    """本来就够清楚的颜色，卡片一点都不要压深。"""
    for color in ("#0A84FF", "#1C1C1E", "#FF453A"):
        assert theme.shade_for_contrast(color, WHITE, 3.0) == 0.0


def test_shade_deepens_card_for_light_colors():
    """浅色设备色必须把卡片压深，否则白底白环。"""
    for color in ("#FFFFFF", "#F5F5F7", "#FFE066", "#C7F5D8"):
        shade = theme.shade_for_contrast(color, WHITE, 3.0)
        assert shade > 0.3, f"{color} 需要压深卡片，实际只给了 {shade:.2f}"

        keep = 1.0 - shade
        mixed = QColor(int(255 * keep), int(255 * keep), int(255 * keep))
        assert theme.contrast_ratio(color, mixed) >= 2.9


def test_shade_never_makes_things_worse():
    """压深后对比必须真的变好，不能出现"越压越糊"。"""
    bg = QColor("#FFFFFF")
    for color in ("#FFFFFF", "#FFE066", "#C7F5D8", "#0A84FF"):
        shade = theme.shade_for_contrast(color, bg, 3.0)
        if shade == 0.0:
            continue
        keep = 1.0 - shade
        mixed = QColor(int(255 * keep), int(255 * keep), int(255 * keep))
        assert theme.contrast_ratio(color, mixed) > theme.contrast_ratio(color, bg)


def test_gauge_keeps_device_color_untouched(qapp):
    """环形/条形的颜色必须是用户选的原色，一个像素都不压暗。"""
    glass.clear_backdrop()
    from app.ui.gauge import BatteryGauge

    for color in ("#FFFFFF", "#FFE066", "#C7F5D8", "#0A84FF"):
        gauge = BatteryGauge("ring", color)
        gauge.set_state(72, False, True, False)
        assert gauge._visible_color(QColor("#FFFFFF")).name() == color.lower()


def _render_card(qapp, color: str, style: str = "ring"):
    from app.core.model import Snapshot
    from app.ui.cards import DeviceCard

    card = DeviceCard("d-test", "测试设备", "鼠标", color, style)
    card.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    card.setFixedSize(196, 152)
    card.apply_snapshot(Snapshot(device_id="d-test", level=72, charging=False, online=True), 20)
    card.show()
    qapp.processEvents()
    pixmap = QPixmap(card.size())
    pixmap.fill(Qt.GlobalColor.transparent)
    card.render(pixmap)
    return card, pixmap.toImage()


@pytest.mark.parametrize("color", ["#FFFFFF", "#F5F5F7", "#FFE066", "#C7F5D8"])
def test_card_background_shades_for_light_device_color(qapp, color):
    """卡片底色确实被压深了，而设备色还是原样。"""
    glass.clear_backdrop()
    card, image = _render_card(qapp, color)

    assert card.color == color, "设备色不能被动过"
    # (170, 30) 落在环右侧的空白卡片区域，取到的就是卡片底色
    face = image.pixelColor(170, 30)
    assert face.alpha() > 200
    assert theme.contrast_ratio(color, face) >= 2.5, f"{color} 的卡片没压够深：底色 {face.name()}"


@pytest.mark.parametrize("color", ["#0A84FF", "#1C1C1E", "#FF453A"])
def test_card_background_light_for_visible_device_color(qapp, color):
    """正常颜色不该被无端压深，卡片要维持原来的浅色玻璃观感。"""
    glass.clear_backdrop()
    card, image = _render_card(qapp, color)

    assert card.contrast_shade() == 0.0
    face = image.pixelColor(170, 30)
    assert theme.relative_luminance(face) > 0.8, f"{color} 的卡片被误压深成 {face.name()}"


def test_shaded_card_text_keeps_contrast(qapp):
    """卡片压深后，卡上的状态文字不能跟着糊掉。"""
    glass.clear_backdrop()
    card, image = _render_card(qapp, "#FFFFFF")

    face = card.face_after_shade()
    # 设备名与状态文字都被校正过，取校正后的颜色与底色比
    name_color = theme.ensure_contrast(theme.TEXT_PRIMARY, face, 4.5)
    status_color = theme.ensure_contrast(theme.TEXT_SECONDARY, face, 4.5)
    assert theme.contrast_ratio(name_color, face) >= 4.4
    assert theme.contrast_ratio(status_color, face) >= 4.4


def test_glass_mode_shade_follows_backdrop(qapp):
    """玻璃模式下：壁纸再暗，卡片底色仍接近白，所以压深量必须照样算出来。"""
    from app.ui.backdrop import BackdropPalette

    glass.set_backdrop(
        QPixmap(64, 64),
        BackdropPalette(QColor("#101010"), 0.02, 0.0, False),
    )
    try:
        shade = theme.shade_for_contrast("#FFFFFF", glass.face_color(), 3.0)
        assert shade > 0.3, "深壁纸下白色设备色同样需要压深卡片"
    finally:
        glass.clear_backdrop()


def test_card_shade_reacts_to_backdrop_change(qapp):
    """换壁纸 / 切模式后压深量要重算，不能沿用上一次的结果。"""
    from app.ui.backdrop import BackdropPalette
    from app.ui.cards import DeviceCard

    glass.clear_backdrop()
    card = DeviceCard("d", "设备", "鼠标", "#FFFFFF", "ring")
    white_mode = card.contrast_shade()
    assert white_mode > 0.3

    glass.set_backdrop(QPixmap(64, 64), BackdropPalette(QColor("#101010"), 0.02, 0.0, False))
    try:
        glass_mode = card.contrast_shade()
    finally:
        glass.clear_backdrop()

    assert glass_mode > 0.3
    # 两种模式的卡片底色不同（#ffffff vs #f3f3f3），压深量必须跟着变
    assert glass_mode != white_mode, "压深量没有随底色重算"

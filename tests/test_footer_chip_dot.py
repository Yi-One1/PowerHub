"""页脚「全部已连接」胶囊：灰底 + 绿点（G4 任务 3）。

旧实现是 `theme.OK`（#2FC48A 浅绿）压在 `rgba(47,196,138,0.14)` 浅绿底上，
实测对比度 226 面 1.59、最暗角 1.29 —— 白底上也不合格，等于什么都看不见。

现在：文字回到共用的 `CHIP_TEXT`（#4A4A4F）深灰、底色回到共用灰，
「已连接」这层语义交给左侧一个 `CHIP_OK_DOT`（#12734A）的圆点：
图形元素按 WCAG 1.4.11 要 3:1，实测 226 面 4.08、202 面 3.30。
"""
from __future__ import annotations

import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from app.core.config import DeviceRegistry, SettingsStore
from app.core.model import Snapshot

pytestmark = pytest.mark.usefixtures("qapp")

# 取色容差（逐通道）：圆点是字号 10px 的实心「●」，抗锯齿会让边缘偏色，中心像素仍是纯色
COLOR_TOLERANCE = 6


# --------------------------------------------------------------------------- #
# 装置
# --------------------------------------------------------------------------- #
def build_panel(tmp_path):
    from app.core.monitor import Monitor
    from app.ui.panel import Panel
    from app.ui.tray import TrayController

    registry = DeviceRegistry(user_dir=tmp_path)
    store = SettingsStore(registry, path=tmp_path / "preferences.json")
    panel = Panel(registry, store, Monitor(registry, store.prefs), TrayController(registry, store))
    panel.show()
    QApplication.processEvents()
    return panel


@pytest.fixture()
def panel(qapp, tmp_path):
    widget = build_panel(tmp_path)
    yield widget
    widget.hide()
    widget.deleteLater()
    QApplication.processEvents()


def _snapshots(registry, *, all_read: bool) -> dict:
    now = time.time()
    result = {}
    for index, cfg in enumerate(registry.enabled_devices()):
        result[cfg.id] = Snapshot(
            device_id=cfg.id,
            level=55 if (all_read or index > 0) else None,
            online=True,
            last_seen=now,
            updated_at=now,
        )
    return result


def _render(widget) -> QImage:
    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    widget.render(image)
    return image


def _pixels_matching(image: QImage, hex_color: str, tolerance: int = COLOR_TOLERANCE) -> list[tuple[int, int]]:
    """找出渲染结果里接近指定颜色（逐通道 ±tolerance）的像素坐标。"""
    raw = hex_color.lstrip("#")
    target = (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))
    hits = []
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            actual = (color.red(), color.green(), color.blue())
            if all(abs(actual[i] - target[i]) <= tolerance for i in range(3)):
                hits.append((x, y))
    return hits


def _composite(fill: tuple[int, int, int], alpha: float, face: int) -> str:
    """半透明胶囊底叠在灰度面上的合成色（与 G2 那套口径一致）。"""
    channels = [int(round(channel * alpha + face * (1 - alpha))) for channel in fill]
    return "#%02X%02X%02X" % tuple(channels)


# --------------------------------------------------------------------------- #
# 1. 状态与样式
# --------------------------------------------------------------------------- #
def test_ok_state_uses_shared_gray_and_green_dot(panel):
    import app.ui.panel as panel_module
    from app.ui import theme

    panel._update_footer(_snapshots(panel.registry, all_read=True))
    QApplication.processEvents()

    style = panel.chip.styleSheet()
    assert panel_module.CHIP_TEXT in style, f"文字没回到共用深灰：{style}"
    assert "rgba(120,120,128," in style, f"底色没回到共用灰：{style}"
    assert theme.OK not in style, "不该再有浅绿字/浅绿底"
    assert "全部已连接" in panel.chip.text()

    image = _render(panel.chip)
    dot_pixels = _pixels_matching(image, panel_module.CHIP_OK_DOT)
    assert dot_pixels, f"胶囊里没有画出 {panel_module.CHIP_OK_DOT} 的圆点"
    text_pixels = _pixels_matching(image, panel_module.CHIP_TEXT)
    assert len(text_pixels) > 50, "文字没有用共用深灰渲染出来"
    # 圆点在文字左侧（语义顺序：点 → 文案）
    assert max(x for x, _ in dot_pixels) < min(x for x, _ in text_pixels)


def test_other_states_have_no_green_dot(panel):
    """只有「全部已连接」带绿点，其余状态不能凭空多出一个点。"""
    import app.ui.panel as panel_module

    panel._update_footer(_snapshots(panel.registry, all_read=False))
    QApplication.processEvents()
    assert "暂无电量" in panel.chip.text()
    assert not _pixels_matching(_render(panel.chip), panel_module.CHIP_OK_DOT)


def test_dot_does_not_grow_the_chip(panel):
    """加点不能让胶囊变高（10px 胶囊的高度由字号决定）。"""
    panel._update_footer(_snapshots(panel.registry, all_read=False))
    QApplication.processEvents()
    without_dot = (panel.chip.sizeHint().height(), panel.chip.height())

    panel._update_footer(_snapshots(panel.registry, all_read=True))
    QApplication.processEvents()
    with_dot = (panel.chip.sizeHint().height(), panel.chip.height())

    assert with_dot == without_dot, f"加了圆点以后胶囊高度变了：{without_dot} → {with_dot}"


# --------------------------------------------------------------------------- #
# 2. 对比度（点 3:1，文字 AA）
# --------------------------------------------------------------------------- #
def test_dot_and_text_meet_contrast_floors():
    import app.ui.panel as panel_module
    from app.ui import glass, theme

    fill = panel_module.CHIP_FILL
    alpha = panel_module.CHIP_FILL_ALPHA
    center = _composite(fill, alpha, glass.FACE_TARGET)
    darkest = _composite(fill, alpha, 202)

    dot_center = theme.contrast_ratio(panel_module.CHIP_OK_DOT, center)
    dot_darkest = theme.contrast_ratio(panel_module.CHIP_OK_DOT, darkest)
    assert dot_center >= 3.0, f"圆点在 226 面上只有 {dot_center:.2f}:1，不到图形元素要求的 3:1"
    assert dot_darkest >= 3.0, f"圆点在 202 面上只有 {dot_darkest:.2f}:1，不到 3:1"

    text_center = theme.contrast_ratio(panel_module.CHIP_TEXT, center)
    text_darkest = theme.contrast_ratio(panel_module.CHIP_TEXT, darkest)
    assert text_center >= 4.5, f"文案在 226 面上只有 {text_center:.2f}:1"
    assert text_darkest >= 4.3, f"文案在 202 面上只有 {text_darkest:.2f}:1"


def test_the_old_green_would_fail_the_dot_floor():
    """判别力自证：把点色改回 theme.OK，上面的 3:1 断言必红（顺带钉住"为什么换色"）。"""
    import app.ui.panel as panel_module
    from app.ui import glass, theme

    center = _composite(panel_module.CHIP_FILL, panel_module.CHIP_FILL_ALPHA, glass.FACE_TARGET)
    darkest = _composite(panel_module.CHIP_FILL, panel_module.CHIP_FILL_ALPHA, 202)
    assert theme.contrast_ratio(theme.OK, center) < 3.0
    assert theme.contrast_ratio(theme.OK, darkest) < 3.0
    # 也不能改回旧的浅绿底 + 浅绿字
    assert theme.contrast_ratio(theme.OK, "#C9DED6") < 4.5

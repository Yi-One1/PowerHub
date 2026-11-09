"""主面板定位：每次从托盘打开都回到主屏右下角（系统托盘区附近）。

用户口径：面板不记忆上次拖到的位置，**每次打开都拉回主屏右下角**；
主屏 = ``QGuiApplication.primaryScreen()``，不跟鼠标所在屏。

为什么不写死坐标：离屏虚拟屏的尺寸与「可用区域」取决于 Qt 版本与 DPI 缩放
（本机离屏是 800×800、无任务栏），期望值一律由 ``availableGeometry()`` 现算，
断言只比**相对边距**与**相对位置**，换机器/换分辨率不会误红。

⚠️ 边距口径：Qt 的 ``QRect.right()`` 是 ``left + width - 1``（最后一个像素列），
拿它当"右边界"去减窗口宽度会凭空多出 1px。所以这里一律用排他右边界
``area.left() + area.width()``，与应用里 ``PANEL_EDGE_MARGIN`` 的算法保持同一口径 ——
否则测试会因为 1px 的口径差而需要放宽容差，反而掩盖真问题。
"""
from __future__ import annotations

import inspect

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QGuiApplication

from app.core.config import DeviceRegistry, SettingsStore
from app.core.monitor import Monitor
from app.ui.panel import PANEL_EDGE_MARGIN, Panel
from app.ui.tray import TrayController


@pytest.fixture()
def panel(qapp, tmp_path):
    """一台离屏面板（不启动 Monitor 线程、不碰真实硬件）。"""
    registry = DeviceRegistry(user_dir=tmp_path)
    store = SettingsStore(registry, path=tmp_path / "preferences.json")
    monitor = Monitor(registry, store.prefs)
    tray = TrayController(registry, store)
    widget = Panel(registry, store, monitor, tray)
    # __init__ 里挂着 QTimer.singleShot(0, _place_initial)，先把这条排队消息放掉，
    # 免得测试中途它突然把窗口挪走（真实使用里它本来就只是首帧兜底）。
    qapp.processEvents()
    qapp.processEvents()
    try:
        yield widget
    finally:
        widget.hide()
        widget.deleteLater()


def screen_area():
    screen = QGuiApplication.primaryScreen()
    assert screen is not None, "离屏环境必须有一个主屏"
    return screen.availableGeometry()


def edge_margins(widget) -> tuple[int, int]:
    """窗口帧到「可用区域」右边界 / 下边界的间隙（px，排他边界口径）。"""
    area = screen_area()
    frame = widget.frameGeometry()
    right = (area.left() + area.width()) - (frame.left() + frame.width())
    bottom = (area.top() + area.height()) - (frame.top() + frame.height())
    return right, bottom


def assert_at_bottom_right(widget, tolerance: int = 2) -> None:
    right, bottom = edge_margins(widget)
    assert right == pytest.approx(PANEL_EDGE_MARGIN, abs=tolerance), (
        f"右边距 {right}px 不是 {PANEL_EDGE_MARGIN}±{tolerance}，面板没贴在右侧"
    )
    assert bottom == pytest.approx(PANEL_EDGE_MARGIN, abs=tolerance), (
        f"下边距 {bottom}px 不是 {PANEL_EDGE_MARGIN}±{tolerance}，面板没贴在下侧"
    )


# --------------------------------------------------------------------------- #
# 1. 每次打开都回右下角（不记忆上次的位置）
# --------------------------------------------------------------------------- #
def test_reopen_parks_at_bottom_right_again(panel, qapp):
    """打开 → 拖走 → 收起 → 再打开：必须回右下角，而不是回到拖走的位置。

    这里刻意两次都走 ``show_panel()``（真实入口是托盘点击）：如果第一次用
    ``show()`` 直接显示，``_first_show`` 不会被消费，旧实现也能"碰巧"通过 ——
    那样这条用例就没有判别力了（已做过对照实验）。
    """
    area = screen_area()
    panel.show_panel()
    qapp.processEvents()
    assert_at_bottom_right(panel)

    parked = QPoint(area.left() + 50, area.top() + 50)
    panel.move(parked)
    assert (panel.x(), panel.y()) == (parked.x(), parked.y()), "手动挪动没生效，后面的断言就没意义"
    panel.hide()
    assert panel.isVisible() is False

    panel.show_panel()
    qapp.processEvents()

    assert panel.isVisible() is True
    assert (panel.x(), panel.y()) != (parked.x(), parked.y()), "又回到上次的位置了，记忆位置的旧行为没去掉"
    assert_at_bottom_right(panel)


# --------------------------------------------------------------------------- #
# 2. 连续多次打开都成立（不是只在第一次生效）
# --------------------------------------------------------------------------- #
def test_bottom_right_holds_across_repeated_opens(panel, qapp):
    """移走 → 收起 → 打开，重复 3 次，每次都回右下角。"""
    area = screen_area()
    for round_index in range(3):
        panel.show_panel()
        qapp.processEvents()
        assert_at_bottom_right(panel)

        # 每轮挪到不同的地方，避免"恰好被夹回原位"的假通过
        offset = 40 + round_index * 30
        panel.move(area.left() + offset, area.top() + offset)
        panel.hide()
        assert panel.isVisible() is False


# --------------------------------------------------------------------------- #
# 3. 切到设置页变高后仍在屏内，且重心还在右下区
# --------------------------------------------------------------------------- #
def test_settings_page_stays_on_screen_and_near_bottom_right(panel, qapp):
    """设置页比电量页高：撑高之后四边都得在可用区域里，中心仍在右下四分屏。"""
    area = screen_area()
    panel.show_panel()
    qapp.processEvents()
    device_page_height = panel.height()

    panel._toggle_settings()
    qapp.processEvents()
    assert panel._settings_open is True
    assert panel.height() > device_page_height, "设置页没有比电量页高，这条用例就测不到'变高'"

    frame = panel.frameGeometry()
    assert frame.left() >= area.left() - 1, f"左边越界：{frame.left()} < {area.left()}"
    assert frame.top() >= area.top() - 1, f"上边越界：{frame.top()} < {area.top()}"
    assert frame.left() + frame.width() <= area.left() + area.width() + 1, "右边越界"
    assert frame.top() + frame.height() <= area.top() + area.height() + 1, "下边越界"

    # 变高是往上长的（下边距保持不变），所以中心必须落在屏幕右下半区
    assert frame.center().x() > area.left() + area.width() / 2, "横向重心跑到左半屏去了"
    assert frame.center().y() > area.top() + area.height() / 2, "纵向重心跑到上半屏去了"
    _, bottom = edge_margins(panel)
    assert bottom == pytest.approx(PANEL_EDGE_MARGIN, abs=2), f"撑高后下边距变成 {bottom}px"


# --------------------------------------------------------------------------- #
# 4. 底图取样必须发生在 show() 之前（否则截到的是自己）
# --------------------------------------------------------------------------- #
def test_backdrop_is_sampled_before_the_window_is_shown(panel, monkeypatch):
    """顺序守卫：_refresh_backdrop() 先于 show()。

    顺序反了会截到"面板自己"：玻璃底图发白、并且每轮取样都把上一次的亮色糊进去
    （越刷越白）。这条用例直接记调用序列，不依赖任何视觉阈值。
    """
    calls: list[str] = []
    original_backdrop = panel._refresh_backdrop
    original_show = panel.show

    def spy_backdrop() -> None:
        calls.append("backdrop")
        original_backdrop()

    def spy_show() -> None:
        calls.append("show")
        original_show()

    monkeypatch.setattr(panel, "_refresh_backdrop", spy_backdrop)
    monkeypatch.setattr(panel, "show", spy_show)

    panel.show_panel()
    panel._refresh_backdrop()  # 保证两种回调都至少出现一次，断言才有判别力

    assert "backdrop" in calls and "show" in calls, f"没有采到两个动作：{calls}"
    assert calls[0] == "backdrop", f"首次动作不是取样：{calls}"
    assert calls.index("show") > 0, f"show() 出现在取样之前：{calls}"


# --------------------------------------------------------------------------- #
# 5. 边距常量只有一个来源
# --------------------------------------------------------------------------- #
def test_edge_margin_has_a_single_source(panel, qapp):
    """``_place_initial`` 与 ``_keep_in_screen`` 都只能用 ``PANEL_EDGE_MARGIN``。

    源码级断言（不许再出现 ``- 8`` / ``- 10`` 这类字面量）+ 行为级断言（实测边距 == 常量）。
    另外守住**排他边界口径**：``area.right()`` 是 ``left + width - 1``，用它减窗口宽度
    会让右/下边距变成 ``PANEL_EDGE_MARGIN + 1``；±2px 的行为容差放过这 1px（QA 实验③
    把它换回错误口径后 8 条全绿），所以这条 1px 只能靠源码断言守。
    """
    for name in ("_place_initial", "_keep_in_screen"):
        source = inspect.getsource(getattr(Panel, name))
        assert "PANEL_EDGE_MARGIN" in source, f"{name} 没有引用边距常量"
        assert "- 8" not in source and "- 10" not in source, f"{name} 里还留着写死的边距字面量"
        assert "area.right()" not in source and "area.bottom()" not in source, (
            f"{name} 用了 QRect.right()/bottom() 这种「最后一个像素列」口径，"
            "实测留白会比 PANEL_EDGE_MARGIN 多 1px"
        )

    # 行为一致：定位后再兜底夹取一次，位置不能被改动（两处口径若不同就会挪 1~2px）
    panel.show_panel()
    qapp.processEvents()
    placed = (panel.x(), panel.y())
    panel._keep_in_screen()
    assert (panel.x(), panel.y()) == placed, "定位与夹取用的边距不一致，夹取把窗口又挪了一点"

    right, bottom = edge_margins(panel)
    assert right == pytest.approx(PANEL_EDGE_MARGIN, abs=1), f"右边距 {right}px 与常量不一致"
    assert bottom == pytest.approx(PANEL_EDGE_MARGIN, abs=1), f"下边距 {bottom}px 与常量不一致"


# --------------------------------------------------------------------------- #
# 6. _first_show 的生命周期（变量保留，语义是"show_panel 跑过没有"）
# --------------------------------------------------------------------------- #
def test_first_show_flag_tracks_first_open_only(panel, qapp):
    """``_first_show`` 初次 True → 首次 show_panel() 后 False → 之后再开仍是 False。

    它现在**不再**决定要不要定位（定位由 ``isVisible()`` 决定），只表示
    "show_panel() 跑过没有"、供 ``_toggle_settings`` / ``_on_devices_changed``
    里的兜底判断使用；这条用例守住"变量没被删、也没被反复置回 True"。
    """
    assert panel._first_show is True, "构造之后应该是 True"
    panel.show_panel()
    qapp.processEvents()
    assert panel._first_show is False, "首次打开之后应该变 False"

    panel.hide()
    panel.show_panel()
    qapp.processEvents()
    assert panel._first_show is False, "_first_show 不该被第二次打开重置"


# --------------------------------------------------------------------------- #
# 7. 窗口比可用区域还大：右/下边仍留在屏内（宁可左/上出屏）
# --------------------------------------------------------------------------- #
def test_oversized_window_keeps_bottom_right_visible(panel, qapp):
    """极端分辨率下窗口放不进可用区域时，托盘那一角（右下）必须还在屏内。"""
    area = screen_area()
    panel.setFixedSize(area.width() + 120, area.height() + 120)
    panel._place_initial()

    frame = panel.frameGeometry()
    assert frame.left() + frame.width() <= area.left() + area.width() + 1, "右边界跑出屏幕了"
    assert frame.top() + frame.height() <= area.top() + area.height() + 1, "下边界跑出屏幕了"
    right, bottom = edge_margins(panel)
    assert right == pytest.approx(PANEL_EDGE_MARGIN, abs=1)
    assert bottom == pytest.approx(PANEL_EDGE_MARGIN, abs=1)


# --------------------------------------------------------------------------- #
# 8. 上次停在设置页时再打开：仍回右下角（设置页更高，容易留下"半空"的 y）
# --------------------------------------------------------------------------- #
def test_reopen_from_settings_page_lands_at_bottom_right(panel, qapp):
    """收起时停在设置页 → 再打开回到电量页，下边距必须还是常量。

    这是一条回归守卫：如果"切回电量页"排在定位之后，y 会按设置页的高度算出来并留在
    屏幕上 —— 窗口变矮后下边距就变成 200+px，看起来悬在半空（实测离线环境如此）。
    """
    area = screen_area()
    panel.show_panel()
    qapp.processEvents()
    panel._toggle_settings()  # 用户点进了设置页
    qapp.processEvents()
    assert panel._settings_open is True

    panel.hide()  # 直接按 Esc / 收起，停在设置页
    panel.show_panel()
    qapp.processEvents()

    assert panel._settings_open is False, "打开时应回到电量显示页"
    assert panel.stack.currentWidget() is panel._page
    assert_at_bottom_right(panel)
    assert panel.frameGeometry().bottom() <= area.top() + area.height() + 1


# --------------------------------------------------------------------------- #
# 9. 面板**已经开着**时再 show_panel()：不许位移
# --------------------------------------------------------------------------- #
def test_visible_panel_is_not_repositioned(panel, qapp):
    """面板可见时再次调用 show_panel()，位置必须一点不动（位移量 0）。

    真实入口有三个：托盘右键菜单点设备行（tray.py:509）、菜单里的「立即刷新」、
    第二次启动 exe 唤醒单实例。用户此时已经把面板拖到顺手的位置，
    把它拽回右下角（实测会跳 574px）纯属打扰 —— 用户要的是"每次**打开**都回右下角"。
    """
    area = screen_area()
    panel.show_panel()
    qapp.processEvents()
    assert_at_bottom_right(panel)

    parked = QPoint(area.left() + 40, area.top() + 70)
    panel.move(parked)
    qapp.processEvents()
    assert panel.isVisible() is True
    before = panel.pos()

    panel.show_panel()
    qapp.processEvents()

    assert panel.isVisible() is True
    assert panel.pos() == before, f"面板开着时被拽走了：{before} → {panel.pos()}"
    assert (panel.pos() - before).manhattanLength() == 0, "可见状态下 show_panel() 不该产生任何位移"
    assert (panel.x(), panel.y()) == (parked.x(), parked.y())


# --------------------------------------------------------------------------- #
# 10. 齿轮 → 返回：下边缘锁住，不许"漂"上去
# --------------------------------------------------------------------------- #
def test_settings_round_trip_keeps_bottom_margin(panel, qapp):
    """贴底打开 → 进设置页（变高）→ 返回（变矮）：下边距始终贴着常量。

    回归守卫：``_toggle_settings()`` 里如果只调 ``_keep_in_screen()``（只夹取不回收），
    从高页退回矮页时高度缩了、y 却没跟着还回去，下边距会变成 222px，面板悬在半空。
    连做 3 轮还顺带守住"每切一次页往上漂 1px"（用 ``frameGeometry().bottom()`` 就会这样）。
    """
    area = screen_area()
    panel.show_panel()
    qapp.processEvents()
    assert_at_bottom_right(panel)

    for round_index in range(3):
        panel._toggle_settings()
        qapp.processEvents()
        assert panel._settings_open is True
        assert_at_bottom_right(panel)

        panel._toggle_settings()
        qapp.processEvents()
        assert panel._settings_open is False
        assert_at_bottom_right(panel)

    frame = panel.frameGeometry()
    assert frame.left() >= area.left() - 1
    assert frame.top() >= area.top() - 1
    assert frame.left() + frame.width() <= area.left() + area.width() + 1
    assert frame.top() + frame.height() <= area.top() + area.height() + 1
    _, bottom = edge_margins(panel)
    assert bottom == pytest.approx(PANEL_EDGE_MARGIN, abs=1), (
        f"3 轮齿轮往返后下边距变成 {bottom}px（每切一次页漂 1px 的典型症状）"
    )

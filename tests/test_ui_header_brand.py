"""主页面头部品牌化测试（G2）。

用户诉求：主页面左上角显示软件中文名「电量中枢」+ 英文名「PowerHub」+ 版本号（灰色胶囊），
一行并列、共用一条底边，右侧三个圆钮位置不变。

这里守的是四件事：
1. 三个标签的文案**全部取自 app/core/paths.py 的常量**，代码里不许出现写死的应用名/版本号；
2. 切到设置页时英文名与版本胶囊不消失、不挪位（头部恒定是「<页面标题> PowerHub v<主>.<次>.<修>」）；
3. 品牌块在 420px 固定宽度下不与右侧按钮、副标题相撞，也不被截断；
4. 视觉排版：胶囊底边与中文墨迹底边齐平，西文/胶囊文字的墨迹底边比中文略高
   （BRAND_EN_NUDGE / BRAND_CHIP_RISE 的光学微调结果）。

关于第 4 条的口径：**只断言「墨迹」相对关系，不写死绝对像素行**。
控件矩形在 AlignBottom 下底边恒等（断言它等于什么也没守住），所以这里把三个标签
用 `widget.render()` 画到透明图上，按 alpha 取真实墨迹行范围再比 —— 字号变了、
补偿被清零、标签被别的容器包一层，这些都会让断言失效，而矩形底边不会。
绝对像素行（如「中文墨迹 y=18..35」）随 alpha 阈值会有 ±1px 漂移，因此不写进断言。

环境依赖（本模块按「要不要真字形」分成两类）：
* **依赖 Windows 字体文件**（`C:/Windows/Fonts` 下的 Segoe UI / 雅黑）的只有 3 条墨迹用例：
  `test_chip_bottom_edge_is_flush_with_chinese_ink`、
  `test_latin_and_chip_text_sit_slightly_above_chinese_ink`、
  `test_zeroing_the_nudges_shifts_the_small_text_down_by_exactly_that_much`。
  它们显式请求 `real_fonts` 夹具；缺字体时只跳过这 3 条（SKIP 原因写明「需要真实字体」）。
* **与环境无关**的其余 17 条（文案、版式、截断、设置页切换、AA 对比度算术、源码守卫、
  页脚四态同源）不挂该夹具，任何机器上都照常执行 —— 这些是 G2 的验收点，
  绝不能因为一台机器缺字体就整模块静默 SKIP（那曾是被绿色掩盖的覆盖缺口）。
"""
from __future__ import annotations

from itertools import combinations
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QFontDatabase, QImage
from PySide6.QtWidgets import QApplication

from app.core.config import DeviceRegistry, SettingsStore
from app.core.paths import APP_DISPLAY_NAME, APP_EN_NAME, APP_VERSION

# 旧版本里写死过「电量中心」，这里留一份用于回归：不允许它再出现在主页面头部
LEGACY_TITLE = "电量中心"

# 离屏沙箱里字体库可能是空的，文字会退化成方块 —— 那样墨迹测量全是假的。
# 必须先把 Windows 自带字体注册进来；跑完摘掉，免得影响后面的像素计数类测试。
_FONT_FILES = (
    Path("C:/Windows/Fonts/segoeui.ttf"),
    Path("C:/Windows/Fonts/segoeuib.ttf"),
    Path("C:/Windows/Fonts/msyh.ttc"),
)


@pytest.fixture(scope="module", name="real_fonts")
def real_fonts(qapp):
    """注册真实字体（只给需要量墨迹的用例显式请求）。

    刻意**不加 autouse**：registration 是进程级的，而 skip 是模块级的 ——
    一旦 autouse，缺字体时整个模块 20 条会一起跳过，连纯算术的 AA 对比度用例
    和纯文本的源码守卫都跑不到，报告却仍是绿的（覆盖面被静默吞掉）。
    """
    available = [path for path in _FONT_FILES if path.exists()]
    if not available:
        pytest.skip("需要真实字体：系统缺少 Segoe UI / 微软雅黑（字形墨迹测量不可信）")
    loaded: list[int] = []
    for path in available:
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            for known in loaded:
                QFontDatabase.removeApplicationFont(known)
            pytest.skip(f"需要真实字体：{path} 加载失败")
        loaded.append(font_id)
    yield
    for font_id in loaded:
        QFontDatabase.removeApplicationFont(font_id)


# --------------------------------------------------------------------------- #
# 装置
# --------------------------------------------------------------------------- #
@pytest.fixture()
def env(qapp, tmp_path):
    registry = DeviceRegistry(user_dir=tmp_path)
    store = SettingsStore(registry, path=tmp_path / "preferences.json")
    return registry, store


def build_panel(registry, store):
    """造一个已显示、布局已生效的面板（只用于量几何，不碰真实硬件）。"""
    from app.core.monitor import Monitor
    from app.ui.panel import Panel
    from app.ui.tray import TrayController

    monitor = Monitor(registry, store.prefs)
    tray = TrayController(registry, store)
    widget = Panel(registry, store, monitor, tray)
    widget.show()
    QApplication.processEvents()
    return widget


@pytest.fixture()
def panel(qapp, env):
    registry, store = env
    widget = build_panel(registry, store)
    yield widget
    widget.hide()
    widget.deleteLater()
    QApplication.processEvents()


def header_of(panel):
    """品牌行所在的头部控件（标题的父控件）。"""
    header = panel.title.parentWidget()
    assert header is not None
    return header


def box(widget, header) -> QRect:
    """把控件几何换算到 header 坐标系（标签可能被容器包着，不能直接读 geometry）。"""
    return QRect(widget.mapTo(header, QPoint(0, 0)), widget.size())


BRAND_LABELS = ("title", "brand_en", "version_chip")
BUTTONS = ("refresh_btn", "gear_btn", "close_btn")

# 墨迹行的阈值：胶囊底色是 rgba(120,120,128,0.10)（alpha≈26），文字是不透明深灰，
# 所以取 alpha>60 就能把「胶囊里的文字」从「胶囊本体」里剥出来；
# 反过来取 alpha>8 时只有胶囊本体（≈26）过线，阈值离它还有约 18 级余量。
PILL_ALPHA = 8
TEXT_ALPHA = 60


def boxes(panel) -> dict[str, QRect]:
    header = header_of(panel)
    result = {name: box(getattr(panel, name), header) for name in BRAND_LABELS + BUTTONS}
    result["subtitle"] = box(panel.subtitle, header)
    return result


def ink_rows(panel, widget, alpha_threshold: int = PILL_ALPHA) -> tuple[int, int]:
    """把控件离屏渲染到透明图上，按 alpha 取**墨迹**的行范围（header 坐标系）。

    返回 (top, bottom)，bottom 为开区间（末行 + 1）。比读 geometry 强的地方在于：
    字号、内边距、QSS margin、行盒怎么算都不影响结论，只认真正画出来的像素。
    """
    header = header_of(panel)
    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    widget.render(image)

    top = bottom = None
    for y in range(image.height()):
        row_has_ink = any(
            image.pixelColor(x, y).alpha() > alpha_threshold for x in range(image.width())
        )
        if row_has_ink:
            top = y if top is None else top
            bottom = y + 1
    assert top is not None, "控件没有画出任何墨迹，无法判断排版"
    offset = widget.mapTo(header, QPoint(0, 0)).y()
    return offset + top, offset + bottom


def chip_text_rows(panel) -> tuple[int, int]:
    """版本胶囊里**文字**的墨迹行（剥掉半透明胶囊底色）。"""
    return ink_rows(panel, panel.version_chip, alpha_threshold=TEXT_ALPHA)


# --------------------------------------------------------------------------- #
# 1~3. 文案来自常量
# --------------------------------------------------------------------------- #
def test_title_shows_chinese_app_name(panel):
    assert panel.title.text() == APP_DISPLAY_NAME
    assert panel.title.text() == "电量中枢"


def test_title_is_not_legacy_typo(panel):
    assert LEGACY_TITLE not in panel.title.text(), "「电量中心」是历史错字，主页面不应再出现"


def test_english_name_is_shown_next_to_title(panel):
    assert panel.brand_en.text() == APP_EN_NAME
    assert panel.brand_en.text() == "PowerHub"


def test_version_chip_matches_version_constant(panel):
    assert panel.version_chip.text() == f"v{APP_VERSION}"


def test_version_chip_reads_constant_at_build_time(qapp, env, monkeypatch):
    """替换模块级 APP_VERSION 后重建面板，标签必须跟着变 —— 证明没写死 "v1.8.4"。"""
    import app.ui.panel as panel_module

    registry, store = env
    monkeypatch.setattr(panel_module, "APP_VERSION", "9.9.9")
    assert panel_module.version_text() == "v9.9.9"

    widget = build_panel(registry, store)
    try:
        assert widget.version_chip.text() == "v9.9.9"
    finally:
        widget.hide()
        widget.deleteLater()
        QApplication.processEvents()


# --------------------------------------------------------------------------- #
# 4. 设置页切换
# --------------------------------------------------------------------------- #
def test_toggle_settings_keeps_english_name_and_version(panel):
    home_boxes = boxes(panel)

    panel._toggle_settings()
    QApplication.processEvents()

    assert panel.title.text() == "设置", "设置页顶部仍显示页面标题"
    assert panel.brand_en.text() == APP_EN_NAME
    assert panel.version_chip.text() == f"v{APP_VERSION}"
    assert not panel.brand_en.isHidden(), "英文名在设置页不能消失"
    assert not panel.version_chip.isHidden(), "版本胶囊在设置页不能消失"
    assert panel.brand_en.isVisible() and panel.version_chip.isVisible()

    settings_boxes = boxes(panel)
    # 位置不变 = 相对页标题的排布关系不变（间距仍是 6px，仍在标题右侧）
    gap = settings_boxes["brand_en"].left() - settings_boxes["title"].right()
    assert gap == home_boxes["brand_en"].left() - home_boxes["title"].right()
    assert settings_boxes["brand_en"].top() == home_boxes["brand_en"].top()
    assert settings_boxes["brand_en"].height() == home_boxes["brand_en"].height()
    assert settings_boxes["version_chip"].top() == home_boxes["version_chip"].top()
    assert settings_boxes["version_chip"].height() == home_boxes["version_chip"].height()

    panel._toggle_settings()
    QApplication.processEvents()
    assert panel.title.text() == APP_DISPLAY_NAME


# --------------------------------------------------------------------------- #
# 5. 版式：不重叠 / 顺次排列 / 留够右侧按钮的位置
# --------------------------------------------------------------------------- #
def test_brand_row_does_not_overlap_anything(panel):
    cells = boxes(panel)
    names = list(cells)
    overlaps = [
        (a, b)
        for a, b in combinations(names, 2)
        if cells[a].intersects(cells[b])
    ]
    assert not overlaps, f"头部元素互相重叠：{overlaps} -> {[(a, cells[a], b, cells[b]) for a, b in overlaps]}"


def test_brand_row_is_left_to_right_and_pushed_left(panel):
    cells = boxes(panel)
    assert cells["brand_en"].left() > cells["title"].right(), "英文名应在中文名右侧"
    assert cells["version_chip"].left() > cells["brand_en"].right(), "版本胶囊应在英文名右侧"
    # 整体靠左：品牌块右边界离刷新按钮还远着呢（实测 119px，这里只挡住"挤在一起"）
    assert cells["refresh_btn"].left() - cells["version_chip"].right() >= 24


def test_subtitle_stays_clear_of_action_buttons(panel):
    cells = boxes(panel)
    assert cells["subtitle"].right() < cells["refresh_btn"].left(), "副标题不能被品牌行挤到按钮下面"


# --------------------------------------------------------------------------- #
# 6. 不截断
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", BRAND_LABELS)
def test_brand_label_is_not_truncated(panel, name):
    label = getattr(panel, name)
    assert label.sizeHint().width() <= label.width(), f"{name} 宽度不足，文字会被截断"
    assert label.sizeHint().height() <= label.height()
    assert label.minimumSizeHint().width() <= label.width()


def test_brand_labels_fit_inside_header(panel):
    header = header_of(panel)
    cells = boxes(panel)
    for name in BRAND_LABELS:
        assert cells[name].left() >= 0
        assert cells[name].right() < header.width(), f"{name} 越出 header 右边界"
        assert cells[name].top() >= 0
        assert cells[name].bottom() < header.height(), f"{name} 越出 header 下边界"


# --------------------------------------------------------------------------- #
# 7. 底边对齐 / 光学微调（按墨迹量，不看控件矩形）
# --------------------------------------------------------------------------- #
def test_chip_bottom_edge_is_flush_with_chinese_ink(panel, real_fonts):
    """用户要的「共用一条底边」落在**胶囊底边 vs 中文墨迹底边**上（实测 1px）。

    容差 1（原为 2）：现测偏移恰好 1px，容差 2 等于没有余量约束。
    注意这条**抓不到** `BRAND_CHIP_RISE` 归零 —— QSS margin 在控件矩形内部，
    归零时胶囊可视底边不移动（动的是胶囊里的文字与上沿）。归零由下面两条把住：
    `test_latin_and_chip_text_sit_slightly_above_chinese_ink` 与
    `test_zeroing_the_nudges_shifts_the_small_text_down_by_exactly_that_much`。
    """
    _, title_bottom = ink_rows(panel, panel.title)
    _, chip_bottom = ink_rows(panel, panel.version_chip)   # 含胶囊底色 = 胶囊本体

    delta = chip_bottom - title_bottom
    assert abs(delta) <= 1, f"胶囊底边与中文墨迹底边错开 {delta:+d}px，不再是一条底边"


def test_latin_and_chip_text_sit_slightly_above_chinese_ink(panel, real_fonts):
    """BRAND_EN_NUDGE / BRAND_CHIP_RISE 的**结果**：两行小字的墨迹底边比中文略高。

    区间是光学校准值（16px 离屏实测：西文 +3px、胶囊文字 +5px）。清零补偿会掉到
    +1px / +3px，被下面的 A/B 用例与这里一起拦住；抬得更高则小字悬空。
    """
    _, title_bottom = ink_rows(panel, panel.title)
    _, en_bottom = ink_rows(panel, panel.brand_en)
    _, chip_text_bottom = chip_text_rows(panel)

    latin_lift = title_bottom - en_bottom
    chip_lift = title_bottom - chip_text_bottom
    assert 2 <= latin_lift <= 4, f"西文墨迹底边只比中文高 {latin_lift}px，不在光学微调区间"
    assert 4 <= chip_lift <= 6, f"胶囊文字墨迹底边比中文高 {chip_lift}px，不在光学微调区间"


def test_compensation_constants_are_wired_into_the_widgets(panel):
    """两个常量确实被用进了内边距 / 胶囊样式，而不是写了没接。"""
    import app.ui.panel as panel_module

    assert panel.brand_en.contentsMargins().bottom() == panel_module.BRAND_EN_NUDGE
    assert f"margin: 0 0 {panel_module.BRAND_CHIP_RISE}px 0" in panel.version_chip.styleSheet()


def test_zeroing_the_nudges_shifts_the_small_text_down_by_exactly_that_much(qapp, env, monkeypatch, real_fonts):
    """A/B 对照：把两个常量清零重建面板，西文/胶囊文字必须整体下移常数量。

    这条既守住「补偿真的作用在排版上」，也钉住**方向**：补偿是把小字**抬高**，
    不是防止它掉到中文基线以下（清零时西文墨迹底边只比中文低 1px，几乎齐平）。
    """
    import app.ui.panel as panel_module

    registry, store = env
    nudge = panel_module.BRAND_EN_NUDGE
    rise = panel_module.BRAND_CHIP_RISE
    assert nudge >= 1 and rise >= 1, "补偿常量被清零：西文/胶囊文字会下坠，视觉上就歪了"

    shipped = build_panel(registry, store)
    try:
        shipped_en = ink_rows(shipped, shipped.brand_en)[1]
        shipped_chip = chip_text_rows(shipped)[1]
    finally:
        shipped.hide()
        shipped.deleteLater()
        QApplication.processEvents()

    monkeypatch.setattr(panel_module, "BRAND_EN_NUDGE", 0)
    monkeypatch.setattr(panel_module, "BRAND_CHIP_RISE", 0)
    zeroed = build_panel(registry, store)
    try:
        zeroed_en = ink_rows(zeroed, zeroed.brand_en)[1]
        zeroed_chip = chip_text_rows(zeroed)[1]
    finally:
        zeroed.hide()
        zeroed.deleteLater()
        QApplication.processEvents()

    assert zeroed_en - shipped_en == nudge, "西文补偿没生效（清零后应正好下移 nudge px）"
    assert zeroed_chip - shipped_chip == rise, "胶囊文字的补偿没生效（清零后应正好下移 rise px）"


# --------------------------------------------------------------------------- #
# 8. 胶囊的可读性：字 vs 底的对比度（头部版本胶囊 + 页脚状态胶囊共用一套配色）
# --------------------------------------------------------------------------- #
def _composite(fill: tuple[int, int, int], alpha: float, face: int) -> str:
    """把半透明胶囊底色叠在一档灰度面上，返回合成色的十六进制值。

    合成公式（逐通道）：合成 = 胶囊底色 × alpha + 面灰度 × (1 - alpha)，四舍五入取整。
    面灰度取 0~255 的单一灰度值 —— 玻璃面是中性白纱，三个通道本就相同。
    """
    channels = [int(round(channel * alpha + face * (1 - alpha))) for channel in fill]
    return "#%02X%02X%02X" % tuple(channels)


def test_chips_meet_aa_contrast(panel):
    """两颗胶囊的文字在最不利的两档玻璃面上都要过 AA。

    基准面取值来源：
      · 中心面 = ``glass.FACE_TARGET``（226）：白纱"刚好把玻璃面压到这个亮度"的目标灰度；
      · 最暗角 = 202：玻璃最暗处 211 级再乘 0.9 的取样衰减。它比
        ``FACE_TARGET - EDGE_FALLOFF_LEVELS``（= 214）更暗，所以按更保守的 202 算。
    底线：中心面 4.5（WCAG AA 正文），最暗角 4.3（本仓库对"边缘灰字"自定的底线）。

    覆盖范围：头部版本胶囊与页脚状态胶囊**同一个配色**，用两个样式函数各算一次 ——
    只要有人把其中一处改回 `TEXT_SECONDARY`，这条就会红。
    同时把当前色值的实测数钉住（`EXPECTED`），这样"悄悄改 alpha/字色"也会被发现。
    """
    import app.ui.panel as panel_module
    from app.ui import glass, theme

    fill = panel_module.CHIP_FILL
    alpha = panel_module.CHIP_FILL_ALPHA
    color = panel_module.CHIP_TEXT

    center = _composite(fill, alpha, glass.FACE_TARGET)
    darkest = _composite(fill, alpha, 202)
    on_white = _composite(fill, alpha, 255)
    center_ratio = theme.contrast_ratio(color, center)
    darkest_ratio = theme.contrast_ratio(color, darkest)

    # 两条样式函数产出的都是同一套色（页脚那颗与头部那颗必须长一样）
    for name, style in (
        ("页脚状态胶囊", panel_module.chip_style()),
        ("头部版本胶囊", panel_module.version_chip_style()),
    ):
        assert color in style, f"{name} 字色不是 {color}：{style}"
        assert f"rgba({fill[0]},{fill[1]},{fill[2]},{alpha:g})" in style, f"{name} 底色不是共用灰：{style}"
        assert center_ratio >= 4.5, f"{name} 在中心面 {center} 上只有 {center_ratio:.2f}:1，不到 AA 4.5"
        assert darkest_ratio >= 4.3, f"{name} 在最暗角 {darkest} 上只有 {darkest_ratio:.2f}:1，不到 4.3"

    # 控件实际挂上的样式也必须是同一套（防止只改了函数没接上控件）
    for name, widget in (("页脚状态胶囊", panel.chip), ("头部版本胶囊", panel.version_chip)):
        assert color in widget.styleSheet(), f"{name} 用的是别的字色：{widget.styleSheet()}"

    # 当前定案的实测值：#4A4A4F on rgba(120,120,128,0.10) 的四档
    expected = {255: 7.87, glass.FACE_TARGET: 6.13, 214: 5.54, 202: 4.95}
    for face, ratio in expected.items():
        actual = theme.contrast_ratio(color, _composite(fill, alpha, face))
        assert actual == pytest.approx(ratio, abs=0.02), f"{face} 面上的对比度实测 {actual:.2f}，与注释里的 {ratio} 不符"
    assert alpha == pytest.approx(0.10), "胶囊底色透明度被改动过，请重算四档对比度并同步注释"

    # 反证：原来的 TEXT_SECONDARY 在 202 面上连"底色全透明"都过不了 4.3（上限 4.06），
    # 所以这次只能加深字色 —— 谁把字色改回 TEXT_SECONDARY，上面的断言会立刻红。
    assert theme.contrast_ratio(theme.TEXT_SECONDARY, _composite(fill, 0.0, 202)) < 4.3
    assert theme.contrast_ratio(theme.TEXT_SECONDARY, center) < center_ratio
    # 也别把字色压到比主标题还黑：层级上它只是"胶囊里的小字"
    assert theme.relative_luminance(color) > theme.relative_luminance(theme.TEXT_PRIMARY)
    assert theme.contrast_ratio(color, on_white) >= 4.5


def _code_only_module_source(module) -> str:
    """模块源码剥掉注释后的**代码**部分（token 直接拼接，便于做"相邻写法"匹配）。

    注释里写 `rgba(120,120,128,0.10)` 是文档（告诉后人我们用的就是这个值），不算硬编码；
    把注释剔除之后，"用常量拼出来的底色"与"又抄了一遍字面量"才区分得开。
    """
    import inspect
    import io
    import tokenize

    source = inspect.getsource(module)
    pieces = [
        token.string
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type != tokenize.COMMENT
    ]
    return "".join(pieces)


def test_no_hardcoded_chip_colors_left_in_panel():
    """结构守卫：`panel.py` 的代码里不许再写死胶囊灰底，5 个调用点必须同源。

    对比度问题当年就是因为同一串 QSS 在 5 处各写了一遍，改一处漏四处；这条盯住"别再抄一遍"：
    灰底只能由 ``_chip_background()`` 用 ``CHIP_FILL`` / ``CHIP_FILL_ALPHA`` 拼出来，
    页脚 4 个状态 + 头部版本胶囊都必须经过样式函数。
    """
    import app.ui.panel as panel_module

    code = _code_only_module_source(panel_module)
    assert "rgba(120,120,128" not in code, "代码里还有写死的胶囊底色，请走 _chip_background()"
    assert "CHIP_FILL_ALPHA" in code, "灰底不是由常量拼出来的"
    assert code.count("self.chip.setStyleSheet(chip_style(") == 4, "页脚 4 个状态必须都走 chip_style()"
    assert "self.version_chip.setStyleSheet(version_chip_style())" in code, "头部版本胶囊没走共用样式函数"


def test_footer_chip_states_all_share_one_style_helper(panel):
    """页脚 4 种状态（初始 / 演示数据 / 暂无电量 / 全部已连接）都必须走 chip_style()。

    只查"颜色对不对"不够：还得把它们真的跑一遍，确认没有哪一处偷偷 setStyleSheet 了别的形状。
    """
    import app.ui.panel as panel_module
    from app.core.model import Snapshot

    import time  # 局部导入：这个文件其余用例不需要时间

    assert panel_module.CHIP_TEXT in panel.chip.styleSheet(), "初始状态的胶囊没走共用配色"

    now = time.time()
    devices = [cfg.id for cfg in panel.registry.enabled_devices()]
    assert devices, "内置设备清单不该是空的"

    # 有设备读不到电量 → 灰色「N 台暂无电量」
    partial = {
        device_id: Snapshot(
            device_id=device_id,
            level=None if index == 0 else 55,
            online=True,
            last_seen=now,
            updated_at=now,
        )
        for index, device_id in enumerate(devices)
    }
    panel._update_footer(partial)
    assert panel_module.CHIP_TEXT in panel.chip.styleSheet()
    assert "border-radius: 9px" in panel.chip.styleSheet(), "形状参数必须来自 chip_style()"

    # 全部读到 → 「全部已连接」：G4 起改成灰底 + 绿点（点色见 panel.CHIP_OK_DOT），
    # 于是这一态的文字色也回到了共用深灰，形状仍来自同一个函数
    full = {
        device_id: Snapshot(device_id=device_id, level=55, online=True, last_seen=now, updated_at=now)
        for device_id in devices
    }
    panel._update_footer(full)
    from app.ui import theme

    assert panel_module.CHIP_TEXT in panel.chip.styleSheet(), "「全部已连接」应回到共用深灰（G4）"
    assert theme.OK not in panel.chip.styleSheet(), "不该再有浅绿字/浅绿底（G4 已换成灰底绿点）"
    assert "border-radius: 9px" in panel.chip.styleSheet()

    # 演示数据（面板里那颗琥珀标记仍然保留，只删了设置页的开关）：琥珀色 + 同样的形状
    panel.store.prefs.demo = True
    try:
        panel._update_footer(full)
        assert theme.WARN_TEXT in panel.chip.styleSheet()
        assert "border-radius: 9px" in panel.chip.styleSheet()
    finally:
        panel.store.prefs.demo = False

"""托盘数字居中：按字形**墨迹外框**对齐徽标中心（竖直 + 水平）。

为什么需要这组测试：
旧实现是 `drawText(badge_rect, AlignCenter)`，Qt 按 `ascent + descent` 的整块行高居中。
阿拉伯数字没有下伸部（descender），基线以下那段空白把字形整体往下压了约 0.06em
（16px 画布实测偏低 1px、32px 偏低 1.5px、64px 偏低 2.5px）；水平方向则按 advance
宽度居中，左右 side bearing 不对称还会带偏零点几像素。肉眼看上去就是「偏下一点、略偏左」。

这里不做截图对比，而是**按前景色覆盖率把字形像素抠出来**，量它的包围盒中心，
再和徽标几何中心 `(8*scale, 8*scale)` 比。像素测量是唯一的 ground truth：
它不关心实现用的是哪种对齐方式，只认「画出来到底站在哪儿」。

⚠️ 字体陷阱：pytest 离屏沙箱里字体库可能是空的，文字会退化成「豆腐块」，
像素测量完全不可信（方块既不是数字，宽高比也不对）。所以：
  1. 先 `QFontDatabase.addApplicationFont()` 把 Windows 自带字体注册进来，
     字体文件不存在时直接 skip；
  2. 再断言墨迹「明显宽于高」—— 真数字才长这样，方块是接近正方形的。
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFontDatabase, QImage, QPainter, QPainterPath, QPixmap

from app.ui import theme
from app.ui.tray import BADGE_INSET, foreground_on

# Segoe UI 是应用真正的首选字体（theme.TEXT_FAMILIES）；
# 雅黑作为二级回退，保证极端环境里至少还有一套中文字体可选。
_FONT_FILES = (
    Path("C:/Windows/Fonts/segoeui.ttf"),
    Path("C:/Windows/Fonts/segoeuib.ttf"),
    Path("C:/Windows/Fonts/msyh.ttc"),
)

# 徽标中心在画布上的归一化位置（16px 画布下 = 8.0）
BADGE_CENTER = 8.0


@pytest.fixture(scope="module")
def real_fonts(qapp):
    """把系统字体注册进离屏 Qt，否则数字会被渲染成方块，像素测量没有意义。

    注册是**进程级**的，跑完必须摘掉：后面的测试模块（对比度、仪表盘）里
    有不少按像素计数定的阈值，字体一换口径就变了，属于不该被本文件影响的邻居。

    刻意**不加 autouse**：skip 是模块级、注册是进程级，一旦 autouse，缺字体时
    整个模块 29 条会一起静默 SKIP —— 连纯几何的 `_badge_rect` 护栏和只比绘制
    起点的用例都跑不到，报告却仍然是绿的（覆盖面被吞掉）。所以只让真正量字形
    墨迹的那 24 条显式请求本夹具。
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
    if "Segoe UI" not in QFontDatabase.families():
        pytest.skip("需要真实字体：注册后字体库里仍没有 Segoe UI")
    yield
    for font_id in loaded:
        QFontDatabase.removeApplicationFont(font_id)


@pytest.fixture(scope="module", autouse=True)
def _qt_app(qapp):
    """所有用例都必须有 QApplication。

    刻意 autouse：`QPixmap` / `QPainter` 在没有 QApplication 时**不是抛异常，
    而是直接 abort 整个进程**（实测退出码 0xC0000409，stdout 一个字都没有）。
    那比一条红更糟 —— 报告只剩半截，很容易被误判成并行抢 basetemp。
    所以这里把 qapp 兜住，不依赖任何用例自己记得请求。
    """
    return qapp


def _center_tolerance(size: int) -> float:
    """中心偏差允许值（像素）。

    构成：±0.5px 是像素栅格本身的量化台阶（包围盒边界只能落在整数上），
    再加每 16px 画布 0.25px 的抗锯齿/字体细微信号差。16px 画布下即 0.75px，
    而旧实现 16px 偏低 1.0px、32px 偏低 1.5px —— 够把它挡在门外。
    """
    return 0.5 + 0.25 * (size / 16.0)


def _ink_bbox(image: QImage, background: QColor, foreground: QColor, threshold: float = 0.35):
    """按前景色覆盖率抠出墨迹包围盒，返回像素**边界**坐标 (left, top, right, bottom)。

    徽标底色是纯色、前景色是纯色，抗锯齿像素就是两者的线性混合 —— 于是把像素颜色
    投影到 bg→fg 这条线上，投影系数就是覆盖率（0=纯底色，1=纯前景）。
    比「亮度阈值」稳，浅底深字（深字压在浅底上）同样适用。

    右下角 +1 用像素边界而不是像素中心，避免整体多出 0.5px 的系统性偏差。
    """
    background_rgb = (background.red(), background.green(), background.blue())
    foreground_rgb = (foreground.red(), foreground.green(), foreground.blue())
    span = tuple(hi - lo for hi, lo in zip(foreground_rgb, background_rgb))
    denominator = sum(value * value for value in span) or 1.0

    left = top = 10 ** 9
    right = bottom = -1
    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixelColor(x, y)
            if pixel.alpha() < 200:
                continue
            offset = (pixel.red() - background_rgb[0],
                      pixel.green() - background_rgb[1],
                      pixel.blue() - background_rgb[2])
            projection = sum(a * b for a, b in zip(offset, span)) / denominator
            if projection < threshold:
                continue
            left, right = min(left, x), max(right, x)
            top, bottom = min(top, y), max(bottom, y)
    if right < 0:
        return None
    return left, top, right + 1, bottom + 1


def _render(level: int, color: str, size: int, charging: bool = False) -> QImage:
    """端到端：走真实的 `battery_icon()`，再取指定尺寸那张位图。"""
    from app.ui.tray import battery_icon

    return battery_icon(level, color, charging, True, False).pixmap(size, size).toImage()


def _render_single(level: int, color: str, size: int, charging: bool = False) -> QImage:
    """只画**一枚**指定尺寸的图标。

    `battery_icon()` 会一口气把 ICON_SIZES 全部画一遍，抓 drawText 时对不上号，
    所以验证绘制起点这类逐次比对用这个单尺寸入口。
    """
    from app.ui.tray import _draw_icon

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    _draw_icon(painter, size, level, color, charging, True, False)
    painter.end()
    return pixmap.toImage()


def _measure(level: int, color: str, size: int, charging: bool = False):
    """测量一枚图标里数字墨迹的包围盒与中心偏差。"""
    base = QColor(color)
    image = _render(level, color, size, charging)
    box = _ink_bbox(image, base, foreground_on(base))
    assert box is not None, f"{size}px / {level} 下没测到任何墨迹"
    left, top, right, bottom = box
    scale = size / 16.0
    offset_x = (left + right) / 2 - BADGE_CENTER * scale
    offset_y = (top + bottom) / 2 - BADGE_CENTER * scale
    return offset_x, offset_y, right - left, bottom - top


def _assert_centered(level: int, color: str, size: int, min_aspect: float = 1.3) -> None:
    offset_x, offset_y, width, height = _measure(level, color, size)
    tolerance = _center_tolerance(size)

    # 先证「量到的是真数字」：数字的墨迹明显宽于高；字体回退成方块时两者接近，
    # 那种情况下任何居中结论都不成立。
    assert width >= height * min_aspect, (
        f"{size}px / {level} 的墨迹 {width}×{height} 不像数字（宽应明显大于高），"
        "字体可能回退成了方块，像素测量不可信"
    )
    # 水平与竖直都要各自成立：分开断言，失败时一眼看出是哪一轴偏了
    assert abs(offset_x) <= tolerance, f"{size}px / {level} 横向偏移 {offset_x:+.2f}px（允许 ±{tolerance:.2f}）"
    assert abs(offset_y) <= tolerance, f"{size}px / {level} 纵向偏移 {offset_y:+.2f}px（允许 ±{tolerance:.2f}）"


# --------------------------------------------------------------------------- #
# 像素级验收：各尺寸 × 两位数/三位数 × 深底白字/浅底深字
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("size", (16, 18, 20, 24, 32, 40, 48, 64))
@pytest.mark.usefixtures("real_fonts")
def test_two_digit_number_is_centered_on_every_icon_size(size):
    """两位数（PERCENT_FONT）在全部图标尺寸下两端居中。"""
    _assert_centered(88, "#0A84FF", size)


@pytest.mark.parametrize("size", (16, 18, 20, 24, 32, 40, 48, 64))
@pytest.mark.usefixtures("real_fonts")
def test_three_digit_number_is_centered_on_every_icon_size(size):
    """三位数 100（PERCENT_FONT_COMPACT，字更小更扁）在全部尺寸下同样居中。"""
    _assert_centered(100, "#0A84FF", size)


# 前景色切换的两条分支都要覆盖：前三个是浅底深字，后两个是深底白字。
# 参数化与「分支覆盖」断言共用这一份清单，避免改一处忘另一处。
FOREGROUND_SAMPLES = ("#F2E3A0", "#FFE066", "#FFFFFF", "#2FC48A", "#FF453A")


@pytest.mark.parametrize("color", FOREGROUND_SAMPLES)
@pytest.mark.usefixtures("real_fonts")
def test_digits_are_centered_for_both_foreground_colors(color):
    """前景色自动切换不该影响几何：浅底深字与深底白字都要居中。

    #F2E3A0 / #FFE066 / #FFFFFF 走深字分支，#2FC48A / #FF453A 走白字分支 ——
    下面顺带确认这条色值本身有效、且整份清单覆盖两条分支，否则「深字也居中」就是空话。
    """
    from app.ui.tray import FG_DARK, FG_LIGHT

    foregrounds = {foreground_on(QColor(value)).name() for value in FOREGROUND_SAMPLES}
    assert foregrounds == {FG_DARK.name(), FG_LIGHT.name()}, "这组设备色没有同时覆盖深字/白字两条分支"

    for size in (16, 24, 32):
        _assert_centered(88, color, size)


@pytest.mark.usefixtures("real_fonts")
def test_centering_does_not_depend_on_the_digits():
    """不同数字（1 窄、8 宽、100 最宽）的墨迹中心都落在同一处。

    墨迹居中的意义就在这里：'11' 的墨迹比 '88' 窄一半，按墨迹对齐才会看起来一样居中。
    '11' 的墨迹接近方形（宽高比约 1.2），不能用宽高比筛字体回退，
    真数字的守卫交给上面的 88 / 100 用例。
    """
    _assert_centered(11, "#0A84FF", 32, min_aspect=1.1)
    _assert_centered(48, "#0A84FF", 32)
    _assert_centered(88, "#0A84FF", 32)
    _assert_centered(100, "#0A84FF", 32)


def test_charging_does_not_move_the_digits(monkeypatch):
    """充电只加右下角绿点角标，数字的字号与位置都不变（旧版会把数字缩小上移）。"""
    original = QPainter.drawText
    captured: list = []

    def spy(painter, *args):
        if len(args) == 2 and isinstance(args[1], str):
            captured.append((QPointF(args[0]), painter.font().pixelSize(), args[1]))
        elif len(args) == 3 and isinstance(args[2], str):
            captured.append(("rect", painter.font().pixelSize(), args[2]))
        return original(painter, *args)

    monkeypatch.setattr(QPainter, "drawText", spy)
    _render_single(88, "#0A84FF", 32, charging=False)
    idle = captured[-1]
    _render_single(88, "#0A84FF", 32, charging=True)
    charging = captured[-1]

    assert idle[0] != "rect" and charging[0] != "rect", "数字必须用基线起点（墨迹居中），不能用矩形对齐"
    assert charging[1] == idle[1], "充电时数字字号不该变"
    assert charging[0] == idle[0], f"充电时数字位置不该动：{idle[0]} → {charging[0]}"


@pytest.mark.usefixtures("real_fonts")
def test_digits_still_fill_the_badge_width():
    """数字墨迹占徽标宽度约八成：够满（不是缩在中间的小字），也不溢出圆角块。

    这条守的是「居中」之外的另一个视觉约束 —— 光居中但字太小同样难看。
    实测 16/32/64px 均为 77%~80%。
    """
    for size in (16, 32, 64):
        _, _, width, _ = _measure(88, "#0A84FF", size)
        badge_width = (16 - 2 * BADGE_INSET) * (size / 16.0)
        ratio = width / badge_width
        assert 0.6 <= ratio <= 0.95, f"{size}px 下数字墨迹占徽标宽 {ratio:.0%}，不是『撑满且不溢出』"


# --------------------------------------------------------------------------- #
# 几何自洽：绘制起点必须让「墨迹外框中心」正好落在徽标中心
#
# 像素测量受栅格量化限制，精度只到半像素；这里再用字形轮廓精确复核一次绘制起点。
# 轮廓路径由测试自己算（不复用 app 里的 _ink_box），因此能抓住「算错中心/用错重载」。
# --------------------------------------------------------------------------- #
def _outline_center(font, text: str) -> QPointF:
    path = QPainterPath()
    path.addText(QPointF(0.0, 0.0), font, text)
    box = path.boundingRect()
    # 实测：空串 / 空格 / 全角空格 / 零宽空格均返回 0×0；真·无字形环境同理。
    # 这种时候「轮廓中心」没有意义（实现会走 _ink_box 的兜底分支），
    # 继续比下去只会得到一条假红，所以降级成诚实的 SKIP。
    if box.width() <= 0.01 or box.height() <= 0.01:
        pytest.skip("需要真实字体：无可用字形，轮廓自洽性检查不成立")
    return box.center()


@pytest.mark.parametrize("size", (16, 32, 64))
def test_draw_origin_puts_outline_center_on_badge_center(monkeypatch, size):
    from app.ui.tray import _badge_rect

    original = QPainter.drawText
    captured: list = []

    def spy(painter, *args):
        if len(args) == 2 and isinstance(args[1], str):
            captured.append((QPointF(args[0]), painter.font(), args[1]))
        return original(painter, *args)

    monkeypatch.setattr(QPainter, "drawText", spy)
    _render_single(88, "#0A84FF", size)

    assert len(captured) == 1, f"数字只该画一次，实际画了 {len(captured)} 次"
    origin, font, text = captured[0]
    center = _outline_center(font, text)
    badge_center = _badge_rect(size / 16.0).center()

    assert origin.x() + center.x() == pytest.approx(badge_center.x(), abs=0.05), "横向墨迹中心没落在徽标中心"
    assert origin.y() + center.y() == pytest.approx(badge_center.y(), abs=0.05), "纵向墨迹中心没落在徽标中心"


# --------------------------------------------------------------------------- #
# 对照实验：把旧版 AlignCenter 画法复刻一遍，确认上面的断言确实有判别力。
# 如果这条测试不再失败，说明容差已经松弛到抓不住「偏下一点」了。
# --------------------------------------------------------------------------- #
def _render_legacy(level: int, color: str, size: int) -> QImage:
    """逐行复刻旧的 AlignCenter 画法（徽标 + 数字），只用于对照实验。"""
    from app.ui.tray import (
        BADGE_RADIUS,
        PERCENT_FONT,
        PERCENT_FONT_COMPACT,
        _badge_rect,
    )

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    base = QColor(color)
    scale = size / 16.0
    badge = _badge_rect(scale)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(base)
    painter.drawRoundedRect(badge, BADGE_RADIUS * scale, BADGE_RADIUS * scale)
    painter.setPen(foreground_on(base))
    text = str(min(100, int(level)))
    painter.setFont(theme.font((PERCENT_FONT if len(text) < 3 else PERCENT_FONT_COMPACT) * scale, 700))
    painter.drawText(badge, int(Qt.AlignmentFlag.AlignCenter), text)
    painter.end()
    return pixmap.toImage()


@pytest.mark.usefixtures("real_fonts")
def test_legacy_align_center_geometry_is_rejected():
    """旧画法按行高居中，纵向偏低 —— 新容差必须把它判为不合格。"""
    base = QColor("#0A84FF")
    image = _render_legacy(88, "#0A84FF", 16)
    box = _ink_bbox(image, base, foreground_on(base))
    assert box is not None
    left, top, right, bottom = box
    offset_y = (top + bottom) / 2 - BADGE_CENTER
    assert abs(offset_y) > _center_tolerance(16), (
        f"旧 AlignCenter 画法只偏低 {offset_y:+.2f}px，居然通过了新容差 —— 断言已失效"
    )


def test_badge_center_is_where_we_think_it_is():
    """护栏：徽标几何中心就是 (8*scale, 8*scale)。徽标图形变了要同步改测试口径。"""
    from app.ui.tray import _badge_rect

    for size in (16, 18, 20, 24, 32, 40, 48, 64):
        scale = size / 16.0
        center = _badge_rect(scale).center()
        assert center.x() == pytest.approx(BADGE_CENTER * scale, abs=0.001)
        assert center.y() == pytest.approx(BADGE_CENTER * scale, abs=0.001)
        # 徽标依然占满画布（只留 BADGE_INSET 的抗锯齿余量）
        assert _badge_rect(scale).left() == pytest.approx(BADGE_INSET * scale, abs=0.001)

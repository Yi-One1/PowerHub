"""拖动手柄的 6 个圆点：整数圆心、等距、严格对称，且**是圆点不是方块**（G4 任务 2）。

用户报的现象：「上方点和中间点的间距，大于中间点和下方点的间距」。
根因是旧实现用浮点 `step = 4.2`、`cy = height/2 - step`，三行圆心理论值 7.8 / 12 / 16.2，
再被 `int()` 各截一刀 → 7.5 / 12 / 16，行距于是变成 **4.5 与 4.0**。

第一版修法把直径降成整数 2px 换来严格对称，但 2px 硬边画出来是**小方块**，用户说的是"6 个点"。
所以最终版：**圆心取整数、直径取浮点 2.8、用 `drawEllipse(QRectF)` 以圆心为中心画**，
让抗锯齿把边磨圆。三条约束互相牵制，改任一常数前请先读 `drag_sort.DOT_*` 上方那段注释。

本文件按"渲染出来的墨迹"验收，不读代码里的数字：
* 等距 + 对称：三行/两列墨迹分组的间距相等，且整体关于控件中心严格对称；
* 圆度：单个点的外接盒里，覆盖率不能是 1.0（那是方块），四角墨迹明显弱于中心。
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QWidget

from app.ui.drag_sort import HANDLE_SIZE, DragHandle, ReorderController

pytestmark = pytest.mark.usefixtures("qapp")

# 墨迹判据：手柄自己不画背景，`render()` 会把控件调色板底色填成不透明，
# 所以不能按 alpha 判，改成「与背景色的通道差」。
# 圆点是 0.75 不透明度的深灰，压底色上通道差约 88；抗锯齿边缘约 20~37。
# 取 24 作"实在的墨迹"阈值：边缘不算、点芯算 —— 三行才分得开。
INK_DELTA = 24
# 判"圆不圆"时反过来要**连抗锯齿边缘一起看**，阈值要低
EDGE_DELTA = 4


# --------------------------------------------------------------------------- #
# 装置与工具
# --------------------------------------------------------------------------- #
def make_handle() -> DragHandle:
    """造一个真实手柄（拖动控制器只是占位，本组不测拖拽逻辑）。"""
    host = QWidget()
    host.resize(200, 60)
    row = QWidget(host)
    controller = ReorderController(host, key_of=lambda widget: "row", columns=1)
    return DragHandle(row, controller)


def render(widget: QWidget) -> QImage:
    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    widget.render(image)
    return image


def delta(image: QImage, background, x: int, y: int) -> int:
    color = image.pixelColor(x, y)
    return max(
        abs(color.red() - background.red()),
        abs(color.green() - background.green()),
        abs(color.blue() - background.blue()),
    )


def ink_columns(image: QImage, threshold: int = INK_DELTA) -> list[int]:
    background = image.pixelColor(0, 0)
    return [
        x
        for y in range(image.height())
        for x in range(image.width())
        if delta(image, background, x, y) > threshold
    ]


def ink_rows(image: QImage, threshold: int = INK_DELTA) -> list[int]:
    background = image.pixelColor(0, 0)
    return [
        y
        for y in range(image.height())
        for x in range(image.width())
        if delta(image, background, x, y) > threshold
    ]


def group(values: list[int]) -> list[tuple[int, int]]:
    """把连续坐标合并成「段」：[起, 止]（闭区间）。"""
    spans: list[tuple[int, int]] = []
    for value in sorted(set(values)):
        if spans and value - spans[-1][1] <= 1:
            spans[-1] = (spans[-1][0], value)
        else:
            spans.append((value, value))
    return spans


def assert_even_dot_grid(image: QImage, width: int, height: int) -> None:
    """3 行 2 列圆点：行距相等、上下/左右关于控件中心严格对称。

    对称判据：墨迹在闭区间 [起, 止] 上，其**连续范围** [起, 止+1) 的中点必须正好落在
    控件中心（width/2、height/2），也就是 `起 + 止 + 1 == 边长`。
    """
    rows = group(ink_rows(image))
    cols = group(ink_columns(image))
    assert len(rows) == 3, f"应有三行圆点，实际 {rows}"
    assert len(cols) == 2, f"应有两列圆点，实际 {cols}"

    tops = [span[0] for span in rows]
    first_gap = tops[1] - tops[0]
    second_gap = tops[2] - tops[1]
    assert first_gap == second_gap, f"三行不等距：上行距 {first_gap}px、下行距 {second_gap}px（{rows}）"

    assert rows[0][0] + rows[2][1] + 1 == height, f"三行整体不关于水平中线对称：{rows} in h={height}"
    assert cols[0][0] + cols[1][1] + 1 == width, f"两列不关于竖直中线对称：{cols} in w={width}"

    for span in rows:
        thickness = span[1] - span[0] + 1
        assert 2 <= thickness <= 3, f"圆点核芯高度应在 2~3px，实际 {thickness}px"


# --------------------------------------------------------------------------- #
# 圆度：单个点不能是方块
# --------------------------------------------------------------------------- #
def dot_window(centre: tuple[int, int], dot_size: float | None = None) -> tuple[int, int, int, int]:
    """单个圆点的观察窗（闭区间）。

    圆心落在整数格上、直径 2.8，所以它只覆盖 `[cx-2, cx+1] × [cy-2, cy+1]` 这 4×4 个像素。
    为什么不用 ±2 的 5×5：相邻圆点间距只有 4px，多取一行会把下一颗点的抗锯齿边缘框进来，
    中间像素就落到空隙里了（第一版就是这么翻车的）。
    """
    import math

    import app.ui.drag_sort as drag_sort  # 现取：直径可能被上层改过，别在 import 时绑定

    size = drag_sort.DOT_SIZE if dot_size is None else dot_size
    cx, cy = centre
    # 圆点覆盖 [cx - size/2, cx + size/2)，横向占 ceil(size/2) 个像素。
    # 别用 round(2.8/2)=round(1.4)=1 —— 会把窗开小、只圈住点芯，方块就混过去了。
    reach = math.ceil(size / 2)
    return (cx - reach, cy - reach, cx + reach - 1, cy + reach - 1)


def dot_metrics(image: QImage, centre: tuple[int, int], dot_size: float | None = None) -> dict:
    """量单个圆点的"圆度"：墨迹外接盒的覆盖率 + 四角/中心墨迹强度。

    `dot_size` 只在自证用例里显式给（画的是"如果改成方块/如果改回 3px"这类反例图），
    正常用例留空、跟随实现里的真实直径。
    """
    background = image.pixelColor(0, 0)
    left_w, top_w, right_w, bottom_w = dot_window(centre, dot_size)
    ink = [
        (x, y)
        for y in range(top_w, bottom_w + 1)
        for x in range(left_w, right_w + 1)
        if delta(image, background, x, y) > EDGE_DELTA
    ]
    assert ink, f"圆心 {centre} 的观察窗 {dot_window(centre, dot_size)} 里没有墨迹"
    left = min(x for x, _ in ink)
    right = max(x for x, _ in ink)
    top = min(y for _, y in ink)
    bottom = max(y for _, y in ink)
    area = (right - left + 1) * (bottom - top + 1)
    corners = [
        delta(image, background, left, top),
        delta(image, background, right, top),
        delta(image, background, left, bottom),
        delta(image, background, right, bottom),
    ]
    middle = delta(image, background, (left + right) // 2, (top + bottom) // 2)
    return {
        "bbox": (left, top, right, bottom),
        "size": (right - left + 1, bottom - top + 1),
        "coverage": len(ink) / area,
        "corners": corners,
        "middle": middle,
    }


def assert_dot_is_round(image: QImage, centre: tuple[int, int], dot_size: float | None = None) -> None:
    """圆点判据：外接盒覆盖率 <= 0.85（方块恒为 1.0），且四角 <= 中心的一半。"""
    metrics = dot_metrics(image, centre, dot_size)
    assert metrics["coverage"] <= 0.85, (
        f"圆心 {centre} 处的点覆盖率 {metrics['coverage']:.2f}（≈1.0 说明是方块）：{metrics}"
    )
    assert metrics["middle"] > 0, f"圆心 {centre} 处中心像素没有墨迹：{metrics}"
    worst_corner = max(metrics["corners"])
    assert worst_corner <= metrics["middle"] * 0.5, (
        f"圆心 {centre} 处四角墨迹 {metrics['corners']} 与中心 {metrics['middle']} 同强，说明是硬边方块"
    )


def _canvas() -> QImage:
    """空白画布：模拟 `render()` 会填的不透明控件底色。"""
    image = QImage(HANDLE_SIZE[0], HANDLE_SIZE[1], QImage.Format.Format_ARGB32)
    image.fill(QColor("#EFEFEF"))
    return image


def render_squares(corners: list[tuple[int, int]], size: int) -> QImage:
    """按"左上角 + 整数边长"画方块（旧实现与反例用）。"""
    image = _canvas()
    painter = QPainter(image)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#5C5C61"))
    painter.setOpacity(0.75)
    for x, y in corners:
        painter.drawRect(x, y, size, size)
    painter.end()
    return image


def render_round(centres: list[tuple[int, int]], size: float = 2.8) -> QImage:
    """按"圆心 + 浮点直径"画抗锯齿圆点（正解与圆度自证用）。"""
    image = _canvas()
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#5C5C61"))
    painter.setOpacity(0.75)
    radius = size / 2.0
    for cx, cy in centres:
        painter.drawEllipse(QRectF(cx - radius, cy - radius, size, size))
    painter.end()
    return image


def legacy_layout(width: int, height: int) -> list[tuple[int, int]]:
    """G4 之前的画法（浮点步长 + int 截断）的圆点左上角。"""
    layout: list[tuple[int, int]] = []
    step, dot = 4.2, 2.0
    cx, cy = width / 2, height / 2 - step
    for row in range(3):
        for col in (-1, 1):
            layout.append((int(cx + col * step - dot / 2), int(cy + row * step - dot / 2)))
    return layout


# --------------------------------------------------------------------------- #
# 1. 版式：等距 + 严格对称
# --------------------------------------------------------------------------- #
def test_handle_dots_are_evenly_spaced_and_symmetric(qapp):
    handle = make_handle()
    assert_even_dot_grid(render(handle), *HANDLE_SIZE)


def test_handle_dot_centres_are_symmetric_by_construction(qapp):
    """版面数学：圆心由控件中心反推，横向 4+10=14、纵向 8+16=24（不依赖取整）。"""
    handle = make_handle()
    centres = handle.dot_centres()
    assert len(centres) == 6
    xs = sorted({x for x, _ in centres})
    ys = sorted({y for _, y in centres})
    width, height = HANDLE_SIZE
    assert xs[0] + xs[-1] == width, f"两列圆心不对称：{xs}（应满足 {xs[0]}+{xs[-1]}={width}）"
    assert ys[0] + ys[-1] == height, f"三行圆心不对称：{ys}（应满足 {ys[0]}+{ys[-1]}={height}）"
    assert ys[1] - ys[0] == ys[2] - ys[1], f"三行不等距：{ys}"


def test_handle_dot_centres_match_the_rendered_ink(qapp):
    """版面数学与真正画出来的墨迹必须是同一套：每行/每列都能找到对应圆心。"""
    handle = make_handle()
    image = render(handle)
    rows = group(ink_rows(image))
    cols = group(ink_columns(image))
    centres = handle.dot_centres()

    for span in rows:
        assert any(span[0] - 1 <= cy <= span[1] + 1 for _, cy in centres), f"第 {span} 行找不到圆心"
    for span in cols:
        assert any(span[0] - 1 <= cx <= span[1] + 1 for cx, _ in centres), f"第 {span} 列找不到圆心"


# --------------------------------------------------------------------------- #
# 2. 圆度：必须是"点"，不能是硬边方块
# --------------------------------------------------------------------------- #
def test_handle_dots_are_round_not_squares(qapp):
    """用户说的是"6 个点"：外接盒不能被填满，四角必须明显弱于中心。

    实测（14×24 手柄、0.75 不透明度深灰、底色 #EFEFEF）：
      浮点椭圆 2.8 → 覆盖率 0.75、四角 0/0/0/0、中心 110；
      整数 2px 方块 → 覆盖率 1.00、四角 88 与中心 88 同强。
    """
    handle = make_handle()
    image = render(handle)
    for centre in handle.dot_centres():
        assert_dot_is_round(image, centre)


def test_roundness_assertion_catches_hard_squares():
    """判别力自证：把同一套圆点画成方块，圆度检查必须报错。"""
    centres = [(4, 8), (10, 8), (4, 12), (10, 12), (4, 16), (10, 16)]
    # 方块：左上角对齐（旧写法），2px 硬边
    squares = render_squares([(3, 7), (9, 7), (3, 11), (9, 11), (3, 15), (9, 15)], size=2)
    with pytest.raises(AssertionError, match="方块"):
        assert_dot_is_round(squares, (4, 8), dot_size=2)

    # 同一套判据套在正解（浮点椭圆）上必须通过
    assert_dot_is_round(render_round(centres), (4, 8), dot_size=2.8)


def test_assertion_catches_the_old_non_uniform_layout():
    """判别力自证：旧算法（浮点步长 + int 截断）画出的图必须让等距断言失败。"""
    image = render_squares(legacy_layout(*HANDLE_SIZE), size=3)
    with pytest.raises(AssertionError, match="不等距"):
        assert_even_dot_grid(image, *HANDLE_SIZE)

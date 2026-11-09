"""主面板：无边框柔光玻璃窗 + 设备卡片网格 + 设置页 + 托盘联动。"""
from __future__ import annotations

import ctypes
import logging
import time
from typing import Optional

from PySide6.QtCore import QEvent, QPoint, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.config import BACKGROUND_LIVE_GLASS, BACKGROUND_WHITE, DeviceRegistry, SettingsStore
from ..core.discovery import build_device_config
from ..core.model import Snapshot
from ..core.monitor import Monitor
from ..core.paths import APP_DISPLAY_NAME, APP_EN_NAME, APP_VERSION, resource_root
from ..core.presence import filter_visible, hidden_devices, ordered_devices
from . import theme
from .backdrop import capture_screen
from .cards import DeviceCard
from .drag_sort import DragHandle, ReorderController
from .glass import GlassSurface, IconButton, apply_shadow, clear_backdrop, paint_glass, set_backdrop
from .settings import SettingsPane
from .tray import TrayController

log = logging.getLogger(__name__)

MARGIN = 12          # 阴影留白，改小以减少截图软件识别的窗口边界与实际内容的偏差
CONTENT_WIDTH = 420
HEADER_HEIGHT = 58
# 窗口与主屏「可用区域」（已扣掉任务栏）之间的固定留白。
# 定位（_place_initial）与兜底夹取（_keep_in_screen）必须共用这一个数值：
# 旧版一个写 10、一个写 8，打开时刚算好的位置在随后的夹取里又被挪 2px，
# 而且两处数值谁对谁错没人说得清。测试也从这里导入，不许再写死 8/10。
PANEL_EDGE_MARGIN = 10
# 面板显示期间重取桌面底图的间隔。取整屏 + 1/8 缩放约 20~30 ms，
# 15 秒一次摊下来对 CPU 的影响可以忽略，但换壁纸能在一刻钟内跟上。
BACKDROP_REFRESH_MS = 15_000
# 外壳的不透明度：取到桌面底图时让壁纸透上来；取不到就用实一点的静态玻璃
SHELL_ALPHA_WITH_BACKDROP = 0.74
SHELL_ALPHA_STATIC = 0.86


def shell_alpha(has_backdrop: bool) -> float:
    return SHELL_ALPHA_WITH_BACKDROP if has_backdrop else SHELL_ALPHA_STATIC
FOOTER_HEIGHT = 42
CARD_HEIGHT = 152
CARD_GAP = 12
PAGE_PADDING = 20

# 品牌行的纵向微调（px）：三个标签都用 AlignBottom 排在同一条底边上，但字号差得多
# （17px 中文 / 11px 西文 / 10px 胶囊，控件高实测 23 / 17 / 18，后两个已含下面那点补偿），
# 底边齐平时那行小字在视觉上会显得往下坠 —— 所以按真实渲染的墨迹做了 2px 的光学微调。
# 实测（tests/test_ui_header_brand.py 离屏 1:1 渲染、按 alpha 取墨迹）：
#   · 不补偿时西文墨迹底边只比中文高 1px —— 也就是"共用底边"的字面结果，几何上没毛病；
#   · 补 2px 后西文整体抬高 2px，视觉重心与中文对齐，8 倍放大图看起来才不歪。
# 换句话说这是**光学校准**，不是几何纠偏：改字号/字重/字体后必须重新标定。
#   BRAND_EN_NUDGE  —— 西文名的底部内边距，把文字本身抬高（底色透明，不影响观感）；
#   BRAND_CHIP_RISE —— 版本胶囊的 QSS 下外边距。它参与 sizeHint，AlignBottom 下
#                      标签底边不动、整体变高 n px，于是胶囊上沿与里面的文字一起升高
#                      n px（文字在胶囊内仍然居中，实测上下留白 4/5px），
#                      所以胶囊底边与中文墨迹底边依旧齐平。
# 两者都会参与 sizeHint，所以抬高之后布局不会重叠。
# 数值按实测墨迹定：差 1px 就能看出来，别随手改。
BRAND_EN_NUDGE = 2
BRAND_CHIP_RISE = 2


def version_text() -> str:
    """版本标签文本（形如 ``v1.8.4``）。

    刻意在**函数体内**读模块级 ``APP_VERSION``，而不是在 import 时就拼成字面量：
    这样版本号只有 ``app/core/paths.py`` 一个来源，测试也能通过替换模块属性
    验证标签确实来自常量而非硬编码。
    """
    return f"v{APP_VERSION}"


# ------------------------------------------------------------------ 胶囊（chip）配色
# 面板上有两颗长得很像的胶囊：头部那颗「版本号」和页脚那颗「状态」。两者必须是**同一套灰**，
# 否则同一界面里会出现两种灰的同一个控件。所以配色只在这里定义一次，样式由下面的函数生产，
# 页脚 4 种状态（初始 / 演示数据 / N 台暂无电量 / 全部已连接）也全部走这两个函数 ——
# 别在别处再写 `rgba(120,120,128,…)` 或 `color: {theme.TEXT_SECONDARY}` 的字面量。
#
# 为什么字色不是 TEXT_SECONDARY（#5C5C61）：胶囊压在玻璃面上，玻璃面不是纯白 ——
# 中心被白纱压到 FACE_TARGET=226 级灰度，实测最暗角约 202 级（211 级面再乘 0.9 的取样衰减；
# 比 FACE_TARGET - EDGE_FALLOFF_LEVELS = 214 那档更保守，测试按 202 算）。
# 胶囊自己那层半透明底还会把面再压暗，于是"字 vs 底"的对比度比看上去更低：
#   #5C5C61 + alpha 0.10 → 226 面 4.62、202 面 3.74（QA 报的"低于 AA"就是这个组合）
#   #5C5C61 + alpha 0    → 202 面 4.06 ← 连"底色全透明"都到不了 4.3，这是它的数学上限，
#   所以只调透明度救不回来，必须加深**字本身**。
# 最终取 #4A4A4F（比 TEXT_SECONDARY 深一档，仍明显轻于 TEXT_PRIMARY #1C1C1E，不新增 token），
# 底色透明度取 0.10 —— 再淡下去胶囊底与面板面只差 1.06:1，"胶囊"这个形状就快看不见了，
# 形状本身也是要传的信息。合成后的实测四档（#4A4A4F on rgba(120,120,128,0.10)）：
#   纯白 255 面 7.87、中心 226 面 6.13、边缘 214 面 5.54、最暗角 202 面 4.95
# 合成公式：合成通道 = 胶囊底色 × alpha + 面灰度 × (1 - alpha)，逐通道四舍五入取整，
# 再按 WCAG 相对亮度算对比度（theme.contrast_ratio）。
# ⚠️ 改下面三个数之前先跑 tests/test_ui_header_brand.py 里的对比度用例（两颗胶囊都覆盖）。
CHIP_TEXT = "#4A4A4F"
CHIP_FILL = (120, 120, 128)      # 中性灰底；透明度单独给
CHIP_FILL_ALPHA = 0.10

# 「全部已连接」的状态圆点。为什么不用 theme.OK（#2FC48A）：
# 那是给进度环/条形这类**大面积图形**调的亮绿，压在浅灰胶囊底（叠面后 #D7D7D8）上
# 对比度只有 1.56:1、最暗角 1.26:1 —— 连 WCAG 1.4.11 对图形元素要求的 3:1 都到不了，
# 于是"绿底绿字"的旧胶囊（1.59 / 1.29）等于什么都看不见。
# 取同色相压深两档的 #12734A：vs 灰底 226 面 4.08、202 面 3.30，两档都过 3:1。
# 就地写色值、不加 theme token（只有这一处用；theme.OK 仍是环/条的主色，不动它）。
CHIP_OK_DOT = "#12734A"
# 圆点自己画（不用富文本的「●」字符）：富文本会把 QLabel 的 sizeHint 抬高 2px，
# 胶囊跟着变高；自绘在像素上可控，也不依赖字体里有没有这个字形。
CHIP_DOT_SIZE = 6       # 圆点直径
CHIP_DOT_LEFT = 9       # 圆点左边缘（与 QSS 的左右 9px 内边距对齐）
CHIP_DOT_INDENT = 21    # 有圆点时文字让开的左侧内边距（圆点 + 呼吸位）


def _chip_background() -> str:
    """胶囊默认底色（中性灰 + 低透明度）。"""
    red, green, blue = CHIP_FILL
    return f"rgba({red},{green},{blue},{CHIP_FILL_ALPHA:g})"


def chip_style(color: str = CHIP_TEXT, background: str | None = None, padding_left: int = 9) -> str:
    """页脚状态胶囊的 QSS（圆角 9px、上下 3px / 左右 9px）。

    默认走共用灰。演示数据（琥珀）只换颜色，形状参数仍然只有这一份；
    「全部已连接」不再换色 —— 它是灰底 + 一个 `CHIP_OK_DOT` 绿点（见该常量的注释），
    绿点靠 `padding_left` 在左侧让出位置，文字整体右移。
    """
    return (
        f"color: {color}; background: {background or _chip_background()};"
        f"border-radius: 9px; padding: 3px 9px 3px {padding_left}px;"
    )


class _StatusChip(QLabel):
    """页脚状态胶囊：圆角灰底 + 可选的左侧状态圆点。

    圆点自己画，不用富文本「●」也不用子控件：
    · 富文本会把 QLabel 的 sizeHint 抬高 2px（胶囊跟着变高，用户能看出来）；
    · 子控件要手动跟 resize 同步位置；
    · 自绘只需要一个颜色字段，且在像素上完全可控、不依赖字体有没有这个字形。
    """

    def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self._dot_color: Optional[str] = None

    def set_dot(self, color: Optional[str]) -> None:
        """设置或清除左侧圆点（只影响绘制，不改变控件尺寸）。"""
        self._dot_color = color
        self.update()

    def dot_color(self) -> Optional[str]:
        return self._dot_color

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if not self._dot_color:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._dot_color))
        top = (self.height() - CHIP_DOT_SIZE) // 2
        painter.drawEllipse(CHIP_DOT_LEFT, top, CHIP_DOT_SIZE, CHIP_DOT_SIZE)
        painter.end()


def version_chip_style(color: str = CHIP_TEXT) -> str:
    """头部版本胶囊的 QSS：与页脚同色，形状小一档，另加 2px 下外边距做基线补偿。"""
    return (
        f"color: {color}; background: {_chip_background()};"
        # 下面这段 `margin: 0 0 Npx 0` 的字面形式被 test_compensation_constants_are_wired_into_the_widgets
        # 依赖，改成 margin-bottom 或换插值方式会让那条断言失败 —— 要改先一起改断言。
        f"border-radius: 7px; padding: 1px 7px; margin: 0 0 {BRAND_CHIP_RISE}px 0;"
    )


class _Shell(GlassSurface):
    """窗体内层：整块大圆角玻璃。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, radius=30, alpha=SHELL_ALPHA_WITH_BACKDROP)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # 纯白模式整块不透明，由 _apply_window_blur 依据背景模式开关
        self.solid = False

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        paint_glass(
            painter,
            rect,
            self.radius,
            alpha=self.base_alpha,
            border_alpha=0.92,
            offset=self.backdrop_offset(),
            solid=self.solid,
        )
        painter.end()


class Panel(QWidget):
    """托盘应用的浮动面板。"""

    hidden = Signal()

    def __init__(self, registry: DeviceRegistry, store: SettingsStore, monitor: Monitor, tray: TrayController) -> None:
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.registry = registry
        self.store = store
        self.monitor = monitor
        self.tray = tray
        self._cards: dict[str, DeviceCard] = {}
        self._snapshots: dict[str, Snapshot] = {}
        self._notified: dict[str, float] = {}
        self._drag_offset: Optional[QPoint] = None
        self._settings_open = False
        # 只表示"show_panel() 跑过没有"，不再决定要不要定位（定位是每次打开都做）。
        # 现在服务于 _toggle_settings / _on_devices_changed 里的兜底夹取 ——
        # 首次显示之前窗口还没被摆过，那时不该去做"按当前几何夹取"这种动作。
        self._first_show = True
        self._shown_at = 0.0
        self._has_backdrop = False
        self._build()
        self.monitor.discovered.connect(self._on_discovered)

        self._hotplug = QTimer(self)
        self._hotplug.setSingleShot(True)
        self._hotplug.setInterval(1200)
        self._hotplug.timeout.connect(self._on_hotplug)

        # 显示期间定时重取桌面底图：换壁纸 / 别的窗口移到面板后面时，
        # 玻璃里的颜色会跟着变，而不是停在打开那一刻。隐藏时停掉，不占 CPU。
        self._backdrop_timer = QTimer(self)
        self._backdrop_timer.setInterval(BACKDROP_REFRESH_MS)
        self._backdrop_timer.timeout.connect(self._refresh_backdrop)

        # 拖动时实时刷新玻璃：move 事件很密，用 16ms 定时器节流到约 60fps
        self._drag_update_timer = QTimer(self)
        self._drag_update_timer.setInterval(16)
        self._drag_update_timer.setSingleShot(False)
        self._drag_update_timer.timeout.connect(self._on_drag_update)

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle(APP_DISPLAY_NAME)
        icon_path = resource_root() / "app" / "assets" / "app.ico"
        if icon_path.exists():
            from PySide6.QtGui import QIcon

            self.setWindowIcon(QIcon(str(icon_path)))

        root = QVBoxLayout(self)
        root.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        root.setSpacing(0)

        self.shell = _Shell(self)
        apply_shadow(self.shell, blur=28, dy=10, alpha=40)
        root.addWidget(self.shell)

        column = QVBoxLayout(self.shell)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        column.addWidget(self._build_header())

        self.stack = QStackedWidget(self.shell)
        self.stack.setStyleSheet("background: transparent;")
        self.stack.addWidget(self._build_devices_page())
        self.settings = SettingsPane(self.registry, self.store, self.stack)
        self.settings.changed.connect(self._on_settings_changed)
        self.settings.devices_changed.connect(self._on_devices_changed)
        self.stack.addWidget(self.settings)
        column.addWidget(self.stack, 1)

        column.addWidget(self._build_footer())

        self._resize_for_rows()
        self._apply_window_blur()
        QTimer.singleShot(0, self._place_initial)

    def _build_header(self) -> QWidget:
        header = QWidget(self.shell)
        header.setFixedHeight(HEADER_HEIGHT)
        header.setStyleSheet("background: transparent;")
        header.installEventFilter(self)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(PAGE_PADDING, 14, 14, 4)
        layout.setSpacing(6)

        text_box = QVBoxLayout()
        text_box.setSpacing(0)
        text_box.setContentsMargins(0, 0, 0, 0)

        # 品牌行：中文名 + 英文名 + 版本胶囊，三者共用一条底边；
        # 行尾的 stretch 负责把右侧三个圆钮留在最右边（text_box 自己有 stretch=1）。
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(0, 0, 0, 0)
        brand_row.setSpacing(6)

        self.title = QLabel(APP_DISPLAY_NAME, header)
        self.title.setFont(theme.font(17, 600, theme.DISPLAY_FAMILIES, -0.2))
        self.title.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; background: transparent;")
        brand_row.addWidget(self.title, 0, Qt.AlignmentFlag.AlignBottom)

        self.brand_en = QLabel(APP_EN_NAME, header)
        self.brand_en.setFont(theme.font(11, 500, theme.TEXT_FAMILIES))
        self.brand_en.setStyleSheet(f"color: {theme.TEXT_TERTIARY}; background: transparent;")
        # 底部内边距 = 西文的光学抬高量，见 BRAND_EN_NUDGE 的注释
        self.brand_en.setContentsMargins(0, 0, 0, BRAND_EN_NUDGE)
        brand_row.addWidget(self.brand_en, 0, Qt.AlignmentFlag.AlignBottom)

        self.version_chip = QLabel(version_text(), header)
        self.version_chip.setFont(theme.font(10, 600))
        self.version_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 复用页脚胶囊那套观感：半透明底 + 圆角 + 左右留白，尺寸更小一档；
        # margin-bottom 把胶囊里的文字一起抬高（底边保持齐平），见 BRAND_CHIP_RISE 的注释。
        # 配色与页脚那颗共用 CHIP_*，理由见 version_chip_style() 上面那段推导。
        self.version_chip.setStyleSheet(version_chip_style())
        brand_row.addWidget(self.version_chip, 0, Qt.AlignmentFlag.AlignBottom)

        brand_row.addStretch(1)
        text_box.addLayout(brand_row)

        self.subtitle = QLabel("正在扫描…", header)
        self.subtitle.setFont(theme.font(10.5, 400))
        self.subtitle.setStyleSheet(f"color: {theme.TEXT_TERTIARY}; background: transparent;")
        self.subtitle.setMinimumWidth(0)
        self.subtitle.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        text_box.addWidget(self.subtitle)
        layout.addLayout(text_box, 1)

        self.refresh_btn = IconButton("refresh", header, diameter=28)
        self.refresh_btn.setToolTip("立即刷新")
        self.refresh_btn.clicked.connect(self._on_refresh)
        layout.addWidget(self.refresh_btn)

        self.gear_btn = IconButton("gear", header, diameter=28)
        self.gear_btn.setToolTip("设置")
        self.gear_btn.clicked.connect(self._toggle_settings)
        layout.addWidget(self.gear_btn)

        self.close_btn = IconButton("close", header, diameter=28)
        self.close_btn.setToolTip("收起到托盘")
        self.close_btn.clicked.connect(self.hide)
        layout.addWidget(self.close_btn)
        return header

    def _build_devices_page(self) -> QWidget:
        page = QWidget(self.shell)
        page.setStyleSheet("background: transparent;")
        self.grid = QGridLayout(page)
        self.grid.setContentsMargins(PAGE_PADDING, 4, PAGE_PADDING, 8)
        self.grid.setHorizontalSpacing(CARD_GAP)
        self.grid.setVerticalSpacing(CARD_GAP)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
        self._page = page
        # 卡片拖拽排序：拖动卡片左上角的 ⋮⋮ 手柄，顺序写回 device_order
        self._reorder = ReorderController(
            page,
            key_of=lambda card: str(getattr(card, "device_id", "") or ""),
            columns=2,
            parent=self,
        )
        self._reorder.reordered.connect(self._on_card_reorder)
        self._rebuild_cards()
        return page

    def _build_footer(self) -> QWidget:
        footer = QWidget(self.shell)
        footer.setFixedHeight(FOOTER_HEIGHT)
        footer.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(footer)
        layout.setContentsMargins(PAGE_PADDING, 2, PAGE_PADDING, 14)
        layout.setSpacing(8)

        self.footer_text = QLabel("尚未同步", footer)
        self.footer_text.setFont(theme.font(10.5, 400))
        self.footer_text.setStyleSheet(f"color: {theme.TEXT_TERTIARY}; background: transparent;")
        layout.addWidget(self.footer_text)
        layout.addStretch(1)

        self.chip = _StatusChip("", footer)
        self.chip.setFont(theme.font(10, 600))
        self.chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.chip.setStyleSheet(chip_style())
        self.chip.hide()
        layout.addWidget(self.chip)
        return footer

    # ------------------------------------------------------------- 卡片布局
    def _card_width(self) -> int:
        return (CONTENT_WIDTH - 2 * PAGE_PADDING - CARD_GAP) // 2

    def visible_devices(self) -> list:
        """当前该占位的设备：已启用、未因断连收起，并按用户自定义顺序排列。"""
        visible = filter_visible(self.registry.enabled_devices(), self._snapshots, self.store.prefs)
        return ordered_devices(visible, self.store.prefs)

    def _rebuild_cards(self) -> None:
        for card in self._cards.values():
            self.grid.removeWidget(card)
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()

        devices = self.visible_devices()
        for index, cfg in enumerate(devices):
            type_cfg = self.registry.type_of(cfg)
            card = DeviceCard(
                cfg.id,
                cfg.display_name,
                type_cfg.label,
                self.store.prefs.color_for_device(cfg),
                self.store.prefs.style_for_device(cfg),
                self._page,
            )
            row, col = divmod(index, 2)
            self.grid.addWidget(card, row, col)
            self._cards[cfg.id] = card
            handle = DragHandle(card, self._reorder)
            handle.move(5, 5)
            handle.raise_()
            snapshot = self._snapshots.get(cfg.id)
            if snapshot:
                card.apply_snapshot(snapshot, self.store.prefs.low_battery_threshold)
        if hasattr(self, "_reorder"):
            self._reorder.set_rows(list(self._cards.values()))
        self._resize_for_rows()

    def _on_card_reorder(self, ids: list) -> None:
        """主界面拖拽结束：写回顺序，设置页与托盘跟着重排。"""
        order = [str(item) for item in ids if str(item)]
        if not order or order == list(self.store.prefs.device_order):
            return
        self.store.prefs.device_order = order
        log.info("主界面拖拽调整顺序：%s", ", ".join(order))
        self.store.save()
        self._rebuild_cards()
        self.settings.refresh_devices()
        self.tray.update_snapshots(self._snapshots)

    def _sync_visibility(self) -> None:
        """断连超时的设备该收起、重新上线的该回来 —— 只有集合真的变了才重建界面。"""
        expected = [cfg.id for cfg in self.visible_devices()]
        if expected != list(self._cards.keys()):
            log.debug("可见设备变化：%s -> %s", list(self._cards.keys()), expected)
            self._rebuild_cards()

    def _resize_for_rows(self) -> None:
        rows = max(1, (len(self._cards) + 1) // 2)
        if self._settings_open:
            # 设置页内容较长（设备清单 + 各类外观），临时拉高窗口，减少滚动
            page_height = 540
        else:
            page_height = rows * CARD_HEIGHT + (rows - 1) * CARD_GAP + 12
        height = HEADER_HEIGHT + page_height + FOOTER_HEIGHT
        self.shell.setFixedSize(CONTENT_WIDTH, height)
        self.setFixedSize(CONTENT_WIDTH + 2 * MARGIN, height + 2 * MARGIN)

    # --------------------------------------------------------------- 位置/拖拽
    def _keep_in_screen(self) -> None:
        """把窗口夹进主屏可用区域，四边各留 ``PANEL_EDGE_MARGIN``。

        边界用「可用区域左/上 + 宽/高」这种**排他右边界**算，而不是
        ``QRect.right()/bottom()`` —— Qt 的 ``right()`` 是 ``left + width - 1``，
        是"最后一个像素列"，拿它减宽度会让实测留白比常量多 1px，
        于是同一份常量在两条路径上量出两个值。

        窗口比可用区域还大时 ``min()`` 会胜出：宁可让左/上边出屏，也要把右/下边
        留在屏内 —— 托盘就在屏幕右下角，用户能抓到的始终是那一角。
        """
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        margin = PANEL_EDGE_MARGIN
        low_x = area.left() + margin
        high_x = area.left() + area.width() - margin - self.width()
        low_y = area.top() + margin
        high_y = area.top() + area.height() - margin - self.height()
        self.move(min(max(low_x, self.x()), high_x), min(max(low_y, self.y()), high_y))

    def _place_initial(self) -> None:
        """把面板摆到主屏右下角（系统托盘区附近）。

        尺寸取 ``self.size()``：``_resize_for_rows()`` 已经用 ``setFixedSize()``
        把几何钉死了，``size()`` 就是那个被钉死的值，不依赖窗口管理器有没有装饰。
        实测（本窗口 frameless）``frameGeometry().size() == size()``、``hide()``
        之后两者也仍然一致，所以**不是**因为"未显示时 frameGeometry 不准"才这么写 ——
        只是 ``size()`` 更直接地对应 ``setFixedSize`` 的语义，少绕一层窗口装饰的概念。

        末尾那次 ``_keep_in_screen()`` 是**幂等兜底**，不是生效中的夹取：
        这里算出的 x/y 恒等于 ``_keep_in_screen`` 的 ``high_x/high_y``，
        所以此刻它是个空操作。留着它只为将来改这段算式时不至于漏掉边界保护，
        「窗口比可用区域还大时保住右/下边」这个结论是算式本身给的，不是 ``min()`` 给的。
        """
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        margin = PANEL_EDGE_MARGIN
        size = self.size()
        x = area.left() + area.width() - margin - size.width()
        y = area.top() + area.height() - margin - size.height()
        self.move(x, y)
        self._keep_in_screen()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            if self.store.prefs.background_mode == BACKGROUND_LIVE_GLASS:
                self._drag_update_timer.start()
            return False
        if event.type() == QEvent.Type.MouseMove and self._drag_offset is not None:
            if event.buttons() & Qt.MouseButton.LeftButton:
                self.move(event.globalPosition().toPoint() - self._drag_offset)
                return False
        if event.type() == QEvent.Type.MouseButtonRelease:
            self._drag_offset = None
            self._drag_update_timer.stop()
        return super().eventFilter(obj, event)

    def _on_drag_update(self) -> None:
        """拖动期间持续重绘，让柔光玻璃按新位置从整屏背景板里取样。"""
        if self._drag_offset is not None and self.isVisible():
            self.shell.update()

    # ------------------------------------------------------------------ 显示
    def show_panel(self) -> None:
        # 无论上次关闭时停在设置页还是电量页，打开时一律回到电量显示页；
        # 托盘菜单里的「设置…」走 open_settings()，会在此之后重新切到设置页。
        # 这一步必须排在定位**之前**：设置页比电量页高一截（见 _resize_for_rows），
        # 先定位再切页会让"按设置页高度算出来的 y"留在屏幕上 ——
        # 收起时停在设置页、下次打开就悬在半空（下边距 200+ px），而不是回右下角。
        if self._settings_open:
            self._toggle_settings()
        if not self.isVisible():
            # 只有"真的要新打开"才定位：用户已经把面板拖到顺手的位置、又从托盘菜单
            # 点了一下（设备行 / 立即刷新 / 第二次启动 exe 唤醒单实例）时，
            # 窗口不该被拽回右下角 —— 那 500+px 的位移纯属打扰，旧版也没有。
            self._place_initial()
            # 必须在 show() 之前截屏，否则截到的是自己
            self._refresh_backdrop()
            self.show()
        self._first_show = False
        self.raise_()
        self.activateWindow()
        self.monitor.refresh()

    def _refresh_backdrop(self) -> None:
        """根据背景模式取桌面底图或回落静态背景。

        live_glass: 取整屏并做柔光玻璃自适应；拖动时颜色跟着走。
        white: 不截屏，直接使用纯白色背景（最省电、最稳定）。
        """
        mode = self.store.prefs.background_mode
        if mode == BACKGROUND_WHITE:
            clear_backdrop()
            self._has_backdrop = False
            self._apply_window_blur()
            return

        if mode == BACKGROUND_LIVE_GLASS and self._has_backdrop:
            # 柔光玻璃模式下已经取过底图就不再重复取，靠定时器刷新
            return

        exclude = self.frameGeometry().adjusted(-6, -6, 6, 6) if self.isVisible() else None
        backdrop = capture_screen(exclude=exclude)
        if backdrop is None or not backdrop.is_valid():
            if not self._has_backdrop:
                clear_backdrop()
                self._apply_window_blur()
            return
        set_backdrop(
            backdrop.pixmap,
            backdrop.palette,
            origin=backdrop.origin,
            scale=backdrop.scale,
        )
        self._has_backdrop = True
        log.debug(
            "背景取样完成：亮度 %.2f，环境色 %s，原点 %s，1/%d 缩放",
            backdrop.palette.luminance,
            backdrop.palette.color.name(),
            backdrop.origin,
            int(backdrop.scale),
        )
        self._apply_window_blur()

    def open_settings(self) -> None:
        self.show_panel()
        if not self._settings_open:
            self._toggle_settings()

    def toggle_panel(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.show_panel()

    def closeEvent(self, event) -> None:  # noqa: N802
        event.ignore()
        self.hide()

    def event(self, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.WindowDeactivate:
            QTimer.singleShot(160, self._maybe_auto_hide)
        return super().event(event)

    def _maybe_auto_hide(self) -> None:
        if not self.isVisible():
            return
        # 刚弹出时（点击托盘、菜单收起）会出现瞬时失焦，别误关
        if time.monotonic() - self._shown_at < 0.5:
            QTimer.singleShot(280, self._maybe_auto_hide)
            return
        if QApplication.activeModalWidget() or QApplication.activePopupWidget():
            return
        if QApplication.activeWindow() is self:
            return
        self.hide()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            if self._settings_open:
                self._toggle_settings()
            else:
                self.hide()
            return
        super().keyPressEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._shown_at = time.monotonic()
        self._apply_window_blur()
        mode = self.store.prefs.background_mode
        # 白色模式不截屏、不刷新；柔光玻璃模式定时重取
        if mode == BACKGROUND_LIVE_GLASS:
            self._backdrop_timer.start()
        elif mode == BACKGROUND_WHITE:
            self._backdrop_timer.stop()
        if not self._has_backdrop and mode != BACKGROUND_WHITE:
            self._refresh_backdrop()


    def hideEvent(self, event) -> None:  # noqa: N802
        # 隐藏后没必要再截屏 —— 低占用的一部分
        self._backdrop_timer.stop()
        self._drag_update_timer.stop()
        super().hideEvent(event)

    def _apply_window_blur(self) -> None:
        """根据背景模式决定外壳画法：

        - 纯白色：整块不透明实心白（solid），与桌面彻底隔开。
        - 柔光玻璃：有底图时让壁纸透上来，无底图时更实一些。
        """
        mode = self.store.prefs.background_mode
        if mode == BACKGROUND_WHITE:
            self.shell.solid = True
            self.shell.base_alpha = 1.0
        else:
            self.shell.solid = False
            self.shell.base_alpha = shell_alpha(self._has_backdrop)
        self.shell.update()

    # ------------------------------------------------------------- 设备热插拔
    def nativeEvent(self, event_type, message):  # noqa: N802
        try:
            if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == 0x0219:  # WM_DEVICECHANGE
                    self._hotplug.start()
        except Exception:  # noqa: BLE001
            pass
        return super().nativeEvent(event_type, message)

    def _on_hotplug(self) -> None:
        log.debug("检测到设备变化，触发刷新")
        self.monitor.refresh()

    # ------------------------------------------------------------------ 交互
    def _on_refresh(self) -> None:
        self.footer_text.setText("正在刷新…")
        self.monitor.refresh()

    def _toggle_settings(self) -> None:
        self._settings_open = not self._settings_open
        self.stack.setCurrentWidget(self.settings if self._settings_open else self._page)
        self.gear_btn.set_kind("back" if self._settings_open else "gear")
        self.gear_btn.setToolTip("返回" if self._settings_open else "设置")
        self.title.setText("设置" if self._settings_open else APP_DISPLAY_NAME)
        # 切页会改高度（设置页比电量页高 200px 上下），所以**锁住下边缘**：
        # 只调 _keep_in_screen() 是不够的 —— 它只在越界时才动，从高页退回矮页时
        # 窗口只会向上缩、腾出来的空间不还给下边缘，面板就"漂"在半空
        # （实测下边距 222px）。这里在切页前记下下边缘，切页后原样放回去，
        # 最后再夹一次防越界 —— 不重算右下角，用户把面板拖到左边时不会被拽回右侧。
        # 用 top()+height() 而不是 frameGeometry().bottom()：Qt 的 bottom() 是
        # top + height - 1（最后一行像素），每切一次页就会往上漂 1px，几次就看得见。
        bottom_edge = self.frameGeometry().top() + self.frameGeometry().height()
        self._resize_for_rows()
        if not self._first_show:
            self.move(self.x(), bottom_edge - self.height())
            self._keep_in_screen()
        if self._settings_open:
            self.footer_text.setText("改动即时保存并生效")
            self.chip.hide()
        elif self._snapshots:
            self._update_footer(self._snapshots)
        if self._settings_open:
            self._update_subtitle()

    def _on_settings_changed(self) -> None:
        self.settings.sync_colors()
        for cfg in self.registry.enabled_devices():
            card = self._cards.get(cfg.id)
            if card:
                # 改名立即生效：卡片标题跟随设置页，不用等卡片重建
                card.set_display_name(cfg.display_name)
                card.set_color(self.store.prefs.color_for_device(cfg))
                card.set_style(self.store.prefs.style_for_device(cfg))
        self.shell.setFixedSize(self.shell.width(), self.shell.height())
        self._resize_for_rows()
        # 背景模式切换时立即生效
        mode = self.store.prefs.background_mode
        if mode == BACKGROUND_WHITE:
            self._backdrop_timer.stop()
        elif mode == BACKGROUND_LIVE_GLASS:
            self._backdrop_timer.start()
        self._refresh_backdrop()
        self._apply_window_blur()
        self.monitor.set_prefs(self.store.prefs)
        if self._snapshots:
            self.apply_snapshots(self._snapshots)
        else:
            self._sync_visibility()
        self.tray.update_snapshots(self._snapshots)

    def _on_devices_changed(self) -> None:
        """设置页新增/删除了设备。"""
        self._rebuild_cards()
        self._resize_for_rows()
        if not self._first_show:
            self._keep_in_screen()
        self._update_subtitle()
        self._update_footer(self._snapshots)
        self.tray.update_snapshots(self._snapshots)
        self.monitor.refresh()

    def _on_discovered(self, devices: list) -> None:
        """监测线程扫到未登记的设备 —— 配置落盘只能在 UI 线程做，所以在这里收口。"""
        added = []
        for device in devices:
            base_id = device.default_id
            if self.registry.is_removed(base_id) or self.registry.get(base_id) is not None:
                continue
            cfg = build_device_config(device, base_id)
            self.registry.add_device(cfg)
            added.append(cfg)
        if not added:
            return
        log.info("自动登记 %d 台设备：%s", len(added), ", ".join(c.display_name for c in added))
        self.settings.refresh_devices()
        self._on_devices_changed()

    # ------------------------------------------------------------------ 数据
    def apply_snapshots(self, snapshots: dict[str, Snapshot]) -> None:
        self._snapshots = snapshots
        self._sync_visibility()
        threshold = self.store.prefs.low_battery_threshold
        for device_id, snapshot in snapshots.items():
            card = self._cards.get(device_id)
            if card:
                card.apply_snapshot(snapshot, threshold)
        self._update_footer(snapshots)
        self._update_subtitle(snapshots)
        self._maybe_notify(snapshots)

    def _update_subtitle(self, snapshots: Optional[dict[str, Snapshot]] = None) -> None:
        if self._settings_open:
            self.subtitle.setText("设备清单、颜色、样式与启动项")
            return
        snapshots = snapshots if snapshots is not None else self._snapshots
        visible_ids = set(self._cards)
        total = len(self._cards)
        online = sum(1 for did, s in snapshots.items() if did in visible_ids and s.online)
        read = sum(1 for did, s in snapshots.items() if did in visible_ids and s.level is not None)
        hidden = len(hidden_devices(self.registry.enabled_devices(), snapshots, self.store.prefs))
        if total == 0:
            self.subtitle.setText(f"{hidden} 台设备均已断开" if hidden else "没有启用的设备")
            return
        text = f"{total} 台设备 · {online} 台在线 · {read} 台可读电量"
        if hidden:
            text += f" · {hidden} 台已收起"
        self.subtitle.setText(text)

    def _update_footer(self, snapshots: dict[str, Snapshot]) -> None:
        recent = max((s.updated_at for s in snapshots.values() if s.updated_at), default=0.0)
        if recent:
            age = int(time.time() - recent)
            age_text = "刚刚" if age < 10 else f"{age // 60} 分钟前" if age >= 60 else f"{age} 秒前"
            self.footer_text.setText(f"最后同步 {age_text} · 每 {self.store.prefs.refresh_seconds} 秒刷新")
        else:
            self.footer_text.setText("等待首次同步…")

        if self.store.prefs.demo:
            self.chip.setText("演示数据")
            # 琥珀色是"演示数据"的专属语义色，只换颜色，形状/字号仍走共用函数
            self.chip.setStyleSheet(chip_style(theme.WARN_TEXT, "rgba(255,159,10,0.18)"))
            self.chip.set_dot(None)
            self.chip.show()
            return

        visible_ids = set(self._cards)
        total = len(self._cards)
        read = sum(1 for did, s in snapshots.items() if did in visible_ids and s.level is not None)
        if total and read < total:
            self.chip.setText(f"{total - read} 台暂无电量")
            self.chip.setStyleSheet(chip_style())
            self.chip.set_dot(None)
            self.chip.show()
            self.chip.setToolTip("把鼠标停在对应卡片上可以看到诊断信息")
        elif total:
            # 灰底 + 绿点：文字回到共用的深灰（浅绿字压浅绿底实测只有 1.59:1），
            # "已连接"这层语义交给左边那个 #12734A 的圆点（4.08 / 3.30，过图形 3:1）。
            # padding_left 为圆点让位，文字不压在点上，胶囊高度不变。
            self.chip.setText("全部已连接")
            self.chip.setStyleSheet(chip_style(padding_left=CHIP_DOT_INDENT))
            self.chip.set_dot(CHIP_OK_DOT)
            self.chip.show()
        else:
            self.chip.set_dot(None)
            self.chip.hide()

    def _maybe_notify(self, snapshots: dict[str, Snapshot]) -> None:
        if not self.store.prefs.notifications:
            return
        threshold = self.store.prefs.low_battery_threshold
        now = time.time()
        for device_id, snapshot in snapshots.items():
            if not snapshot.online or snapshot.level is None or snapshot.charging:
                continue
            if snapshot.level > threshold:
                continue
            last = self._notified.get(device_id, 0.0)
            if now - last < 1800:
                continue
            cfg = self.registry.get(device_id)
            if cfg is None:
                continue
            self._notified[device_id] = now
            self.tray.notify(f"{cfg.display_name} 电量偏低", f"当前 {snapshot.level}%，建议及时充电。")

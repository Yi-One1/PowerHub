"""视觉基调：颜色、字体、通用 QSS。

风格关键词：柔光玻璃（Light Glass）——
大面积低饱和白 + 极细高光描边 + 大圆角 + 柔和外阴影 + 类型色仅用于强调。
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtGui import QColor, QFont, QFontDatabase

TEXT_PRIMARY = "#1C1C1E"
TEXT_SECONDARY = "#5C5C61"
# 原来是 #8E8E93 —— 在纯白上只有 3.3:1，铺到会透壁纸色的玻璃上更低，
# 页脚那行"最后同步刷新"几乎看不见。压深到 #6E6E76（白底 5.1:1，玻璃上 3.5~4.3:1），
# 仍然明显轻于主文字，但小字终于读得清。
TEXT_TERTIARY = "#6E6E76"
DIVIDER = "rgba(60, 60, 67, 0.10)"
SURFACE = "rgba(255, 255, 255, 0.62)"
SURFACE_STRONG = "rgba(255, 255, 255, 0.86)"
BORDER_SOFT = "rgba(255, 255, 255, 0.75)"
ACCENT_BLUE = "#0A84FF"
WARN = "#FF9F0A"
# 徽标 / 小字号里用的警告色：WARN 本身在浅玻璃上只有 1.4:1，只能当图标和进度弧用
WARN_TEXT = "#A05A00"
DANGER = "#FF453A"
OK = "#2FC48A"

DISPLAY_FAMILIES = ["Segoe UI Variable Display", "Segoe UI", "Microsoft YaHei UI", "PingFang SC"]
TEXT_FAMILIES = ["Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI", "PingFang SC"]
NUMBER_FAMILIES = ["Segoe UI Variable Display", "Segoe UI Semibold", "Segoe UI", "Microsoft YaHei UI"]


def _available(families: list[str]) -> list[str]:
    installed = set(QFontDatabase.families())
    return [f for f in families if f in installed] or ["Segoe UI"]


def font(size: float, weight: int = 400, families: list[str] | None = None, letter_spacing: float = 0.0) -> QFont:
    result = QFont()
    result.setFamilies(_available(families or TEXT_FAMILIES))
    result.setPixelSize(int(round(size)))
    result.setWeight(QFont.Weight(weight))
    if letter_spacing:
        result.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, letter_spacing)
    result.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return result


def color(value: str, alpha: float | None = None) -> QColor:
    c = QColor(value)
    if alpha is not None:
        c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


def mix(a: str, b: str, ratio: float) -> QColor:
    ca, cb = QColor(a), QColor(b)
    ratio = max(0.0, min(1.0, ratio))
    return QColor(
        int(ca.red() + (cb.red() - ca.red()) * ratio),
        int(ca.green() + (cb.green() - ca.green()) * ratio),
        int(ca.blue() + (cb.blue() - ca.blue()) * ratio),
    )


def lighten(value: str, ratio: float = 0.25) -> QColor:
    return mix(value, "#FFFFFF", ratio)


def darken(value: str, ratio: float = 0.2) -> QColor:
    return mix(value, "#000000", ratio)


# --------------------------------------------------------------------------- #
# 对比度
#
# 设备颜色由用户自选，可以选到接近白色的值；而卡片底色可能是纯白。
# 这时"忠实还原用户选的颜色"和"看得见"是冲突的 —— 一律以看得见为先，
# 只在对比度不足时派生一个**同色相、明度更极端**的颜色用于绘制，
# 用户配置里存的原色不动（下次换到深色卡片上仍原样生效）。
# --------------------------------------------------------------------------- #
def relative_luminance(value: str | QColor) -> float:
    """WCAG 相对亮度（0 = 全黑，1 = 全白）。"""
    color = QColor(value) if not isinstance(value, QColor) else value

    def channel(raw: int) -> float:
        srgb = raw / 255.0
        return srgb / 12.92 if srgb <= 0.03928 else ((srgb + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(color.red()) + 0.7152 * channel(color.green()) + 0.0722 * channel(color.blue())


def contrast_ratio(a: str | QColor, b: str | QColor) -> float:
    """WCAG 对比比（1.0 ~ 21.0）。3.0 是图形元素的可读下限。"""
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def ensure_contrast(
    color: str | QColor,
    background: str | QColor,
    minimum: float = 3.0,
) -> QColor:
    """保证 color 在 background 上看得出轮廓。

    做法是沿着明度轴把颜色往"远离背景"的方向推（背景亮就往暗推，反之往亮推），
    色相与饱和度保持不变，所以蓝还是蓝、红还是红，只是深浅变了。
    主方向推到底仍不够时才反着推一次；两边都不达标就返回对比更高的那个，
    绝不会无脑返回原色。
    """
    fg = QColor(color) if not isinstance(color, QColor) else QColor(color)
    bg = QColor(background) if not isinstance(background, QColor) else background
    if contrast_ratio(fg, bg) >= minimum:
        return fg

    hue = fg.hueF()
    hue = 0.0 if hue < 0 else hue
    sat = fg.saturationF()
    base_light = fg.lightnessF()
    # 背景亮 → 往暗推；背景暗 → 往亮推
    prefer_darker = relative_luminance(bg) >= 0.5

    def scan(darker: bool) -> tuple[Optional[QColor], float]:
        """沿一个方向逐格推，命中就返回；没命中返回该方向对比最高的那个。"""
        best: Optional[QColor] = None
        best_ratio = 0.0
        for index in range(1, 51):
            light = base_light - 0.02 * index if darker else base_light + 0.02 * index
            if light < 0.0 or light > 1.0:
                break
            candidate = QColor.fromHslF(hue, sat, light)
            ratio = contrast_ratio(candidate, bg)
            if ratio >= minimum:
                return candidate, ratio
            if ratio > best_ratio:
                best, best_ratio = candidate, ratio
        return best, best_ratio

    primary, primary_ratio = scan(prefer_darker)
    if primary is not None and primary_ratio >= minimum:
        return primary
    secondary, secondary_ratio = scan(not prefer_darker)
    if secondary is not None and secondary_ratio > primary_ratio:
        return secondary
    return primary if primary is not None else fg


def app_stylesheet() -> str:
    """全局样式：菜单、工具提示、对话框、滚动条、滑块。"""
    return f"""
    QToolTip {{
        background-color: rgba(28, 28, 30, 0.92);
        color: #FFFFFF;
        border: none;
        border-radius: 8px;
        padding: 6px 10px;
        font-size: 12px;
    }}
    QMenu {{
        background-color: rgba(255, 255, 255, 0.96);
        border: 1px solid rgba(0, 0, 0, 0.08);
        border-radius: 12px;
        padding: 6px;
        color: {TEXT_PRIMARY};
    }}
    QMenu::item {{
        padding: 7px 18px 7px 14px;
        border-radius: 8px;
        font-size: 12px;
    }}
    QMenu::item:selected {{
        background-color: rgba(10, 132, 255, 0.12);
        color: {TEXT_PRIMARY};
    }}
    QMenu::separator {{
        height: 1px;
        background: {DIVIDER};
        margin: 5px 8px;
    }}
    QScrollArea {{ background: transparent; border: none; }}
    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 2px 0;
    }}
    QScrollBar::handle:vertical {{
        background: rgba(60, 60, 67, 0.26);
        border-radius: 4px;
        min-height: 28px;
    }}
    QScrollBar::handle:vertical:hover {{ background: rgba(60, 60, 67, 0.30); }}
    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
        height: 0; width: 0; background: transparent; border: none;
    }}
    QSlider::groove:horizontal {{
        height: 4px;
        border-radius: 2px;
        background: rgba(60, 60, 67, 0.14);
    }}
    QSlider::sub-page:horizontal {{
        height: 4px;
        border-radius: 2px;
        background: {ACCENT_BLUE};
    }}
    QSlider::handle:horizontal {{
        width: 14px; height: 14px;
        margin: -6px 0;
        border-radius: 7px;
        background: #FFFFFF;
        border: 1px solid rgba(0, 0, 0, 0.06);
    }}
    QSpinBox {{
        background: rgba(255, 255, 255, 0.86);
        border: 1px solid rgba(60, 60, 67, 0.12);
        border-radius: 8px;
        padding: 3px 6px;
        color: {TEXT_PRIMARY};
        selection-background-color: rgba(10, 132, 255, 0.20);
        selection-color: {TEXT_PRIMARY};
    }}
    QSpinBox:focus {{ border-color: rgba(10, 132, 255, 0.55); }}
    """

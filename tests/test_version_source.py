"""版本号与打包产物名的「单一来源」守卫（G5）。

为什么用 AST 而不是正则扫源码：``tools/build_exe.py`` 的**模块 docstring 里有一句举例**
（``dist/电量中枢_PowerHub_v1.4.0.exe``），任何 ``"v1.\\d+.\\d+" in source`` 式的
断言都会因为这句举例误红。所以先 ``ast.parse``、只检查真正的字符串常量，
并显式放行 ``ast.get_docstring(tree)``。

守三件事：
1. ``APP_VERSION`` 就是本次要发的版本（防止有人只改测试不改常量）；
2. 打包脚本里不许出现任何版本字面量；
3. ``BUILD_NAME`` / ``FINAL_STEM`` 必须由 ``APP_VERSION`` 拼出，且产物名沿用
   「中文名_英文名_v版本」这条老规则（``dist/`` 里 v1.7.0~v1.8.4 都是这个形状）。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from app.core.paths import APP_DISPLAY_NAME, APP_EN_NAME, APP_VERSION

ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "tools" / "build_exe.py"
# 不带 \\b 边界：版本字面量极可能长成 ``电量中枢_PowerHub_v1.9.0.exe``，
# 前面是下划线（属于 \\w），带 \\b 反而匹配不到 —— 那正是最容易漏掉的一种写法。
VERSION_LITERAL = re.compile(r"v?\d+\.\d+\.\d+")


def test_app_version_matches_this_release():
    """版本号只有一个来源，且必须升到本次发布的 1.9.0。"""
    assert APP_VERSION == "1.9.0", f"APP_VERSION 还是 {APP_VERSION}，发版前忘了升版本"


def test_build_script_has_no_hardcoded_version():
    """打包脚本里除模块 docstring 的举例外，不许出现 ``x.y.z`` 版本字面量。"""
    source = BUILD_SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    module_docstring = ast.get_docstring(tree, clean=False)

    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    offenders = [
        text
        for text in literals
        if text != module_docstring and VERSION_LITERAL.search(text)
    ]
    assert not offenders, (
        f"{BUILD_SCRIPT.name} 里出现了写死的版本字面量 {offenders}，"
        "产物名必须由 APP_VERSION 拼出（否则头部胶囊与 exe 文件名会打架）"
    )


def test_build_artifact_name_comes_from_app_version():
    """ASCII 中间名与最终中文名都由常量拼出，且沿用既有命名规则。"""
    from tools import build_exe

    assert build_exe.BUILD_NAME == f"{APP_EN_NAME}_v{APP_VERSION}", (
        "PyInstaller 的中间名没跟着 APP_VERSION 走"
    )
    assert build_exe.FINAL_STEM == f"{APP_DISPLAY_NAME}_{APP_EN_NAME}_v{APP_VERSION}", (
        "最终产物名没跟着 APP_VERSION 走"
    )
    assert build_exe.FINAL_STEM.startswith(f"{APP_DISPLAY_NAME}_PowerHub_v"), (
        "产物名偏离「中文名_英文名_v版本」规则，dist/ 里的历史产物都是这个形状"
    )

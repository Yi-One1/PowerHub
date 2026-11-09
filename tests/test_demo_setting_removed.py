"""「演示数据」开关移除（G4 任务 1）。

用户诉求：设置页里那个开关是开发/预览用的，正式使用没有意义，误开后界面会一直是假电量。
处理方式（已与主理人确认）：
* **设置页的开关删掉**；
* `Preferences.demo` 字段**保留**，但加载偏好时一律置为 False —— 用户层
  preferences.json 里历史残留的 `"demo": true` 不该让正式启动进演示模式；
* 演示能力本身保留：`main.py --demo`、`tools/screenshot.py`、`Monitor(demo=True)`
  以及页脚那颗「演示数据」琥珀标记都还在（那是"数据是假的"的诚实标注）。
"""
from __future__ import annotations

import json

import pytest
from PySide6.QtWidgets import QLabel

from app.core.config import DeviceRegistry, Preferences, SettingsStore
from app.ui.settings import SettingRow, SettingsPane

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture()
def env(tmp_path):
    registry = DeviceRegistry(user_dir=tmp_path)
    store = SettingsStore(registry, path=tmp_path / "preferences.json")
    return registry, store


# --------------------------------------------------------------------------- #
# 1. 设置页不再有这一项
# --------------------------------------------------------------------------- #
def test_settings_pane_has_no_demo_switch(env):
    registry, store = env
    pane = SettingsPane(registry, store)
    assert not hasattr(pane, "demo_toggle"), "「演示数据」开关应当已被移除"
    assert not hasattr(pane, "_on_demo"), "开关的回调也应当一起删掉"

    titles = [label.text() for label in pane.findChildren(QLabel)]
    assert "演示数据" not in titles, f"设置页仍有「演示数据」这一行：{titles}"
    # 顺手确认这一页还是正常建出来的（不是被整体删空）
    assert pane.findChildren(SettingRow), "设置页应当仍有其它设置行"


# --------------------------------------------------------------------------- #
# 2. 加载时忽略持久化的 true
# --------------------------------------------------------------------------- #
def test_persisted_demo_true_is_ignored_on_load(tmp_path):
    registry = DeviceRegistry(user_dir=tmp_path)
    path = tmp_path / "preferences.json"
    path.write_text(json.dumps({"demo": True, "refresh_seconds": 30}), encoding="utf-8")

    store = SettingsStore(registry, path=path)
    assert store.prefs.demo is False, "残留的 demo: true 不该让正式启动进演示模式"
    assert store.prefs.refresh_seconds == 30, "其它字段照常生效，别把整份偏好丢了"


def test_demo_field_still_exists_for_cli_and_tools():
    """字段必须留着：`--demo` / screenshot / Monitor(demo=True) 都靠它，默认值是 False。"""
    assert Preferences().demo is False
    assert "demo" in Preferences().to_dict()


def test_saving_does_not_write_demo_true_back(tmp_path):
    registry = DeviceRegistry(user_dir=tmp_path)
    path = tmp_path / "preferences.json"
    path.write_text(json.dumps({"demo": True}), encoding="utf-8")

    store = SettingsStore(registry, path=path)
    store.save()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["demo"] is False, "保存时应当把被忽略的 true 落回 false，避免下次再被读到"


# --------------------------------------------------------------------------- #
# 3. 演示能力保留
# --------------------------------------------------------------------------- #
def test_demo_capability_survives_the_switch_removal(env):
    from app.core.monitor import Monitor

    registry, store = env
    # main.py --demo 的做法就是在 load 之后显式置位
    store.prefs.demo = True
    assert Preferences.from_dict({"demo": True}, registry).demo is False
    assert store.prefs.demo is True, "运行时置位仍应生效（--demo 走这条路）"

    assert Monitor(registry, store.prefs, demo=True).demo is True
    # 不给 demo 时不该自动进演示模式（旧代码里 prefs.demo 可能被持久化带进来）
    fresh = SettingsStore(registry, path=store.path)
    assert fresh.prefs.demo is False
    assert Monitor(registry, fresh.prefs).demo is False

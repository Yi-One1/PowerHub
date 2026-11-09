# 项目进展（progress）

> 更新：2026-11-10　版本：**v1.9.0**（`dist/电量中枢_PowerHub_v1.9.0.exe`）　状态：**已推送 GitHub**，
> 本地与 `origin/main` 同步；发布 Release 由用户手动完成（见 `docs/RELEASE_NOTES_v1.9.0.md`）

## 已完成

| 事项 | 提交 |
|---|---|
| G5：升 **v1.9.0** + 打包单文件 exe 到 `dist/`（7 个旧产物一个不动）+ 文档同步；新增版本号 AST 单一来源护栏；`pytest.ini` 加 `--basetemp` 修好「不带参数跑 pytest 会在 sessionfinish 崩」 | `68961ff` |
| 设置页删「演示数据」开关（能力保留、旧配置 `demo:true` 加载即忽略）+ 拖动手柄 6 点改为严格等距 + 「全部已连接」改灰底绿点 | `fa6c7d0` |
| 主页面每次打开都落到**主屏右下角**（托盘区）；顺带修掉「收起时停在设置页 / 齿轮往返」导致的面板悬空 222px | `8756ce6` |
| 主页面头部改为「电量中枢 · PowerHub · v版本」一行并列，版本号取自 `APP_VERSION` | `56c76be` |
| 顺带修掉胶囊对比度：字色 `#5C5C61` → `#4A4A4F`，5 处重复 QSS 收成 `chip_style()` | `56c76be` |
| 托盘数字改为按**墨迹外框**居中：竖直不再视觉偏低（16px 偏低 1px、32px 1.5px、64px 2px → 0） | `7495062` |
| 深色壁纸下玻璃**边缘不再变灰**：白纱厚度改为按目标面亮度反解，边缘只允许比中心暗 12 级；三级灰 #6E6E76 → #66666D | `f24173c` |
| 浅色设备色不再隐形：环/条加**环境阴影**（按对比缺口定强度）+ 卡片淡染 0.10 → 0.16，设备色本身一字不改 | `6729b34` |
| 充电态底色改为**设备原色**（不再整块绿），读不到电量时显示高对比闪电；电池外壳模式的闪电同步加描边 | `1c18044` |
| 托盘数字字号 11.6 → **10.6px**（三位数 9.0 → 8.4），不再贴边发挤 | `d328425` |
| 托盘图标排版优化：数字 9.4→11.6px 并占满徽标，充电标记改为右下角绿点（不再挤数字） | `b830d51` |
| 设备排序改为**拖拽**（设置页设备行 + 主界面卡片都有 ⋮⋮ 手柄），托盘跟随重排 | `82c252a` |
| 修复托盘图标顺序「完全反序」（Windows 把新注册图标插在最前 → 改逆向注册） | `6018db2` |
| 断连收起时长支持 **1 秒 ~ 1 小时**（数值输入 + 单位菜单，去掉了固定档位） | `cf25ccc` `e5a0703` |
| 修复浅色设备颜色下托盘数字看不清（按底色亮度自动切黑/白字） | `380c961` |
| 修复托盘图标顺序与主界面不一致、每次重启还变（启动即建齐 + 逐个注册） | `6db982f` |
| 版本号体系：`APP_VERSION` + 产物名 `电量中枢_PowerHub_v<版本>.exe`，旧产物一律保留 | `bc0f4fa` |
| 修复老用户配置冻结：内置 `devices.json` 的 `version` 一变，用户层内置副本的 `protocol` 段整体按内置刷新 | `018708d` |
| 开机自启注册表值名 `PeripheralBattery` → `PowerHub`，带旧值迁移 | `bd1a72c` |
| 软件更名「电量中枢 / PowerHub」，源码/文档/测试断言全同步 | `5fc27f8` |
| 迈从 G98 Pro：充电标志位改为 `byte6`（有线 `byte9`）的 **bit4** | `b3f36d9` |
| 迈从 G98 Pro：删除误配的 `charging_invert`（曾导致未充电误报充电中） | `408f05e` |
| HECATE G3 MAX：补充电位 `byte7` 的 **bit0**，修复充电不显示「充电中」 | `face728` |
| 进展文档同步到 v1.8.4（含本轮白底白环 + 深色壁纸灰字两轮修复记录） | `d7d1c37` |

测试：**478 passed / 1 skipped**（skip 为真机无应答的 live 用例；本轮新增 `tests/test_version_source.py` 3 条，共 39 个测试文件、479 项）。
显式 `--basetemp` 与**不带参数的 `-m pytest`** 两次跑法结果一致（`pytest.ini` 已固定 basetemp）。

**打包与启动验收（v1.9.0）**：产物 `dist/电量中枢_PowerHub_v1.9.0.exe` = **45,941,141 字节**；
v1.7.0~v1.8.4 七个旧产物的文件名与字节数逐个不变（只多这一件），未部署到桌面。
用新 exe 做了两轮启动验证（均带 `--tray`、各 15s+15s、结束用 `taskkill /T /F` 清理父子进程）：
- `-v --tray`：启动横幅 + `监测线程启动` + **`扫描完成：1/4 台有数据`（DEBUG 行确实落进 `app.log`）**，两段等待内无 `Traceback`/`ERROR`；
- 默认 `--tray`：启动横幅 + `监测线程启动`（无 DEBUG 行，符合 INFO 口径）、无异常。
两轮进程均正常存活到第二段结束、清理后无残留；用户层 `devices.json` 只被读取、未改写。
结论：**已验证启动并跑完一轮扫描**。窗口外观（版本胶囊 / 右下角定位 / 托盘图标）未做视觉确认（按约定不截屏）。

## 关键决策

- **柔光玻璃的白纱厚度是算出来的**：`adaptive_scrim()` 反解 `(FACE_TARGET - 背面) / (255 - 背面)`，
  目标是把玻璃面压到 226 灰阶 —— 亮壁纸只铺底纱让颜色透上来，暗壁纸刚好够灰字读得清。
  不要再退回"固定上限"式的曲线：0.78 那个上限是拍的，深色壁纸下面板只到 #C8，灰字照样糊。
- **边缘融色有上限**：径向白纱的边缘最多比中心暗 `EDGE_FALLOFF_LEVELS = 12` 级
  （`scrim_edge_ratio()`），亮壁纸仍走 0.58 的比例。反过来调会让页脚/副标题/分组标题
  在深色壁纸下掉到 2:1（就是"深色壁纸部分灰字看不清"那次的根因）。
- **悬停提亮走 `paint_glass(highlight=)`**，不能再靠加 alpha：暗壁纸下白纱被目标值锁住，加 alpha 无效果。

- **版本号**：唯一来源 `app/core/paths.py: APP_VERSION`。修 bug 升末位、加功能升中位、不兼容升首位。
  **只有内置设备协议变更时**才同步升 `app/config/devices.json` 的 `version`（它是触达老用户协议刷新的开关）。
- **打包产物**：`电量中枢_PowerHub_v<版本>.exe`，PyInstaller 先用 ASCII 名打包再重命名。
  同版本重打属于重建（会覆盖同名文件），跨版本产物天然不同名。**旧版本一律保留**，删不删由使用者决定。
- **断连收起**：内部按秒存（`offline_hide_seconds`，1~3600），旧配置 `offline_hide_minutes` 自动 ×60 迁移。
  控件是「数值 + 单位菜单」，数值与单位是一个整体输入（10 分钟切到「秒」= 10 秒），越界自动夹紧；
  单位用 `QToolButton + QMenu` 而不是 `QComboBox`（后者弹出列表会先闪一帧黑底）。
- **托盘数字对比度**：`foreground_on()` 按 WCAG 相对亮度、阈值 0.5 选黑/白，浅色设备色不再白字白底。
- **托盘图标排版**：数字模式就是一整块圆角徽标（内缩 0.5、几乎占满 16px 画布），数字 10.6px 加粗居中，
  三位数自动收字号到 8.4；充电用右下角小绿点角标，**数字字号与位置不因充电变化**。
- **数字居中按墨迹算，不按行高算**：`drawText(rect, AlignCenter)` 是 `ascent+descent` 整块行高居中，
  数字没有下伸部 → 基线以下的空白把字形压低（实测 16px 低 1px、64px 低 2px）。
  现在用轮廓路径 `QPainterPath.addText` 的包围盒（亚像素）把**墨迹中心**对齐徽标中心再按基线绘制；
  `tightBoundingRect` 会整数量化到相邻像素，只作兜底，不能当首选。
- **设备排序**：设置页设备行与主界面卡片都用「⋮⋮ 手柄拖动」（`app/ui/drag_sort.py`），
  不用整行拖动 —— 设置页每行里嵌着输入框/取色/开关，整行拖会抢鼠标。
  拖完写 `device_order`，主界面、托盘（`ordered_devices` 同一口径）一起重排。
- **托盘顺序**：启动即按主界面顺序把槽位建齐（未扫到的先灰电池占位），扫描回来**只换图不重建**；
  Windows 把新注册图标插在最前，所以注册要**按显示顺序倒序**（`_do_swap` 里 `reversed`）并逐个注册
  （`CREATE_INTERVAL_MS`）。
- **命名**：中文「电量中枢」/ 英文 `PowerHub`；内部标识 `APP_NAME` 保留 `BatteryGlass`（配置目录 `%APPDATA%\BatteryGlass` 不变 → 零迁移、不丢用户数据）。
- **头部品牌行**：`电量中枢`（17px/600）+ `PowerHub`（11px/500/TEXT_TERTIARY）+ 版本胶囊（`v{APP_VERSION}`），
  三者底边齐平，右侧三个圆钮不动。文案/版本一律取自 `paths.py` 的三个常量，
  `version_text()` 刻意在函数体内读模块全局 —— 测试靠 monkeypatch 换常量来证明没有硬编码。
  两个基线补偿量 `BRAND_EN_NUDGE` / `BRAND_CHIP_RISE` 是**光学校准**（不是几何纠偏），
  改字号/字重/字体族后必须重测。
- **胶囊配色**：字色 `#4A4A4F`、底色 `rgba(120,120,128,0.10)`。
  不能沿用 `TEXT_SECONDARY`：它在玻璃最暗角（202 灰）即使底色全透明也只有 4.06:1，
  永远够不到 4.3；加深一档后 226 面 6.13、202 面 4.95。
  版本胶囊与页脚 4 种状态**必须**同走 `chip_style()` / `version_chip_style()`，
  源码里不许再抄 `rgba(120,120,128,…)` 字面量（有剥注释后的结构守卫盯着）。
- **窗口位置**：主面板每次**新打开**（`isVisible()` 为假）都摆到主屏右下角，
  边距只有一个来源 `PANEL_EDGE_MARGIN = 10`；边界用「可用区域 left/top + width/height」
  的**排他**口径算，`QRect.right()` 是 `left+width-1`（最后一列像素），拿它减窗口宽会多 1px。
  - 面板**已经开着**时从托盘菜单点设备行 / 立即刷新 / 二次启动唤醒，**不重定位**
    （旧版会在可见状态下被拽回右下角，实测位移 574px）。
  - `_toggle_settings()` 切页前后**锁住下边缘**（用 `top()+height()` 而非 `frameGeometry().bottom()`，
    后者每切一次页往上漂 1px）。不锁的话：进设置页(664)再返回电量页(452) 时只缩高度、
    y 不回收，面板悬空 222px。同理，收起时停在设置页、下次打开也会悬空 —— 所以
    `show_panel()` 里「先归位页面、再定位、最后截屏 + show」这个顺序动不得。
- **拖动手柄（⋮⋮）**：圆心按控件中心反推（`4/10 × 8/12/16`），行距 **4/4**、列距 6，
  对称由构造保证；直径 `DOT_SIZE = 2.8` 用 `drawEllipse(QRectF)` 交抗锯齿磨圆。
  - 不能退回 2：硬边 2px 画出来是"小方块"，而用户要的是"6 个点"；
  - 也不能取 3.0：AA 边缘会把三行墨迹连成一片，等距断言会误红（2.4~2.8 是安全区间）；
  - 必须**以圆心为中心**建 `QRectF`：按左上角对齐整数格会变成 7..9/11..13/15..17，上下差 1px；
  - 版面数学只能有一处 `dot_centres()`，`paintEvent` 直接遍历（曾经两处各算一遍，改一处会"测试绿、界面错"）。
- **「全部已连接」用绿点而不是绿字**：`theme.OK` 当文字色在灰胶囊上只有 1.56 / 1.26，
  当底色更糟（绿字压绿底 1.59 / 1.29），数学上救不回来。改成灰胶囊 + `#12734A` 小圆点
  （灰底上 4.08 / 3.30，过 WCAG 1.4.11 图形元素 3:1），文字回到 `CHIP_TEXT`（6.13 / 4.95）。
- **电量口径**：以硬件原始值为准（如 83%），不对齐官方驱动的取整/平滑。
- **充电时的电量**：硬件只报 50% 占位符、无真实值 → 显示「充电中 + 闪电图标」，绝不显示 50。
- **配置三层**：内置 `app/config/devices.json` / 用户层 `%APPDATA%\BatteryGlass\devices.json` / `dist/*/_internal/config/devices.json`。
- **配置合并规则**：内置为底、用户层覆盖；内置设备在用户层的副本带 `based_on`，版本不一致时 `protocol` 段整体改用内置。
- **协议事实**：迈从充电位 = `byte6`（有线 `byte9`）bit4，`0x10`=充电中；HECATE 充电位 = `byte7` bit0，`0x01`=充电中。均正向，不取反。

## 未完成待办

- [x] **推送 GitHub**：已完成（2026-11-10），本地与 `origin/main` 0/0。
      过程：沙箱内前 3 次推送失败（schannel / 502 ×2）；用户本机首推被 `rejected (fetch first)`
      —— 远端多出 1 个本地没有的提交 `5041b9a Update LICENSE`（只把版权人字样
      「毅One」改成「Yi One」）。`git fetch origin main` 后确认分叉点 `b71c0bf` 之后
      **本地完全没有动过 LICENSE**，合并无冲突；于是用
      `git pull --no-rebase --no-edit origin main` 生成合并提交 `3be3f66`（**不用 rebase**，
      否则本文件里按哈希记录的 25 个提交会全部改写），再 `git push origin main` 成功：
      `5041b9a..3be3f66 main -> main`。GitHub commits 页面已核对，本地与远端 0/0。
- [x] **部署新版本**：用户已明确「**不需要部署到桌面，只打包到 `dist/`**」—— 不再复制到 `D:\桌面\APP\`，也不再需要「关一次再开一次自启」的迁移动作
- [ ] （可选）`dist/` 下的历史产物要不要清理，交由使用者决定

## 已知问题 / 待办（只记录，本轮不动手修）

1. **`DeviceRegistry.save_user_config()` 吞掉写盘异常**：`except Exception: log.error` 后只返回 `False`，磁盘瞬时失败时内存已改、磁盘没改，界面看着成功、重启后操作丢失（QA 用 monkeypatch 精确复现过）。下一步建议：重试一次 + 失败让上层感知 + 补测试。
2. **设置页「开机自启动」说明与实际路径脱节**：说明写死「写入当前用户的启动项，无需管理员权限」，没告诉用户真实注册表位置 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`、值名 `PowerHub`、值数据为当前 exe 命令行 + `--tray`。`autostart.open_task_manager_startup()` 已实现但**未接到界面**，适合单独做一轮。
3. **面板 `subtitle` 超宽会硬裁且无省略号**：该标签用了 `QSizePolicy.Ignored`（横向），未来文案一长就会静默截断。当前四种实际文案需要 47 / 70 / 155 / 140px，标签可用 284px（富余 ≥129px），**现在不触发**；加长时改用 `QFontMetrics.elidedText()` 或缩短文案。
4. **待复核：「副标题在设置页被裁成『正在扫』」** —— QA 报告，工程离屏实测**未复现**：注册系统字体后该文案需要 47px、标签可用 284px（纵向也余 3px）；且「正在扫描…」只在电量页构造时出现，进设置页即被 `_update_subtitle()` 覆盖成「设备清单、颜色、样式与启动项」。记为**待复核**，不当 bug 写死；等 QA 补截图与复现条件（窗口宽 / DPI / 哪个页面）。
5. **`preview/` 面板截图停留在 10-20**：未反映 v1.8.1~v1.9.0 的玻璃边缘 / 浅色设备色 / 头部品牌行改动。

## 接续要点

- 跑测试：直接 `./.venv/Scripts/python.exe -m pytest` 即可 —— `pytest.ini` 的 `addopts` 已带
  `--basetemp=.pytest-tmp`，绕开本机那个删不掉的 `pytest-current` 损坏 junction（不带 `--basetemp`
  曾导致 sessionfinish 崩、exit 1）；命令行显式 `--basetemp=...` 仍然优先（`pytest.ini` 已含 `-q`，别再重复加）
- 打包：`./.venv/Scripts/python.exe tools/build_exe.py`（单文件）/ `--onedir`（目录版）；
  **venv 重建后需补装 PyInstaller**；目标 exe 被占用时先退出软件
- 托盘相关测试：需要把 `SWAP_DELAY_MS`、`CREATE_INTERVAL_MS` 都归零，再用「空转事件循环」
  （`for _ in range(40): qapp.processEvents()`）把两轮定时器跑完，否则只建成第一枚
- 关键文件：`app/core/paths.py`（名称/版本）、`app/config/devices.json`（设备规则 + 配置版本）、
  `app/core/config.py`（三层合并 + 协议刷新）、`app/core/presence.py`（断连收起判定）、
  `app/core/protocols.py`（协议解析）、`app/core/model.py`（显示逻辑）、
  `app/ui/tray.py`（托盘图标绘制与槽位管理）、`app/ui/settings.py`（设置页）、`app/core/autostart.py`（自启 + 旧值迁移）
- 长期记忆：`.workbuddy/memory/MEMORY.md`；历史日志：`.workbuddy/memory/2026-1*.md`

## 推送故障排查记录（本轮已解决，留作以后参考）

> 2026-11-10 的 `rejected (fetch first)` 已按下面第 3 步解决：**先 fetch 看差异，再用 merge 而非 rebase**
> （本项目 `progress.md` 按提交哈希记录进展，rebase 会改写 25 个哈希、让文档全部对不上）。

在本机（不经沙箱代理）打开 **Git Bash / PowerShell / CMD**，逐条执行：

```bat
cd /d "E:\AI工作空间\电量中枢PowerHub"

:: 1) 先看状态：应当显示工作区干净、且提示领先 origin/main 若干个提交
git status
git log origin/main..HEAD --oneline

:: 2) 确认远端是改名后的仓库
git remote -v
::    期望： https://github.com/Yi-One1/PowerHub.git
::    若还是旧名，执行：
::    git remote set-url origin https://github.com/Yi-One1/PowerHub.git

:: 3) 推送
git push origin main
```

推送成功会打印 `main -> main`；再到 `https://github.com/Yi-One1/PowerHub` 刷新，
确认最新提交是 `0a71446`（或之后的新提交）。

**如果报 `non-fast-forward` / `rejected`**（远端有本地没有的提交）：
先 `git pull --rebase origin main`，解决冲突后再 `git push origin main`。**不要用 `--force`**。

**如果报认证失败**：GitHub 已不支持账号密码，改用 Personal Access Token（PAT）：
`Settings → Developer settings → Personal access tokens → Generate new token (classic)`，
勾选 `repo` 权限，然后在推送时用 `https://<用户名>:<PAT>@github.com/Yi-One1/PowerHub.git` 作为地址
（`git remote set-url origin ...`），或安装 GitHub CLI 后 `gh auth login`。

**如果仍然 502 / schannel 报错**（本机也走了代理）：
`git config --global --unset http.proxy`、`git config --global --unset https.proxy` 后重试；
或 `git -c http.proxy= push origin main` 临时绕过。

## 验收与收尾（2026-11-10）

- 用户已对 5 组改动给出**总验收通过**。
- **发布**：本次发布版本定为 **v1.9.0**（查证过 GitHub 上本仓库 0 个 Release，不撞车）。
  Release 标题、正文、SHA-256、操作步骤都写在 `docs/RELEASE_NOTES_v1.9.0.md`，由用户手动发布。
- **推送**：已完成，见上方「未完成待办」的推送条目；本轮用的是 merge（保留哈希）而非 rebase。
- **文档整理**：README 修掉重复的章节编号（原有两个「五」、两个「七」→ 顺排为七/八/九/十），
  测试文件表补上本轮新增的 5 个文件与「39 文件 / 479 项」总数，抬头加当前版本与产物信息，
  并注明 `preview/` 截图仍为 10-20 旧版；progress 补推送实况、手动教程与本节。
- **清理（已获用户授权）**：删除 6 项临时/缓存文件 —— `.pytest-tmp/`、`.pytest_cache/`、
  `app|tests|tools/__pycache__/`、`.tmp_commit_msg.txt`。实际执行时只有 `.pytest-tmp/`（190 KB）
  仍在，其余 5 项已被自动清理；删除后逐项核对均不存在，`git status` 干净。
  **明确保留**：`dist/` 八个 exe、`preview/` 12 张截图、`.venv/`、`.workbuddy/` 与全部源码。
  注：`.pytest-tmp/` 会在下次跑 pytest 时自动重建，属正常行为。
- **待用户手动完成**：按 `docs/RELEASE_NOTES_v1.9.0.md` 发布第一个 GitHub Release 并附上 exe。
  （代码推送已完成，不需要再做。）
- **待确认（远端带入）**：`5041b9a Update LICENSE` 把版权人字样改成「Yi One」，
  而 `README.md` 的许可证段落仍写「毅One」。这是用户在 GitHub 网页上做的修改，
  本次合并原样接受；两处是否统一、统一成哪个名字，由使用者决定。

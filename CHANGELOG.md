# Changelog（gx0404/gx_shell）

版本真源是本文件 `## X.Y.Z(日期|TBD)` 标题里的最大 SemVer；发版 tag 为
`gx-shell-vX.Y.Z`，获准发布前把 `(TBD)` 改为发布日期。主仓记录安装器、整合与发布变更；
组件源码、上游同步和自身测试记录在各 fork，遵守其 CHANGELOG 规则。每个版本段会原样成为
GitHub Release 说明，只写面向用户的变化；验收过程与内部记录见 README「本轮快照与当前待验证项」。

0.2.0 / 0.1.0 是改为协调仓之前的历史记录：其中 subtree、旧 Release 升级、指纹生成与耗时描述
不再是现行架构的操作流程或验收结果。保留它们用于解释既有行为，不表示旧资产仍可下载。

## 0.5.0(TBD)

本版把随包的 Ghostty GX 更新到 0.0.3 的开发修订、herdr 更新到 fork 的最新修订，并让 Windows 安装程序登记 Ghostty GX
的系统通知身份。组件为 Ghostty GX 0.0.3 的未发布修订（`ac064c31`，未打 tag）、herdr 0.9.3 加 fork 尚未发布的改动
（`fe54d5ff`）与 Oh My Zsh GX `53da420d`（只把依赖锁里的 herdr 换成同一修订，GX Zsh 本身不变）。**本段是发布前草稿**（标题为 `(TBD)`）：
手动验收（`publish=false`）已在 GitHub Actions 上完成与 0.4.1 相同的两平台构建与测试（含 Ghostty GX 的打包契约与核心测试、
Oh My Zsh GX 在真实 Zsh 与伪终端上的测试）：Windows 安装包在一次性的 Windows runner 上完成安装、使用（Ghostty GX 用随包的
Mesa 软件渲染打开 GX Zsh）、同版本重装、卸载与再次安装的冒烟，并核对了通知身份的注册表项与快捷方式；DEB 在 Ubuntu 24.04
的干净容器里完成安装、运行、重装、移除与清除；两平台产物的来源与散列核对无误。定版发布时须在发布 run 上重新通过。硬件 GPU 窗口、桌面输入、系统通知的实际显示与
旧版升级不在 CI 验证范围内，见「已知限制」。

### Ghostty GX 0.0.3（未发布修订）

- **跨进程拖动标签**（Windows）：把标签拖到另一个 Ghostty GX 进程（同一用户、权限与配置）的窗口里，其中的终端以远程
  窗格显示在目标窗口；原进程在后台继续持有终端与子进程，关闭原来的窗口也不会结束它们，目标退出或断开时原进程收回仍在
  运行的终端。只含远程窗格的标签可以拖回去，同时含本地与远程窗格的标签不能再跨进程移动（会提示原因）。
- **会话恢复**：设 `gx-session-restore = true`（默认关闭，改后需完全重启）后，普通启动恢复上次的窗口、标签、分屏比例、
  字号、手动标题与工作目录。不保存命令、参数、环境变量、终端输入或滚屏内容；自定义启动配置恢复前先确认，命令行指定了
  命令或工作目录时不恢复。
- **单实例**（Windows，`gx-single-instance`，默认开启）：已有 Ghostty GX 在运行时，再从「Ghostty GX」启动会在该实例里
  新开窗口，不再另起进程；「GX Zsh」快捷方式带 `-e`，仍启动独立进程，`--gx-single-instance=false` 也可以强制独立进程。
- **拖放**（Windows）：终端除文件外也接受拖入的文本与链接，路径按当前 shell 加引号；拖入内容按粘贴确认规则处理，不会
  自动回车。以管理员身份运行的窗口收不到普通程序的拖放，可以从它的主菜单「拖入管理员终端…」打开一个普通权限的接收
  窗口：拖到其中的内容先在提权窗口里预览，选「允许粘贴」后才粘贴。
- **系统通知与跳转列表**（Windows，仅安装版）：通知改为 Windows 系统通知，点击回到对应终端（程序已退出时只提示原终端
  不可用，不另开 shell）；任务栏跳转列表列出启动配置。GX Shell 安装程序为此登记 Ghostty GX 的通知身份，见「安装包与
  说明」。系统通知不可用时退回托盘气泡，被勿扰模式或用户关闭的通知不改用气泡。
- **无障碍**（Windows）：窗口、标签、终端窗格以及命令面板、菜单、设置、对话框向 UI Automation 公开名称、角色与操作。
- **拼音搜索**：模糊搜索支持全拼（`zhongwen` 找到「中文」，ü 用 v 输入）；Windows 的命令面板与设置里的主题、字体列表
  另支持拼音首字母（`zt` 找到「主题」）、多个词任意顺序与全角字母。
- **弹层输入框编辑**（Windows）：查找栏、命令面板、快捷键速查表与设置的搜索框支持撤销与重做（`Ctrl+Z` / `Ctrl+Y`）、
  按词移动与删除（`Ctrl+←/→`、`Ctrl+Backspace`、`Ctrl+Delete`，连续的汉字算一个词）、双击选词与三击全选。
- **快捷键编辑器与启动配置管理器**（Ubuntu）：可以编辑快捷键，新建、修改、改名、删除自定义启动配置并设为默认，改动只写
  `gui-settings.ghostty`；新增 `gx:move_split_to_tab`、`gx:move_split_to_window`，把分屏连同其终端移到新标签或新窗口，
  不重启 shell；第一个窗口按上次正常关闭时的大小与最大化状态打开。
- **行为调整**（Windows）：
  - 用 `set_tab_title` 或双击改的标签名不再被程序标题冲掉，改名留空即恢复显示程序标题；
  - `goto_tab:N` 改为从 1 计数（以前 `goto_tab:1` 跳到第 2 个），`move_tab` 改为真正移动当前标签；
  - 命令启动即失败时，在窗口底部显示不阻塞的「命令失败」提示，代替原来的模态对话框；正常退出不再提示；
  - 关闭分屏后焦点落到前一个分屏，切换分屏到头后回绕；命令面板空查询打开时不再自动预览主题；
  - 鼠标侧键报告为第 8、9 键，横向滚轮方向与 Linux 版一致；
  - 界面强调色改为从光标色与调色板中挑彩度、对比度合格的颜色（GX Mocha 下为蓝色）；
  - 关闭确认里的进程名不再带 `.exe`，只剩 `wslrelay.exe` 时视为空闲；启动配置不再列出 Docker Desktop、
    Rancher Desktop 的内部 WSL 发行版。
- **修复**（Windows）：Ctrl+点击链接后整个程序卡死；关闭确认等对话框被外部程序关闭后所有窗口点不动；RustDesk、ToDesk
  等同步剪贴板时复制粘贴偶尔没反应；「命令失败」提示一闪而过；超长标签标题、输入法文本与通知文字越界写内存；拖动嵌套
  分隔线跳动、切换标签时焦点来回跳、拖动中鼠标按键卡在按下状态；查找栏关闭后高亮残留、`scrollbar = never` 不生效；
  外部程序批量关闭时「关闭窗口？」弹两次；弹层粘贴超长单行文本卡顿（现截断到 4096 个 UTF-16 单元）。Ubuntu 上分屏迁移
  与会话恢复后退出不再断言失败。
- `ghostty +validate-config` 在 `language` 值不受支持或 `gui-settings.ghostty` 读不出来时报告配置错误并返回 1。
- Windows 安装包与 DEB 附带拼音数据 pinyin-data（MIT）与 Unicode License V3 的许可文本。

### herdr

- **Sessions 树与 Inspector**：新的统一 Sessions 树列出代理会话，Inspector 预览代理活动、提问、失败详情与会话信息；
  默认主题改为 Graphite，状态指示统一。保存的 dock 布局自动迁移到新的面板，终端布局保留。
- 代理概览可以在本机标记已读、未读；端点支持时，可以直接给空闲或待审阅的会话发提示（超时会保留草稿，不代表服务端已
  取消）。
- **移除**：不再提供 CLI 账号用量监控、账号绑定与 Accounts 面板；主机资源监控保留。
- 在 herdr 里启动或恢复的 Codex 会话改用窗格内的启动器；Windows 上可为 Codex 自带的更新程序提供私有的 `tar.exe`，不改
  用户或系统的 `PATH` 与 PowerShell 执行策略。
- 配置改为先写临时文件再替换，保留原有权限与符号链接目标；安装 Codex 集成前先校验其 TOML 与 JSON，只改 herdr 自己的
  hook 设置。
- 修复：Windows 上关闭窗格会结束其完整的子进程树，复用的 PID 不再被当作存活的子进程；输入、调整大小与响应队列有上限，
  卡住的写入或大量响应不再拖住后续输入；空闲或不完整的客户端握手不再长期占用资源；OSC 52 剪贴板、括号粘贴与宽字符
  重绘的边界情况不再丢状态；之前占用窗格的代理迟到的结果不再覆盖当前活动。
- 高频终端输出合并帧、减少重复合成，活动与进程发现改用共享快照，窗格多时更省 CPU。

### 安装包与说明

- Windows 安装程序在 HKCU 登记 Ghostty GX 的通知身份：`Software\Classes\AppUserModelId\gx0404.GhosttyGX` 与系统通知
  激活器 `Software\Classes\CLSID\{978ab84b-3cac-4593-95d5-2e04d68eed4f}`，都指向随包的 Ghostty GX，系统通知与任务栏跳转
  列表因此可用。卸载 GX Shell 时只在这些登记仍属于本次安装时才删除；它们已被别的安装目录占用时，安装程序拒绝继续，不会
  覆盖。

### 已知限制

- 真实硬件 GPU 下的窗口渲染没有验证，CI 只覆盖软件渲染路径（Mesa llvmpipe）。
- 桌面输入、回显与重绘没有验证，本版新增的拖放（含提权窗口的接收窗口）、跨进程拖动标签与 UI Automation 也没有在 CI
  中验证。
- Windows 系统通知是否真正弹出、点击后能否回到终端没有在 CI 中验证（Ghostty GX 自己的安装版实测里，早期有三次通知
  未显示，原因尚未定位）。
- 从旧版本升级（包括从 0.4.1 升级到本版）没有在 CI 中验证。
- 随包的 Ghostty GX 是未打 tag 的开发修订（`ac064c31`），它的 CHANGELOG 里 0.0.3 尚未定版，没有对应的 Ghostty GX
  正式 Release；herdr 同样是 fork 尚未发布的修订。
- 装好 GX Shell 之后再单独安装 Ghostty GX，两者的「Ghostty GX」快捷方式、`App Paths\ghostty.exe` 与通知身份仍会冲突；
  再次运行 GX Shell 安装程序会先卸载单独安装的 Ghostty GX（为所有用户安装的仍需管理员）。
- Windows 安装前卸载单独安装的 Ghostty GX 这一步没有在 CI 的安装冒烟中验证。
- herdr 的 Windows 原生通知默认关闭；一旦启用，它会在 `HKCU\Software\Classes` 下写入注册表项，卸载 GX Shell
  时不会清理。

## 0.4.1(2026-10-10)

本版把随包的 Ghostty GX 从 0.0.1 更新到 0.0.2，GX Zsh 与 herdr 不变。组件为 Ghostty GX 0.0.2（版本串
`1.3.2-gx.0.0.2`，`1be3d19f`）、herdr 0.9.3（`702cf257`）与 Oh My Zsh GX `5b55db6f`。发布前在 GitHub Actions 上完成
两平台构建与测试（含 Ghostty GX 的打包契约与核心测试、Oh My Zsh GX 在真实 Zsh 与伪终端上的测试）：Windows 安装包在
一次性的 Windows runner 上完成安装、使用（Ghostty GX 用随包的 Mesa 软件渲染打开 GX Zsh）、同版本重装、卸载与再次安装
的冒烟，DEB 在 Ubuntu 24.04 的干净容器里完成安装、运行（Ghostty GX 在 Xvfb 下用软件 OpenGL 运行 GX Zsh）、重装、
移除与清除，两平台产物的来源与散列核对无误后才发布。硬件 GPU 窗口、桌面输入与旧版升级没有验证，见「已知限制」。

### Ghostty GX 0.0.2

- **窗口材质透到整个终端区**（Windows）：在设置的「外观」页选云母、亚克力或云母 Alt
  （`gx-window-material = mica|acrylic|tabbed`）后，材质不再只透在标题栏：终端背景按 `background-opacity` 透出材质，
  文字、光标、选区与图片保持不透明。没设 `background-opacity` 时按材质取默认值（云母与云母 Alt 为 0.3，亚克力为
  0.75），显式设置优先（`background-opacity = 1` 即只在标题栏透出材质）。默认的纯色材质配 `background-opacity` 小于 1
  时，改为只有终端背景透明，文字不再随整个窗口变淡。需要 Windows 11 22H2（build 22621）及以上与硬件 OpenGL 驱动；
  更早的系统或使用随包 Mesa 软件渲染时保持 0.4.0 的行为，日志里记一行原因。
- **检测被占用的快捷键**（Windows）：组合键被其他程序注册成全局热键（例如 bilibili 客户端老板键的 `Ctrl+Shift+C`、
  AMD Software 性能指标叠加层的 `Ctrl+Shift+O`）或被当前输入法保留时，Ghostty GX 收不到它，以前也没有提示。现在受
  影响的快捷键在日志里记警告，快捷键速查表（`Ctrl+Shift+/`）给它们加警告标记并说明原因，右键菜单、主菜单与命令面板
  改为提示同一动作的其他可用按键；默认的复制、粘贴、查找或分屏键受影响时，每次运行在窗口底部提示一次替代方式。常见的
  冲突程序与解除办法见 Ghostty GX 的[快捷键冲突说明](https://github.com/gx0404/gx_ghostty/blob/1be3d19fc75f012317c09a7d55fa4be2380fb4a4/docs/GX_FEATURES.md#快捷键冲突)。
- **`Shift+Insert` 粘贴剪贴板**（Windows）：以前按下没有反应；现在与 `Ctrl+Insert` 复制配对，`Ctrl+Shift+C` /
  `Ctrl+Shift+V` 被其他程序占用时仍可用这两个键复制粘贴。
- **新图标**（Windows）：Ghostty GX 改用自己的图标（深色圆角方块加蓝色 `>_` 提示符），不再用 Ghostty 的幽灵图标，
  窗口标题栏、任务栏与资源管理器里都显示它；`ghostty.exe` 的文件属性显示产品名 Ghostty GX、发行者 gx0404 与非官方
  分支声明。Ubuntu 上仍是上游图标。
- **非官方分支声明**：Windows 的「关于」对话框与设置的「关于」页、Ubuntu 设置对话框的「关于」页写明 Ghostty GX 是
  Ghostty 的非官方分支，由 gx0404 维护，与 Ghostty 团队无关，未获其认可或背书（英文界面显示英文）。Ubuntu 主菜单的
  「关于 Ghostty GX」改为打开 Ghostty GX 自己的关于对话框，项目主页与问题反馈指向 gx0404/gx_ghostty；Windows「关于」
  对话框的第二个链接改为「上游 Ghostty」（ghostty.org）。
- **Ubuntu 上的界面修复**：Ubuntu 24.04 的 GTK 4.14 上启动时不再记录 `Theme parser error: style.css:…`；拖动分屏时，
  目标终端靠近指针的那一半重新显示蓝色高亮；只读提示的文字恢复浅橙色；`window-theme = ghostty` 时不再报
  `css parsing failed`，失焦窗口的标题栏会略微变暗。GTK 4.16–4.18 上拖放高亮也不再报 CSS 错误。
- 合入上游 Ghostty 到 `246f70287`：`+list-themes` 的主题预览可以用 `Ctrl+D` / `Ctrl+U` 翻页。

### 安装包与说明

- Windows 上「Ghostty GX」开始菜单与桌面快捷方式随之显示 Ghostty GX 的新图标，GX Shell 安装程序和「设置 > 应用」里的
  GX Shell 条目也改用它；「GX Zsh」快捷方式仍是 GX Zsh 的图标。
- DEB 的包说明（`apt show gx-shell` 可见）写明 Ghostty GX 是 Ghostty 的非官方分支，与 Ghostty 项目无关，也未获其认可
  或背书。
- 仓库 README 介绍 Ghostty GX 时同样写明：它是基于 Ghostty 的非官方分支，由 gx0404 维护，与 Ghostty 团队无关，未获其
  认可或背书。

### 已知限制

- 真实硬件 GPU 下的窗口渲染没有验证，CI 只覆盖软件渲染路径（Mesa llvmpipe）；本版窗口材质透到终端区只在硬件 OpenGL
  下生效，同样没有验证。
- 桌面输入、回显与重绘没有验证。
- 从旧版本升级（包括从 0.4.0 升级到本版）没有在 CI 中验证。
- 装好 GX Shell 之后再单独安装 Ghostty GX，两者的「Ghostty GX」快捷方式与 `App Paths\ghostty.exe` 仍会冲突；
  再次运行 GX Shell 安装程序会先卸载单独安装的 Ghostty GX（为所有用户安装的仍需管理员）。
- Windows 安装前卸载单独安装的 Ghostty GX 这一步没有在 CI 的安装冒烟中验证。
- herdr 的 Windows 原生通知默认关闭；一旦启用，它会在 `HKCU\Software\Classes` 下写入注册表项，卸载 GX Shell
  时不会清理。

## 0.4.0(2026-10-10)

本版用 Ghostty GX 取代 WezTerm GX，成为 GX Shell 的终端。Ghostty GX 是 gx0404/gx_ghostty 维护的 Ghostty fork：
Windows 上是原生应用，Ubuntu 上是 GTK 4 应用。GX Zsh（Oh My Zsh GX）与 herdr 照旧随包提供。DEB 从本版起只支持
Ubuntu 24.04 及更新版本。组件为 Ghostty GX 0.0.1（版本串 `1.3.2-gx.0.0.1`，`5525f8bc`）、herdr 0.9.3（`702cf257`）与
Oh My Zsh GX `5b55db6f`。发布前在 GitHub Actions 上完成两平台构建与测试（含 Ghostty GX 的打包契约与核心测试、
Oh My Zsh GX 在真实 Zsh 与伪终端上的测试）：Windows 安装包在一次性的 Windows runner 上完成安装、使用（Ghostty GX
用随包的 Mesa 软件渲染打开 GX Zsh）、同版本重装、卸载与再次安装的冒烟，DEB 在 Ubuntu 24.04 的干净容器里完成安装、
运行（Ghostty GX 在 Xvfb 下用软件 OpenGL 运行 GX Zsh）、重装、移除与清除，两平台产物的来源与散列核对无误后才发布。
硬件 GPU 窗口、桌面输入与旧版升级没有验证，见「已知限制」。

### 升级须知（破坏性变化）

- GX Shell 不再包含 WezTerm GX。它的壁纸、插件、自定义键位和 `Ctrl+V` 粘贴图片（`clipboard_image_paste`）
  随之移除，Ghostty GX 没有对应功能；它的设置面板与 Shell 选择器由 Ghostty GX 自己的设置界面和启动配置代替
  （见下文），在 WezTerm GX 里做的设置不会迁移。Ghostty GX 使用自己的配置文件：Windows 为
  `%LOCALAPPDATA%\ghostty\config.ghostty`，Ubuntu 为 `~/.config/ghostty/config.ghostty`。
- WezTerm 的配置与数据（`~/.config/wezterm`，Windows 为 `%USERPROFILE%\.config\wezterm`，以及它的插件、备份与日志
  目录）原样保留，GX Shell 不读取、不迁移，也不删除；在 WezTerm 里设置的字体、配色与键位不会带到 Ghostty GX。
- Windows 上从旧版升级时，安装程序删除旧版自带的 WezTerm GX 程序（安装目录下的 `wezterm`），以及仍指向它的
  「WezTerm GX」开始菜单与桌面快捷方式和 `App Paths\wezterm-gx.exe` 登记。单独安装的 WezTerm GX 不受影响，
  安装程序也不再把它当作旧组件先行卸载；卸载 GX Shell 时同样保留它创建的快捷方式与登记。
- Windows 安装程序像对待单独安装的 Oh My Zsh GX、Herdr GX 一样，安装前先卸载单独安装的 Ghostty GX（gx_ghostty
  自己的安装包；交互安装时先询问），之后「Ghostty GX」快捷方式与 `App Paths\ghostty.exe` 由 GX Shell 提供，两者
  共用的配置 `%LOCALAPPDATA%\ghostty\` 原样保留。它的程序文件被占用时安装程序拒绝继续，不会结束进程。为所有用户
  安装的 Ghostty GX 只有管理员能卸载：安装程序不是以管理员身份运行时会拒绝继续，请先在「设置 > 应用」里卸载它。
- Ubuntu 上从旧版升级时，dpkg 删除旧版的 `/usr/lib/wezterm-gx`、`/usr/share/wezterm-gx` 与命令 `wezterm-gx`、
  `wezterm-gx-gui`；Ghostty GX 的命令是 `ghostty-gx`，在其中打开 GX Zsh 用 `ghostty-gx -e gx-zsh`。
- Windows 开始菜单改为「Ghostty GX」与「GX Zsh」两个快捷方式，可选的桌面快捷方式改为「Ghostty GX」；
  `ghostty` 经 `App Paths` 指向随包的 Ghostty GX。
- DEB 不再支持 Ubuntu 20.04 与 22.04：Ghostty GX 需要 GTK 4.14 与 libadwaita 1.5，只能装在 Ubuntu 24.04 及更新版本上。
- 升级前先运行 `herdr server stop`，再关闭 WezTerm GX、Ghostty GX 和 GX Zsh。安装程序遇到被占用的文件会拒绝
  继续，但不会替你结束进程。

### Ghostty GX

- Windows 上「Ghostty GX」默认打开 GX Zsh（找不到时依次改用 PowerShell 7、Windows PowerShell、命令提示符）；
  「GX Zsh」快捷方式总在第一个标签页运行 GX Zsh，即使配置了别的默认 Shell。
- 有自己的设置界面：`Ctrl+,` 或主菜单的「设置…」打开（Windows 上是窗口内的浮层，Ubuntu 上是对话框），分语言、
  外观（主题与窗口材质，主题移动即预览）、字体、交互、Shell 与关于六页；改动保存在 `gui-settings.ghostty`，不改你的
  `config.ghostty`。
- 界面语言默认中文，可以在运行中切换为英文：在设置或主菜单的「语言」里选，或在配置里写 `language = en`（改回
  `zh-CN` 即中文）；菜单、命令面板等不用重启就换成新语言。
- 启动配置：Windows 上标签栏「+」旁的下拉按钮（或右键「+」）与主菜单，Ubuntu 上新建标签页按钮的下拉菜单，列出
  本机找到的 GX Zsh、herdr、PowerShell、WSL 发行版、登录 Shell 等，点一下就在新标签页或新窗口里启动；
  `gx-launch-profile` 可以加自己的条目。
- 主菜单（`Ctrl+Shift+M`）、命令面板与可搜索的快捷键速查表（`Ctrl+Shift+/`）；两个平台的命令面板都列出「设置」
  「键盘快捷键」「主菜单」三项，名称随界面语言显示。窗口里唯一的标签页运行 herdr 时隐藏标签栏（`gx-herdr-app-mode`，
  默认开启）；终端里只剩空闲的 Shell 时，关闭标签页或窗口不再确认。
- 渲染需要 OpenGL 4.3。Windows 上显卡驱动达不到时（例如虚拟机或远程桌面），Ghostty GX 改用随包的 Mesa
  软件渲染；设置环境变量 `GHOSTTY_GX_OPENGL=software` 可以强制使用它。
- 字体：随包的字体文件不变，仍是 JetBrains Mono Nerd Font（常规、半粗、粗体及各自的斜体）与 Noto Sans CJK
  （常规、粗体）共 8 个，与 0.3.0 逐字节相同。终端默认用 JetBrainsMono Nerd Font（12 号），中日韩文字用
  Noto Sans CJK SC。Windows 安装程序只登记随包实际带的字体，旧版登记过而新版不再随带的字体，在升级时先注销再删除。

### 组件更新

- **Oh My Zsh GX**：
  - 提示符改为 Powerlevel10k 的 Lean 风格：各段不再有背景色块，在 Ghostty GX 的默认主题下目录不再显示成看不见
    文字的蓝色色块；两行布局、各段颜色与 `╭─`/`╰─❯` 框线不变。
  - 终端集成改以 Ghostty GX 为目标：在 Ghostty GX 或 herdr 窗格里才接管 OSC 7 工作目录上报（改为
    `file://localhost/…`）；Ghostty GX 自带的 zsh 集成已在位时让给它，不再重复上报 OSC 7 与 OSC 133。
- **herdr**：仍是 0.9.3，另合入上游 v0.9.3 之后的修复，包括：
  - Windows 关机或注销时先保存会话，窗格不再因进程被系统结束而从布局里丢失（herdrdev/herdr#5057）。
  - Windows 上经启动器（如 Scoop shim）或以 32 位程序运行的 Shell，herdr 记下的是 Shell 实际所在的目录，不再退回
    启动器的目录（herdrdev/herdr#5062）。
  - Windows 键盘布局里作为重音键（死键）的符号键，与 Ctrl 组合的快捷键可以识别（herdrdev/herdr#5021）。
  - 托管插件可以从 GitHub 更新（herdrdev/herdr#4245）；agent 挂起或转入后台时保留其会话（herdrdev/herdr#4964）；
    server 收到挂断信号时继续运行，并记录停止原因（herdrdev/herdr#4965）。
  - 非拉丁键盘布局下的 Ctrl 组合键按基础键处理（herdrdev/herdr#4961）。
  - **行为变化**：Windows 上以管理员身份运行的 herdr server 默认只接受管理员终端里的客户端（herdrdev/herdr#4779），
    0.3.0 里普通终端也能连接并控制它（herdrdev/herdr#4777）。需要时在配置里写 `[server]` 段的
    `allow_unelevated_clients = true`，或在管理员终端用 `herdr server --allow-unelevated-clients` 启动 server；
    普通权限的 server 仍接受同一账户的普通与管理员终端。已在运行的 server 要停止并重启后才按新规则。
  - GX 另修复：在 Ghostty GX 里启动 herdr 时，窗格不再继承 Ghostty 的 shell 集成变量，窗格里的 Shell 不会再加载
    一次 Ghostty 的 shell 集成。

### 打包与发版

- 来源锁 `components.lock.json` 的组件改为 `herdr`、`ohmyzsh` 与 `gx_ghostty`（分支 `gx_ghostty`）；Ghostty GX
  以 gx_ghostty 产出的 schema 3 stage 进入组装，安装包清单升级为 schema 3。
- 安装布局：Windows 的 Ghostty GX 在安装目录下的 `ghostty`，DEB 在 `/usr/lib/ghostty-gx`。
- DEB 的依赖（Depends）取自每次构建的 Ghostty GX stage 由 dpkg-shlibdeps 得出的结果，并推荐安装
  `librsvg2-common`（GTK 显示 SVG 图标所需的加载器）。
- DEB 冒烟只在干净的 Ubuntu 24.04 容器里运行：安装、GX Zsh、herdr、Ghostty GX 在 Xvfb 下以软件 OpenGL 运行
  GX Zsh、重装、移除与清除。Windows 冒烟在一次性 runner 上用随包 Mesa 验证 Ghostty GX 启动 GX Zsh。

### 已知限制

- 真实硬件 GPU 下的窗口渲染没有验证，CI 只覆盖软件渲染路径（Mesa llvmpipe）。
- 桌面输入、回显与重绘没有验证。
- 从旧版本升级没有在 CI 中验证。
- 装好 GX Shell 之后再单独安装 Ghostty GX，两者的「Ghostty GX」快捷方式与 `App Paths\ghostty.exe` 仍会冲突；
  再次运行 GX Shell 安装程序会先卸载单独安装的 Ghostty GX（为所有用户安装的仍需管理员）。
- Windows 安装前卸载单独安装的 Ghostty GX 这一步没有在 CI 的安装冒烟中验证。
- herdr 的 Windows 原生通知默认关闭；一旦启用，它会在 `HKCU\Software\Classes` 下写入注册表项，卸载 GX Shell
  时不会清理。

## 0.3.0(2026-10-02)

本版把 GX Shell 改为一个协调仓加三个 fork 的架构：herdr、Oh My Zsh GX 与 WezTerm GX 在各自的 fork 里开发和测试，
GX Shell 锁定它们默认分支上的确定修订来构建安装包。组件升级为 herdr 0.9.3、WezTerm GX `48aff481`、
Oh My Zsh GX `e7de531b`。发布前在 GitHub Actions 上完成两平台构建与测试：Windows 安装包在一次性的 Windows
runner 上完成安装、使用、同版本重装、卸载与再次安装的冒烟，DEB 在 Ubuntu 20.04 与 24.04 的干净容器里完成
安装、运行、重装与移除，两平台产物的来源与散列核对无误后才发布。硬件 GPU 窗口、桌面输入与旧版升级没有验证，
见「已知限制」。

### 升级须知（破坏性变化）

- 从 GX Shell 0.1.0 或 0.2.0 原地升级到本版**没有经过验证**，旧版本的 Release 资产已经撤下。
- 安装布局与用户数据保护不变：安装位置和目录结构与之前相同，卸载只删除 GX Shell 自己安装的内容，
  保留配置与用户数据；同版本重装已验证会保留配置。
- 升级前先运行 `herdr server stop`，再关闭所有 WezTerm GX 窗口和 GX Zsh。安装程序遇到被占用的文件会拒绝
  继续，但不会替你结束进程。
- 静默安装或卸载遇到被占用的文件时直接拒绝并写入日志，不再弹出对话框卡住。

### 组件更新

- **herdr 0.9.3**：同步上游 v0.9.3，包括 Windows 原生可操作通知（herdrdev/herdr#4803）、同一用户的 Windows
  客户端可以跨提权连接（herdrdev/herdr#4777）、Windows 本地 server 权限失败时给出解释（herdrdev/herdr#4769）、
  worktree 分组修复（herdrdev/herdr#4770、herdrdev/herdr#4772）、保留以 Escape 开头的按键绑定
  （herdrdev/herdr#4759）、恢复 codex 空闲检测并通过 hook 报告 codex 轮次完成（herdrdev/herdr#4756）。
  GX 另修复：在 kitty 终端里写入 OSC 52 剪贴板之前先发送重置序列。
- **WezTerm GX**：
  - `Ctrl+V` 可以粘贴剪贴板里的图片，新增配置 `clipboard_image_paste`：默认 `"inline"`，把图片作为内联图片
    插入窗格；设为 `"path"` 时把图片存成 PNG 写到临时目录（`%TEMP%`），再把文件路径作为文本粘贴；设为
    `"none"` 时只粘贴文本。读取剪贴板图片目前只在 Windows 上实现。
  - Windows 上的 WGL（OpenGL）上下文关闭 vsync，帧率改由 `max_fps` 节流。
  - 性能：大批量输出按子批应用并释放终端锁；配色预览节流；设置浮层确认去抖，并给段落扫描设预算；
    壁纸浮层预览改到后台生成，并给缓存设上限。
- **Oh My Zsh GX**：随包的 herdr 依赖锁升到 0.9.3。

### 打包与发版

- GX Shell 改为协调仓：`components.lock.json` 锁定三个 fork 默认分支上的完整修订；各组件先在独立 checkout
  里生成 stage，再由根仓 assemble → build → verify。安装包清单升级为 schema 2，记录组件来源、构建
  provenance 与锁 digest；缺文件、散列或来源不符都会拒绝打包。
- 根仓只保留一个 workflow `release.yml`，有三种用法：推送 tag 发版；手动运行并设 `publish=false` 做完整构建
  验收；手动传入 `source_run_id` 复验已完成构建的原始产物（不重新编译，也不发布）。
- CI 下载 Inno Setup 7.1 并校验散列后再用它编译 Windows 安装包。
- 修复 Windows runner 的临时目录是 8.3 短名时根单元测试失败的问题。
- 本地构建的源码、中间产物与日志都限定在根仓 `.local/`；本地产物名带 `-local`，不能发布。

### 已知限制

- 真实硬件 GPU 下的窗口渲染没有验证，CI 只覆盖软件渲染路径（WebGpu software fallback）。
- 桌面输入、回显与重绘没有验证。
- 从旧版本升级没有验证。
- herdr 的 Windows 原生通知默认关闭；一旦启用，它会在 `HKCU\Software\Classes` 下写入注册表项，卸载 GX Shell
  时不会清理。

## 0.2.0(2026-09-30)

本版集中修复 0.1.0 在 Windows 上的体验问题：在 GX Zsh 里运行 herdr 时提示符损坏、右键
「关闭窗格」失灵、启动和日常操作偏慢、`irm … | iex` 无法运行、Ctrl+C 中断不了程序；同时
让 Windows 上的路径、`/tmp`、ssh 与键位习惯和 Linux 一致，并新增默认 Shell 设置。文中耗时
均为 Windows 上的实测。

### 升级须知（破坏性变化）

- 升级前先运行 `herdr server stop`（窗口关掉后 herdr 的后台 server 仍在运行），再关闭所有
  WezTerm GX 窗口和 GX Zsh。Windows 安装程序遇到被占用的文件会拒绝继续，但不会替你结束进程。
- GX Zsh 的盘符路径由 `/cygdrive/c/...` 改为 `/c/...`（与 Git Bash 相同），`/cygdrive`
  不再存在：写在 `~/.zshrc.local`、脚本和历史命令里的 `/cygdrive/c/...` 要改成 `/c/...`。
  补全等缓存会在第一次启动时按新路径自动重建。
- GX Zsh 的 `/tmp` 现在就是 Windows 用户临时目录（`%TEMP%`）；ssh、scp 改用
  `%USERPROFILE%\.ssh` 里的配置、密钥与 known_hosts，与 Windows 自带的 OpenSSH、Git Bash
  共用同一份。
- WezTerm GX 键位：
  - Windows 改用与 Linux 相同的 `Ctrl+Shift` 方案，裸 `Alt` 组合全部留给 shell：原来的
    `Alt+键` 改为 `Ctrl+Shift+键`，`Ctrl+Alt+键` 改为 `Ctrl+Alt+Shift+键`（如分屏
    `Ctrl+Shift+\`、切换标签 `Ctrl+Shift+[` / `]`）；页面滚动改为 `Shift+PageUp` /
    `Shift+PageDown`，不带修饰的 PageUp / PageDown 交给 less、vim 等程序。
  - 两个平台：关闭窗格改为 `Ctrl+Shift+W`（原为 `Alt+W`），关闭标签 `Ctrl+Alt+Shift+W`，
    窗格里有程序在运行时先确认；窗口缩小 / 放大改为 `Leader -` / `Leader =`（Leader 是 `Ctrl+Shift+Space`），
    `Ctrl+Shift+-`（即 `Ctrl+_`，shell 的撤销）交还给 shell，`Ctrl+Shift+=` 放大字号。
  - Windows 新增 `Ctrl+PageUp` / `Ctrl+PageDown` 切换标签、`Ctrl+=` / `Ctrl+-` / `Ctrl+0`
    缩放字号、`Leader 1..9` 直达标签；截图与 AI 图片粘贴（`Alt+Shift+S` / `Alt+Shift+V`）
    只在 Linux 上绑定。
- 开始菜单「GX Zsh」改为在 WezTerm GX 窗口里打开（控制台窗口显示不了提示符里的 Nerd Font
  图标）。
- WezTerm 配置由只迁移 `launch.lua` 改为按文件升级：与 WezTerm GX 0.3.0 或 GX Shell 0.1.0
  发布内容相同的文件先备份到 `%APPDATA%\wezterm-gx\backups\<时间戳>\wezterm-config\`（Ubuntu
  为 `~/.local/share/wezterm-gx/backups/...`）再换成新版；新增文件补上，自己删掉的发布文件
  （如删除的壁纸）不再补回，`gui-settings.json` 不动。改过的文件保留，与它有 require 关系、
  本次也更新的文件一起留在旧版。每个文件的处理结果与原因写在
  `%APPDATA%\wezterm-gx\config-migration.log`（Ubuntu 为
  `~/.local/share/wezterm-gx/config-migration.log`）。
- 0.1.0 生成的 herdr 配置（`%LOCALAPPDATA%\ohmyzsh-gx\profile\herdr\config.toml`，Ubuntu 为
  `~/.config/ohmyzsh-gx/profile/herdr/config.toml`）在第一次运行 `gx-zsh` 或 `herdr` 时由 GX
  接管（改过其中 `default_shell` 或 `shell_mode` 的除外）：开头加一行 `# gx-shell: manages ...`
  标记，此后 GX 只改 `[terminal]` 里这两项；删掉这行标记，文件就完全由你管理。

### 修复

- 在 GX Zsh 里运行 herdr 或再启动一层 `gx-zsh` 时，不再报
  `(anon):source:27: no such file or directory: …/powerlevel10k/internal/p10k.zsh`，提示符也
  不再退化成 `GX%`。原因是 MSYS2 把 `ZSH_CUSTOM` 等路径转成 `C:/…` 交给原生的 herdr.exe，
  GX Zsh 又把它当成相对当前目录的路径。现在 `gx-zsh` 与 `herdr` 入口不再沿用上层 GX 进程
  导出的内部变量，GX Zsh 也会把盘符（`C:/…`）和 UNC 形式的值转回 POSIX 路径；混进来的
  Windows 路径碎片不再让补全缓存反复重建。
- WezTerm GX 右键菜单的「关闭窗格」「关闭标签页」恢复正常，确认框不再一闪而过、导致窗格关不掉。
  原因是菜单在按下时就执行，同一次点击的抬起落到刚弹出的确认框上，被当成了「否」。标签页右键
  菜单的左移、右移、关闭作用于点中的那个标签页，而不是当前标签页；点菜单外关闭菜单时，这次点击
  的拖动和抬起不再传给窗格。
- 修复 Ctrl+C 中断不了程序：根因是 0.1.0 私有运行时里 msys2-runtime 3.6.10-5 的回归
  （msys2/msys2-runtime#372）——运行过 winget、应用商店版 pwsh / python 等应用执行别名后
  Shell 永久挂住，Ctrl+C 也救不回来；运行时已升级到修复后的 3.6.10-6。此外 `gx-zsh` 与
  `wezterm-gx` 启动器会清除从父进程继承的「忽略 Ctrl+C」标志；Windows 的 `wezterm-gx-cli`
  收到 Ctrl+C / Ctrl+Break 时不再先于子进程退出，并返回子进程的退出码；herdr 转发 Ctrl+字母
  时总带对应的控制字符，外层终端只报普通字母时 MSYS2 程序也能被中断。
- 在 GX Zsh 里 `cd` 之后，WezTerm GX 与 herdr 新开的标签和分屏沿用当前目录（按
  `file:///C:/…` 上报）；GX Zsh 不再改写 Windows 原生程序的 `TEMP` / `TMP`。
- herdr 监控页的「账号」能找到 Codex / Claude 桌面应用自带的 CLI，以及注册表 PATH、npm、
  pnpm、Bun、Volta、Scoop、WinGet 等目录里的 CLI，不再误报「此主机未检测到已安装的 agent
  CLI」；空白页按「刷新」会立即重新扫描。
- WezTerm GX：`Ctrl+Shift+[` `]` `\` `0` `9` 在 Windows 与 X11 上按得到了；设置页保存后深色
  主题不再变回浅色，写文件或重载失败时显示错误，`gui-settings.json` 读取失败时不再被覆盖；
  关闭默认键位时，命令面板和快捷键速查仍显示自己绑定的键。
- Windows 上空闲的 Shell 窗格（GX Zsh、PowerShell、cmd 等）关闭时不再弹确认，运行着 herdr
  等程序时仍会确认；字体回退补上 Microsoft YaHei 与 Segoe UI Emoji；GX Zsh 不再加载在
  Windows 上无效的 `sudo` 插件，`SHELL` 指向正在运行的 zsh。
- 用户目录含 `'`、花括号或带空格的 UNC 路径时，GX Zsh 的路径转换不再出错。

### 性能

- GX Zsh：启动器把全部路径放进一次 `cygpath` 调用转换，`gx-zsh -f -c exit` 约 580 → 123 ms，
  `herdr --version` 571 → 38 ms；交互式热启动 2.65 → 1.87 s（启动时少起外部进程，fzf、zoxide、
  dircolors 的初始化结果缓存并预编译）；每次 `cd` 约 200 → 62 ms（zoxide 改在后台记录）；新
  profile 第一次启动不再连续两次重建补全缓存。
- GX Zsh 在 Windows 上输入不再卡顿：灰色历史建议（zsh-autosuggestions）原来每按一个键就 fork 一个
  子 shell（MSYS2 上每次约 30 ms），现改为进程内同步查历史，每击键约 0.8 ms；回车到下一个提示符的
  中位数约 195 → 33 ms。
- WezTerm GX：配置求值首次 269 → 84 ms、重载 256 → 7 ms（探测 Shell 只检查文件是否存在，
  不再调用 `where.exe`；WSL 发行版列表每个进程只取一次；缺插件时不再在求值中同步 git clone）；
  没有窗口级覆盖的窗口重载时不再把整份配置再执行一遍，标签栏显隐只重排终端区域；状态栏的
  前台进程探测每个窗口至多每 2 秒一次、电池信息缓存 60 秒；光标闪烁缓动改为 Constant、
  `animation_fps` 降到 10，空闲窗口不再持续重绘；关闭上游 WezTerm 的更新检查。
- 内置 16 张壁纸等比缩到不超过 1920×1080，总大小 19.4 MB → 6.3 MB，GPU 纹理图集由 4096²
  （5K 壁纸时 8192²）降到 2048²。
- herdr：Windows 上 15 个窗格时 agent 检测的 server CPU 约降到原来的 1/5～1/12；server 先
  开始监听客户端连接再创建启动工作区，冷启动到提示符 167 → 149 ms；命名管道缓冲由 512 B 提到
  1 MiB，客户端到 server 的大帧吞吐约提升 10 倍；监控页的 GPU 查询至多每 2 秒一次、显卡列表
  缓存 60 秒，无人查看时后台线程不再每 100 ms 唤醒一次。

### 新功能

- 默认 Shell：WezTerm GX 设置页（`Leader s`）新增「Shell」分区；主菜单和标签栏右键菜单的
  「默认 Shell…」、标签栏 `+` 按钮右键列表末项「设为默认 Shell…」都直达该分区，新按键动作
  `ShowDefaultShellSettings` 可自行绑定。可选本机找到的 GX Zsh、PowerShell 7（含应用商店版）、
  Windows PowerShell 5.1、cmd、Git Bash、MSYS2 UCRT64、Nushell 与各 WSL 发行版（Ubuntu 上为
  GX Zsh、Zsh、Bash），选择保存在配置目录的 `gui-settings.json`。默认仍是 GX Zsh；所选 Shell
  不可用时依次回退到 GX Zsh、PowerShell 7、Windows PowerShell 5.1（Ubuntu 为 GX Zsh、Zsh）。
- 安装包内的 herdr 跟随默认 Shell：之后新开的 herdr 窗格使用同一个 Shell，运行中的 herdr
  server 自动重载配置。herdr 只接受一个可执行文件，所以选 WSL 时进入默认发行版（不能指定
  发行版），选 MSYS2 UCRT64 时得到的是 MSYS 环境的 bash，系统通知会如实说明；herdr 配置由你
  自己管理时不做修改。
- PowerShell 桥接：GX Zsh 新增 `gx-pwsh`，以及转交 PowerShell 执行的 `iex` /
  `Invoke-Expression`、`irm` / `iwr` / `Invoke-RestMethod` / `Invoke-WebRequest`，
  `irm https://…/install.ps1 | iex` 这类安装命令可以直接运行（脚本原样交给 PowerShell，以
  `param()` 开头的安装脚本也能用；装好的命令当场可用，不必重开终端）。输入未安装的 PowerShell
  命令或常见 Linux 工具时只提示 `gx-pwsh` 写法或 winget 包名，不会自动执行；另补 `open`、
  `xdg-open`、`pbcopy`、`pbpaste`、`vi`。
- 私有运行时新增 diffutils、patch、unzip、zip、tree、bc、procps-ng（`top`、`pgrep`、`pkill`、
  `watch`、`free`）、vim、rsync、jq，并附对应源码与许可文本。

### 打包与发版

- 私有运行时的 msys2-runtime 锁定为 3.6.10-6；Windows 安装程序升级时删除 0.1.0 留下的
  msys2-runtime 3.6.10-5 包记录（私有运行时里 pacman 的本地数据库），文件被占用时的提示改为
  提醒关闭 WezTerm GX、GX Zsh 并运行 `herdr server stop`。
- herdr 的 zsh 补全 `_herdr` 在打包时用包内 herdr 按中文生成，两个安装包都必须带上它。
- herdr 的许可收集允许没有自带许可文本、且 license 表达式与 herdr 一致的 workspace 成员
  （如上游新增的 `crates/ghostty-vt`）沿用 herdr 根目录的 `LICENSE`，清单记录来源。
- 新增本机构建模式 `GX_LOCAL_BUILD_ROOT`：herdr 可以在本机构建并记为 `builder=local`；只有
  GitHub Actions 构建的 stage 能进入可发布的安装包，本地 stage 要 `assemble --allow-dirty`，
  产物名带 `-local`，永远不能发布。构建指定的 Rust 工具链缺失时直接报错，不再自动安装。
- 发版流程新增 Ubuntu 上用真实 Zsh 与伪终端（PTY）跑的 Oh My Zsh 测试、WezTerm 的 config /
  mux / wezterm-gui 单元测试（cargo nextest）和 Windows 上的原生启动器测试，发布前都必须
  通过；Windows 冒烟新增从 GX Shell 0.1.0 原地升级的完整验证（herdr 与 WezTerm 配置迁移、
  旧包记录清理），逐个运行新增的命令行工具，检查以 `param()` 开头的脚本经 `iex` 运行，并要求
  运行 winget 别名后正常返回；两个平台都在打包的 WezTerm 上运行 `tests/pure_fn_test.lua`。
- WezTerm 启动器用来认出「未改动的已发布配置文件」的指纹表 `released.rs` 由
  `wezterm/scripts/gx_config_fingerprints.py` 只从 git 里的发布提交生成，单元测试逐项复算；
  每次发版后要把新版本登记进去（见 README「发版」）。

## 0.1.0(2026-09-29)

- herdr、Oh My Zsh GX、WezTerm GX 三个 fork 以完整历史并入本仓（`git subtree`），
  一次发版产出 Windows x64 安装 EXE 与 Ubuntu 20.04/24.04 amd64 DEB，不再分别
  下载安装三个仓库的包。
- Windows 安装包按用户安装到 `%LOCALAPPDATA%\Programs\GXShell`，无需管理员（仅 x64）：
  提供开始菜单「WezTerm GX」「GX Zsh」，把 `bin\`（`gx-zsh`、`herdr`）加入用户
  PATH，按用户注册 8 款字体并通知正在运行的程序；安装前自动卸载单独安装的旧版
  WezTerm GX / Oh My Zsh GX / Herdr GX，并把旧的「WezTerm (gx)」快捷方式改指向
  GX Shell；升级沿用原安装目录；卸载只撤销自己的 PATH 与字体，保留用户配置。安装
  向导随系统语言显示中文或英文。
- DEB 包名 `gx-shell`，提供 `gx-zsh`、`herdr`、`wezterm-gx`、`wezterm-gx-gui` 与
  桌面入口，自动替换旧的 `wezterm-gx`、`ohmyzsh-gx`、`herdr-gx` 包；维护脚本不修改
  用户 HOME；同一提交重复构建得到逐字节相同的包。
- WezTerm 默认进入包内 GX Zsh，启动菜单最前面新增「GX Zsh」「herdr」；WezTerm GX
  0.3.0 生成且未修改的配置在首次启动时自动迁移到新默认值，原 `launch.lua` 留有备份。
- herdr 从同一提交的源码编译并写入包身份，二进制内关闭自更新与渠道切换。
- 两个安装包都附带 Noto Sans CJK 字体的 SIL OFL 1.1 许可文本。
- 单一发版流程 `.github/workflows/release.yml`：发布前确认 CHANGELOG 已写日期、提交在
  `main` 上、同名 Release 与 tag 不冲突；两平台构建、组装、在一次性 runner /
  Ubuntu 20.04、24.04 容器中完成安装—使用—原地升级—卸载（Windows 再装再卸，DEB 再
  purge）冒烟，含替换旧版 WezTerm GX 并迁移其配置；全部通过才创建 GitHub Release，
  并附对应源码包与 `SHA256SUMS`。

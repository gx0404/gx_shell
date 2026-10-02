# Changelog（gx0404/gx_shell）

版本真源是本文件 `## X.Y.Z(日期|TBD)` 标题里的最大 SemVer；发版 tag 为
`gx-shell-vX.Y.Z`，获准发布前把 `(TBD)` 改为发布日期。主仓记录安装器、整合与发布变更；
组件源码、上游同步和自身测试记录在各 fork，遵守其 CHANGELOG 规则。每个版本段会原样成为
GitHub Release 说明，只写面向用户的变化；验收过程与内部记录见 README「本轮快照与当前待验证项」。

0.2.0 / 0.1.0 是改为协调仓之前的历史记录：其中 subtree、旧 Release 升级、指纹生成与耗时描述
不再是现行架构的操作流程或验收结果。保留它们用于解释既有行为，不表示旧资产仍可下载。

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

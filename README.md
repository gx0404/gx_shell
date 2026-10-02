# GX Shell

一个协调仓锁定三个独立 fork，一次发版产出 Windows EXE 与 Ubuntu DEB，安装后提供：

- **WezTerm GX**：GPU 加速终端（fork 自 [wezterm](https://github.com/wezterm/wezterm)），带配置、插件、壁纸和字体。
- **GX Zsh**：独立 profile 的 Oh My Zsh + powerlevel10k（fork 自 [ohmyzsh](https://github.com/ohmyzsh/ohmyzsh)），
  Windows 上自带私有 MSYS2 与打过中文路径补丁的 Zsh 5.9.2。
- **herdr**：面向 AI 编码代理的终端工作区管理器（fork 自 [herdr](https://github.com/herdrdev/herdr)）。

WezTerm 默认直接进入 GX Zsh（可以在设置里换成 PowerShell、WSL 等，见「默认 Shell」），herdr 可以在 GX Zsh 里运行，
也可以从 WezTerm 启动菜单打开。

**迁移中**：源码、上游同步和组件测试归各 fork，主仓锁定各自既有默认分支的完整 SHA，负责安装器、整合与发布。
真实 `components.lock.json` 已锁定三个默认分支并通过远端可达性校验，三个 fork 的远端 `gx` 分支已删除；
最终锁的两平台整包 CI（run `36998777427`，publish=false）已通过，但尚未发布，硬件 GPU 等项仍未验证，
见「来源锁与更新」「验收与 PENDING」。
旧 Release 资产已退出下载/验收输入；既有使用与配置保护说明不代表本轮真实产品验收或旧版升级已通过。

## 安装

新架构产物完成验收并发布后，从 [Releases](https://github.com/gx0404/gx_shell/releases) 下载；
迁移期间不要将旧版本说明理解为仍有可下载资产。包格式与安装契约保持如下：

| 平台 | 文件 | 安装方式 |
|---|---|---|
| Windows 10 1809+ x64（不支持 ARM64） | `GX-Shell-<版本>-Setup-x64.exe` | 双击运行。按用户安装到 `%LOCALAPPDATA%\Programs\GXShell`，不需要管理员。安装包未签名，SmartScreen 提示时选「更多信息 → 仍要运行」。 |
| Ubuntu 20.04 / 24.04 amd64 | `gx-shell_<版本>_amd64.deb` | `sudo apt install ./gx-shell_<版本>_amd64.deb` |

`SHA256SUMS` 可校验全部文件；`*-sources.tar.xz` 是再分发组件（MSYS2、Zsh 等）的对应源码，普通使用不需要下载。

装好后：

- Windows：开始菜单有「WezTerm GX」「GX Zsh」（「GX Zsh」在 WezTerm GX 窗口里打开）；新开的终端里可以直接运行
  `gx-zsh`、`herdr`。
- Ubuntu：应用菜单有「WezTerm GX」；命令行有 `gx-zsh`、`herdr`、`wezterm-gx`（CLI）、`wezterm-gx-gui`。

用户数据的位置（卸载时都会保留）：

| 内容 | Windows | Ubuntu |
|---|---|---|
| WezTerm 配置 | `%USERPROFILE%\.config\wezterm` | `~/.config/wezterm` |
| WezTerm 设置页的选择（语言、默认 Shell、壁纸等） | 配置目录里的 `gui-settings.json` | 同左 |
| WezTerm 配置升级的备份与日志 | `%APPDATA%\wezterm-gx\` 下的 `backups\` 与 `config-migration.log` | `~/.local/share/wezterm-gx/` 下同名 |
| WezTerm 插件 | `%APPDATA%\wezterm\plugins` | `~/.local/share/wezterm/plugins` |
| GX Zsh profile（`.zshrc`、历史、缓存） | `%LOCALAPPDATA%\ohmyzsh-gx\profile` | `~/.config/ohmyzsh-gx/profile` |
| GX Zsh 里的 herdr 配置 | `<profile>\herdr\config.toml` | `<profile>/herdr/config.toml` |

## 历史差异：GX Shell 0.1.0 → 0.2.0

以下保留迁移前的行为变化，供已有安装用户核对；旧 Release 资产不再作为验收输入，
**这些说明不代表外置架构已验证从 0.1.0 升级**。安装布局与用户数据保护要求继续保留。
其中路径、`/tmp`、ssh、PowerShell 与命令行工具几条只涉及 Windows：

- **先停掉正在运行的程序**：先运行 `herdr server stop`（窗口关掉后 herdr 的后台 server 仍在运行），再关闭所有
  WezTerm GX 窗口和 GX Zsh。Windows 安装程序遇到被占用的文件会拒绝继续，但不会替你结束进程。
- **盘符路径改为 `/c/...`**：GX Zsh 与 Git Bash 一样把 `C:\` 写作 `/c/`，`/cygdrive/c/...` 不再存在。写在
  `~/.zshrc.local`、脚本或历史命令里的 `/cygdrive/c/...` 要改成 `/c/...`（或 `C:/...`）；补全等缓存会在第一次启动时
  自动重建。
- **`/tmp`** 现在就是 Windows 用户临时目录（`%TEMP%`），与 Git Bash 相同。
- **ssh**：ssh、scp 读写 `%USERPROFILE%\.ssh` 里的配置、密钥和 known_hosts，与 Windows 自带的 OpenSSH、Git Bash 共用一份。
- **WezTerm GX 键位**（完整列表按 `Leader k` 查看；Leader 是 `Ctrl+Shift+Space`，先按它再按后面的键）：
  - Windows 改用与 Linux 相同的 `Ctrl+Shift` 方案，裸 `Alt` 组合（`Alt+.`、`Alt+b`、`Alt+f` 等）全部留给 shell：原来的
    `Alt+键` 改为 `Ctrl+Shift+键`，`Ctrl+Alt+键` 改为 `Ctrl+Alt+Shift+键`，例如分屏 `Ctrl+Shift+\`、切换标签
    `Ctrl+Shift+[` / `]`、新窗口 `Ctrl+Shift+N`；
  - 关闭窗格改为 `Ctrl+Shift+W`（两个平台原来都是 `Alt+W`），关闭标签 `Ctrl+Alt+Shift+W`；窗格里有程序在运行时两者都先确认，
    Windows 上空闲的 Shell（GX Zsh、PowerShell、cmd 等）直接关闭；
  - 页面滚动改为 `Shift+PageUp` / `Shift+PageDown`，不带修饰的 PageUp / PageDown 交给 less、vim 等程序；
  - 窗口缩小 / 放大改为 `Leader -` / `Leader =`，`Ctrl+Shift+-`（即 `Ctrl+_`，shell 的撤销）交还给 shell，
    `Ctrl+Shift+=` 放大字号；
  - Windows 新增 `Ctrl+PageUp` / `Ctrl+PageDown` 切换标签、`Ctrl+=` / `Ctrl+-` / `Ctrl+0` 缩放字号、`Leader 1..9` 直达标签。
- **配置文件**：WezTerm 配置按文件升级，没改过的文件会换成新版，规则、备份与日志的位置见下一节的「WezTerm 配置」。
- **herdr 配置**：0.1.0 生成的 `<profile>\herdr\config.toml` 在第一次运行 `gx-zsh` 或 `herdr` 时由 GX 接管：开头加一行
  `# gx-shell: manages [terminal] default_shell and shell_mode; ...` 标记，同目录多一个 `.gx-config-adopted`。此后 GX
  只在需要时改 `[terminal]` 里的 `default_shell` 与 `shell_mode`（跟随默认 Shell 设置，或原路径失效时），其余内容不动。
  删掉标记行，这个文件就完全归你，GX 不再修改也不再接管；自己改过这两项的文件从一开始就不会被接管。
- **默认 Shell**：新增设置，不改就仍是 GX Zsh。在设置的「Shell」分区（`Leader s`，或菜单里的「默认 Shell…」）换成
  PowerShell、WSL 等之后，herdr 新开的窗格也跟着换；但 herdr 只接受一个可执行文件，选 WSL 发行版时 herdr 只能进入
  WSL 的默认发行版，选 MSYS2 UCRT64 时 herdr 得到的是 MSYS 环境的 bash。详见下文「默认 Shell」。
- **PowerShell 安装命令**：`irm https://…/install.ps1 | iex` 在 GX Zsh 里可以直接运行。`irm`、`iwr`、`iex`（以及
  `Invoke-RestMethod`、`Invoke-WebRequest`、`Invoke-Expression`）会交给 PowerShell 执行，以 `param()` 开头的安装脚本
  也能用，装好的命令当场可用、不必重开终端。其他 PowerShell 代码用 `gx-pwsh '<代码>'` 或 `… | gx-pwsh` 运行；默认用
  PATH 上的 `pwsh.exe`，没有时用 `powershell.exe`，环境变量 `GX_POWERSHELL` 可以指定别的。输入没安装的命令时（如
  `Get-ChildItem` 这类 PowerShell 命令，或 `rg`、`fd`），只提示 `gx-pwsh` 写法或 winget 包名，不会自动执行。
- **新增命令行工具**：diffutils（`diff`、`cmp` 等）、patch、unzip、zip、tree、bc、procps-ng（`top`、`pgrep`、`pkill`、
  `watch`、`free`）、vim（`vi` 也打开 vim）、rsync、jq；另有 `open` / `xdg-open`（用默认程序打开）和 `pbcopy` /
  `pbpaste`（读写剪贴板）。仍然没有 man、htop、rg、fd、tmux，终端复用可以用 herdr。
- **开始菜单「GX Zsh」**：现在在 WezTerm GX 窗口里打开，提示符里的 Nerd Font 图标能正常显示。

## 从单独安装的旧版本迁移

- **旧安装包会被替换**：Windows 安装程序会先卸载按用户安装的 WezTerm GX / Oh My Zsh GX / Herdr GX
  （为所有用户安装的 WezTerm GX 需要你在「设置 → 应用」里手动卸载）；Ubuntu 上 `gx-shell` 会自动替换
  `wezterm-gx`、`ohmyzsh-gx`、`herdr-gx` 包。
- **WezTerm 配置**：新版第一次启动时按文件升级。与 WezTerm GX 0.3.0 或 GX Shell 0.1.0 发布内容相同的文件（文本
  不计 CRLF 与 LF 的差别）先备份到 `%APPDATA%\wezterm-gx\backups\<时间戳>\wezterm-config\`（Ubuntu 为
  `~/.local/share/wezterm-gx/backups/...`）再换新；新增文件补上（`wezterm.lua` 不是 GX 发布的原样时只补新代码用到的），
  删掉的已发布文件（如在壁纸浮层删除的壁纸）不补回，新代码用到时除外；`gui-settings.json` 不动。改过的文件、只读
  文件和符号链接保留，与它有 require 关系、本次也更新的文件一起留在旧版；只改了各版本都没变过的文件（如
  `wezterm.lua` 里的日期格式）不影响其他文件升级。每个文件的结果和原因写在 `%APPDATA%\wezterm-gx\config-migration.log`
  （Ubuntu 为 `~/.local/share/wezterm-gx/config-migration.log`），保留的文件会注明新版在安装目录里的位置。想用新默认值，
  参照安装目录里的 `wezterm\resources\dotfiles\wezterm-config`（Ubuntu 为 `/usr/share/wezterm-gx/dotfiles/wezterm-config`）
  手工合并：把改过的文件换成新版，下次启动会自动补齐留在旧版的文件；合并后仍保留自己改动的文件还算改过，留在旧版的
  文件要从同一目录手工复制。也可以备份后删除 `~/.config/wezterm`（Windows 为 `%USERPROFILE%\.config\wezterm`；只留下
  `gui-settings.json` 也行），再启动一次 WezTerm GX 重新生成。
- **旧 Oh My Zsh GX 用户**：旧 profile 里由 Oh My Zsh GX 生成的 `herdr/config.toml` 记着旧安装目录下的 zsh 路径，
  第一次启动 `gx-zsh` 或 `herdr` 时会自动改到新位置，并由 GX 接管（见上一节「herdr 配置」）。自己改过其中
  `default_shell` 或 `shell_mode` 的文件不会被改动：需要的话手动改路径，或者删掉它，下次启动会按新位置重新生成。
- **herdr 的配置与会话**：通过 `herdr` 命令启动时读取上表中 GX Zsh profile 里的 `herdr/config.toml`，而不是
  单独安装 herdr 时的 `%APPDATA%\herdr` / `~/.config/herdr`，需要的话把旧配置复制过去；会话名默认为
  `ohmyzsh-gx`，要回到单独安装时的默认会话，用 `HERDR_SESSION=default herdr`。
- **Windows on ARM**：WezTerm GX 0.3.0 可以借 x64 仿真装在 ARM64 上；GX Shell 与 Oh My Zsh GX 一样只支持 x64 Windows，
  因为内置的 MSYS2 运行时没有在 ARM64 上验证过。
- 升级方式是安装新版本的安装包（Windows 沿用原来的安装目录）；`herdr update` 在包内被禁用。

## 默认 Shell

WezTerm GX 新开的标签默认进入 GX Zsh，也可以换成本机的其他 Shell：Windows 上有 PowerShell 7（含应用商店版）、
Windows PowerShell 5.1、cmd、Git Bash、MSYS2 UCRT64、Nushell 和各个 WSL 发行版，Ubuntu 上有系统的 Zsh 与 Bash。
列表只含本机找到的 Shell（只检查文件是否存在；WSL 发行版列表每个 WezTerm 进程只向 `wsl.exe` 查一次）。
在设置的「Shell」分区里选：

- 设置用 `Leader s` 打开（Leader 是 `Ctrl+Shift+Space`，先按它再按 `s`），再切到「Shell」分区；
- 主菜单（标签栏右端的 `☰`，或 `Leader m`）和标签栏空白处右键菜单里的「默认 Shell…」、标签栏 `+` 按钮右键列表的
  最后一项「设为默认 Shell…」都直接打开这个分区，命令面板（`F2`）里也能搜到「默认 Shell…」；
- 想用自己的按键打开它，在 WezTerm 配置里绑定 `wezterm.action.ShowDefaultShellSettings`。

选中后新开的标签立即使用它，`+` 按钮右键列表里它会标上「（默认）」。选择保存在配置目录的 `gui-settings.json`
（`default_shell` 键，选回 GX Zsh 即删除这个键），不改动你的 Lua 配置；所选 Shell 以后不可用时，依次回退到 GX Zsh、
PowerShell 7、Windows PowerShell 5.1（Ubuntu 为 GX Zsh、Zsh）。新装的 WSL 发行版一般要重启 WezTerm GX 才会出现在
列表里。改过 `config/launch.lua` 的话，升级时它会保留旧版，「Shell」分区会提示没有可选的 Shell，按上文「WezTerm 配置」
的办法合并新版即可。

安装包里的 herdr 会跟着改：之后 herdr 新开的窗格使用同一个 Shell（已开的窗格不变，正在运行的 herdr server 会自动
重载配置），系统通知会说明 herdr 实际用的是什么。herdr 只接受一个可执行文件，所以有两处与 WezTerm 不完全一致：

- 选 WSL 发行版时，herdr 进入 WSL 的默认发行版，不能指定发行版；
- 选 MSYS2 UCRT64 时，herdr 得到的是 MSYS 环境的 bash，不是 UCRT64 环境。

Ubuntu 上选系统 Zsh 时，herdr 改用 GX Zsh（herdr 里的 zsh 本来也会加载 GX 配置）。herdr 的配置由你自己管理时
（`config.toml` 里没有 GX 的标记行，见上文「herdr 配置」；或 `HERDR_CONFIG_PATH` 指向别的文件），herdr 不会被修改，
通知里会说明。

## 已知问题

- Windows 上没有 GPU 的虚拟机（例如云主机）里，WezTerm GX 默认的 OpenGL 渲染建不出窗口，启动后没有任何反应
  （WezTerm GX 0.3.0 也是如此）。在 `%USERPROFILE%\.config\wezterm\config\appearance.lua` 开头的 `front_end` 表里把
  `windows = 'OpenGL'` 改成 `windows = 'WebGpu'`，再在它返回的表里加一行 `webgpu_force_fallback_adapter = true,`，
  改用系统自带的 CPU 渲染即可（改过的文件以后升级时会保留，见上文「WezTerm 配置」）；发版冒烟在无 GPU 的 Windows
  runner 上就是用这两项设置启动 WezTerm GX 的。

## 仓库结构

主仓是协调仓，不再通过 subtree 或根 `.gitmodules` 管理三个 fork 的源码：

| 仓库 | 负责范围 | 整合方式 |
|---|---|---|
| `gx0404/gx_shell` | 安装布局、安装器、来源锁、stage 整合、冒烟与发布 | 根 coordinator commit + 锁文件 |
| `gx0404/herdr` | herdr 源码、上游同步、自身测试与包身份 | 锁定默认分支的完整 SHA，由 shell 构建链消费 |
| `gx0404/ohmyzsh` | GX Zsh 配置、启动器、Zsh/MSYS2、依赖再分发与自身测试 | 外部 source root 生成 shell stage |
| `gx0404/wezterm` | WezTerm 源码、配置、启动器、配置指纹与自身测试 | 外部 checkout 递归取其子模块，生成 WezTerm stage |

```text
components.lock.json          三个 fork 的 repository / branch / revision
packaging/                    Windows Inno Setup 7.1、Debian 模板与维护脚本
scripts/gx_shell_sources.py   来源锁校验、固定 SHA checkout、显式更新来源
scripts/gx_shell_local_build.ps1   Windows 只读资源与工具链规划
scripts/gx_shell_stage_shell.sh    Oh My Zsh/herdr source root 的 stage 编排入口
scripts/gx_shell_package.py   assemble / build / verify / version / notes
scripts/gx_shell_smoke_*      两平台安装生命周期与隔离硬件 GPU 冒烟入口
.github/workflows/release.yml 唯一的整包发布流程
```

本地/复验目录契约固定为：`.local/sources/<component>/` 保存锁定 SHA 的独立 checkout，
`.local/build/<run>/` 保存编译工作目录、stage、assembly、dist、cache、日志、provenance 和回执；
`.local/` 全目录已由根 `.gitignore` 忽略。根仓的受版本控制工作区不含组件目录；CI 可按 Git 身份契约把组件
checkout 放在 `RUNNER_TEMP`。已核对的**仓外迁移副本**是历史材料：herdr、ohmyzsh 的本地 `gx` 已在
`git switch --detach gx` 后用 `git branch -d gx` 删除（HEAD、文件与 stash 未变），wezterm
不含独立 Git 元数据；不删除这些副本，也不能把它们或继承的父仓 HEAD 当作正式组件来源。WezTerm 的 C 依赖
只从其独立 checkout 的 `.gitmodules` 递归初始化。fork 的开发规则、路由器、测试及 workflow 留在各 fork，
根仓不复制它们。

**组件历史边界**：迁移核对时，远端 `herdr`、`ohmyzsh`、`wezterm` 的 `gx` 相对各自默认分支分别有
2/3/5 个独有提交，其中 herdr 两侧已分叉。三个 fork 的远端 `refs/heads/gx` 已由 gx0404 于 2026-10-02
08:40–08:42 UTC 删除，删除前分别为 herdr `1a6b9d4d13d1b547fe0e21197baeb2ac4e27bef0`、ohmyzsh
`dde872a53c8bdd45f0d4dded809d6dbd67d0196f`、wezterm `4b219eea6a46eab9de03444612b90766d1d0d806`，
均已确认是对应默认分支的祖先。这是提前删除：删除时整包与 GPU 验收尚未完成。不重写 fork 历史，
不删除仓外迁移副本；文档更新不执行组件合并或分支删除。

**根协调仓历史重建（独立 PENDING）**：仍保留未来以**无父初始化 commit** 建立根协调仓新历史、
不继承旧 subtree 合并历史的迁移计划。它与组件默认分支切换及 `gx` 删除是独立事项，未被取消，也不在
本轮执行范围；须在代码与两平台验收完成后另行授权、单独执行和验证，不能据此宣称当前 HEAD 已完成重建。

### 来源锁与更新

`components.lock.json` 的 `schema` 为 `1`；`components` 恰有 `herdr`、`ohmyzsh`、`wezterm`，
每项恰有 `repository`（`gx0404/<name>`）、`branch` 和 `revision`（完整 40 位 commit SHA）。
`branch` 改为各自既有默认分支，不再统一使用 `gx`：

| repository | branch |
|---|---|
| `gx0404/herdr` | `feature/gx_herdr` |
| `gx0404/ohmyzsh` | `feature/gx_ohmyzsh` |
| `gx0404/wezterm` | `feature/gx_wezterm` |

根 coordinator SHA 与三组件 SHA 分别记录，不能再拿一个根提交代表四个仓库。锁 digest 是文件**原始字节**
的 SHA-256；换行或 JSON 格式变化也会改变它，不在锁内写自引用 digest。

真实 `components.lock.json` 已写入，不需初始化占位锁或猜测 SHA。默认分支合并与锁对齐后已重新校验，
最终锁的 revision、digest 与远端校验结果见「本轮快照与当前待验证项」；此前针对 `gx` 的校验只是历史证据，
来源校验通过也不代表真实产品已通过验收。

在上述对齐完成后，从根仓运行以下 Git Bash 示例；本地与复验 checkout 固定在根仓 `.local/sources/<component>`，不使用
仓外路径：

```bash
python scripts/gx_shell_sources.py check --lock components.lock.json
python scripts/gx_shell_sources.py check --lock components.lock.json --require-remote
python scripts/gx_shell_sources.py checkout --lock components.lock.json --output .local/sources
```

- `check` 离线验结构并输出 digest；`--require-remote` 另验各 SHA 是真实 commit，且从对应远端默认分支可达。
- `checkout` 按锁定 SHA 建立独立、detached、干净的 checkout，不追随任何浮动分支头；WezTerm 递归取子模块。
  已有目录必须身份、SHA 与干净状态均匹配，否则拒绝覆盖。不能把开发中的 fork 工作区当作可清空的缓存。
- 完整 checkout 已在本地时可加 `--offline` 复用；缺 clone 或递归子模块会失败，不偷偷联网。

更新来源时，先在相应 fork 完成改动、上游同步与自身测试，推送获准的默认分支提交，再由根仓审阅来源锁。
只有明确要将**三个组件都更新到各自当前默认分支头**，且已有完整锁时，才运行：

```bash
python scripts/gx_shell_sources.py update --lock components.lock.json
git diff -- components.lock.json
python scripts/gx_shell_sources.py check --lock components.lock.json --require-remote
```

`update` 不负责初始化缺失的锁，也不应进入日常构建或发布 job。只更新单个组件时应审阅并修改该项
`revision`，不要误用更新全部组件的命令；之后重新校验并验收受影响的 stage/整包。上游 remote 与同步策略
按各 fork 的 `AGENTS.md` 执行，根仓不再执行 subtree pull。

### 安装布局与安全

外置源码不改变安装契约：Windows 保持 `{app}\bin`、`lib`、`runtime\msys64`、`share\ohmyzsh-gx`、
`fonts` 和 `{app}\wezterm\`；deb 保持 `/usr/lib/{ohmyzsh-gx,wezterm-gx}` 与
`/usr/share/{ohmyzsh-gx,wezterm-gx}`。布局变更须同步两个 fork 的启动器、WezTerm fork 中的
`dotfiles/wezterm-config/utils/gx-shell.lua`、根 packager、安装生命周期与硬件 GPU 冒烟入口，并更新来源锁。

Windows 安装器仅管理 HKCU 中自己的 PATH、字体和 `Software\GX Shell`；文件被占用时拒绝继续，
不杀进程。deb 维护脚本不写用户 HOME。真实安装/卸载仅在一次性 runner 或容器执行；开发机不运行安装
生命周期冒烟，只验证隔离的完整 payload 的硬件 GPU/窗口，具体边界见「验收与 PENDING」。

## Windows 本地构建

### 本地构建与资源规划

`scripts/gx_shell_local_build.ps1` 是**只读 CPU/内存资源规划器**，支持 Windows PowerShell 5.1 与 PowerShell 7；
`-Format Json` 输出报告，`-Format Environment` 只打印拟议的进程环境赋值，默认 `Both` 同时打印两者。
它不创建目录、不修改环境、不下载/安装依赖，也不运行编译器或链接器。

`scripts/gx_shell_build.py` 是实际的本地串行构建入口：它按 `components.lock.json` checkout 独立 fork，
先运行规划器，再按共享 jobs 预算生成 WezTerm/Oh My Zsh stage，最后调用根 `assemble/build`。它只生成
`-local` 不可发布产物；本地/复验工作目录必须是当前根仓 `.local/build/<run>`，源码必须是
`.local/sources/<component>`，不得使用仓外路径；`--plan` 只做来源和资源检查，不编译。

以下 PowerShell 示例使用根仓内的 checkout；工具链版本需与锁定 fork 的构建要求一致：

```powershell
$lock = Get-Content -Raw ./components.lock.json | ConvertFrom-Json
$repo = (Get-Location).Path
$local = Join-Path $repo '.local'
$sources = Join-Path $local 'sources'
$run = Join-Path $local ('build/' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$roots = @{}
$revisions = @{}
foreach ($name in 'herdr', 'ohmyzsh', 'wezterm') {
    $roots[$name] = Join-Path $sources $name
    $revisions[$name] = $lock.components.$name.revision
}
./scripts/gx_shell_local_build.ps1 -Format Json -BuildRoot $run `
    -RepoRoot $repo -Component wezterm `
    -ComponentRoots $roots -ComponentRevisions $revisions `
    -Toolchain '1.96.1-x86_64-pc-windows-msvc'
```

- 规划器根据物理/逻辑核心、总内存和可用内存保留系统余量；`GX_CPU_JOBS`、`GX_ZSH_JOBS`、
  `GX_MEMORY_BUDGET_GB` 可下调预算，越过安全上限会拒绝。Cargo、CMake、原生编译与 Zsh 共用预算，
  **同一时间只构建一个组件**，不能把 jobs 乘以三个；内存预算是估算，不是操作系统强制限额。
- `GX_BUILD_ROOT` 或 `-BuildRoot` 必须解析到当前根仓 `.local/build/<run>` 下的新目录；每组件的缓存、日志和工作目录
  按组件名、完整 SHA、工具链指纹和 target 隔离。每轮使用新的输出目录，不通过删除用户源码来复用目录。
- 本地显式传入根仓内的 `ComponentRoots` 和锁中的 `ComponentRevisions`；CI job 可按 Git 身份契约使用
  `RUNNER_TEMP` 的独立组件 checkout。父仓 HEAD、脏 checkout 或 SHA 不匹配不算通过。`ready=true` 仅表示所选源码、
  Rust/MSVC 与资源规划条件满足，**不等于构建或发布通过**。
- `-UseSccache` / `-UseLld` 只在工具已安装且验证后选择；默认不启用，不自动安装。仍须单独激活 MSVC/SDK
  环境。环境建议中的离线模式要求事先准备依赖缓存，规划器不会填充缓存；不要用 `Invoke-Expression` 盲执行输出。
- **GPU 只用于之后的 WezTerm runtime smoke**，不参与编译资源预算；检测到 GPU、规划器成功或软件渲染成功，
  都不能代替真实 GPU/窗口渲染验收。

### stage 与整包

真实构建仍需 Python 3.14（含 zstd 支持）、fork 要求的 Rust MSVC 工具链、VS Build Tools/Windows SDK、
PowerShell 7、.NET SDK 8、Strawberry Perl 及 Inno Setup 7.1；Linux 构建与冒烟所需的 Docker 和容器工具链
由 Ubuntu GitHub runner 提供，不在本机安装 Docker/WSL。具体版本以锁定 fork 的构建配置与 release workflow
为准，缺工具先报 PENDING，不伪造 runner 或自动安装来绕过检查。

WezTerm 在 CI 中通过独立 checkout 的 `scripts/gx_package.py` 及其 `--stage-dir` 入口产出 stage；
根 `scripts/gx_shell_stage_shell.sh` 接受对应的 Oh My Zsh/herdr source roots、锁和 jobs，生成带 provenance
的 shell stage。CI 的 source roots 可以位于 `RUNNER_TEMP`；本地/复验的 source roots 只能位于
`.local/sources/<component>`，两条 stage 链的输出、assembly、dist、cache 和日志只能位于
`.local/build/<run>/`。`gx_shell_build.py` 将两条 stage 链串行编排，再交给根 packager；producer 的完整编译
和一次性 runner/container 验收以 CI 实测为准，当前结果见「本轮快照与当前待验证项」；不能用夹具 stage 代替真实构建。

本地 herdr 构建必须使用位于根仓 `.local/build/<run>` 下的 `GX_LOCAL_BUILD_ROOT`，记录 `builder=local`，
环境不得含 `GH_TOKEN` / `GITHUB_TOKEN` 或伪造的 CI 身份。本地 stage 只允许 `assemble --allow-dirty`；产物名带
`-local`，永远不可发布，不能通过改 manifest 标记将它提升为正式包。

若另行需要本地构建诊断，可使用以下 Windows 入口，`--plan` 仅验证资源和来源。本轮产品验收按下节路线
执行，本机仅做隔离完整 payload 的硬件 GPU/窗口验证，不以本地编译替代 runner 构建。命令从根仓运行，且所有
本地/复验路径都在 `.local/` 内；`<run>` 每轮必须替换为新的运行目录名：

```powershell
python scripts/gx_shell_build.py --platform windows --components-lock components.lock.json `
  --work-root .local/build/<run> --sources-root .local/sources --jobs 8 --memory-budget-gb 12 --plan
python scripts/gx_shell_build.py --platform windows --components-lock components.lock.json `
  --work-root .local/build/<run> --sources-root .local/sources --jobs 8 --memory-budget-gb 12
```

也可以在已有两个 stage 时直接组装；stage、assembly 和输出目录必须是根仓 `.local/build/<run>` 下的新目录：

```bash
python scripts/gx_shell_package.py assemble --platform windows --allow-dirty \
  --components-lock components.lock.json --wezterm-stage .local/build/<run>/wezterm-stage \
  --ohmyzsh-stage .local/build/<run>/ohmyzsh-stage --output .local/build/<run>/assembly
python scripts/gx_shell_package.py build --assembly .local/build/<run>/assembly --output .local/build/<run>/dist
```

根 packager 离线消费 stage、锁和根安装器材料，不再从组件源码补图标、指纹或许可。schema 2 manifest
保留 coordinator、三个组件来源、原始锁快照/digest、stage 回执与完整清单；文件缺失、内容变动、
来源错配或冲突必须失败。`verify` 需要同一根 SHA 和锁构建的**两个平台**产物，不能对单个本地 Windows 包
声称发布校验通过；本地产物即使凑齐两平台，也只在 `--allow-dirty` 下验收，仍不可发布。

## 发版

迁移后的发布必须遵循以下门禁；下列是门禁要求本身，本轮 CI 实测结果见「本轮快照与当前待验证项」，
**发布尚未执行**：

1. 完成真实锁的默认分支对齐、外部 source adapter 和 stage 接口。根 `prepare` 校验锁 schema、
   digest、仓库/分支/revision、commit 存在与对应默认分支可达性，并检查根 CHANGELOG 版本；缺任一项即阻断。
2. 根与组件分别 checkout，组件放 `RUNNER_TEMP`；WezTerm 递归取自身子模块。build/test jobs 使用外部
   source roots；package jobs 只消费 stage artifacts 与根打包代码，不需要根组件目录或旧指纹 commit fetch。
3. 保留 Windows/Linux 构建、根及组件单测、真实 Zsh/PTY、原生启动器、WezTerm config/mux/GUI nextest、
   Inno Setup 7.1 编译。完整安装生命周期走 GitHub-hosted Windows，以及 Ubuntu GitHub runner 上的
   Docker Ubuntu 20.04/24.04 容器；后两者验证同一个 DEB。保留安装—使用—卸载、同版本重装和配置保护检查，
   硬件 GPU/窗口另按下节隔离验收。**无旧 Release 升级覆盖**：不下载旧安装包，不把 warning skip 或
   同版本重装写成旧版升级通过；旧版替换/跨版本升级未验证。
4. 两平台产物均完成后，由根 `verify` 核对共同 coordinator SHA、锁/digest、组件来源与文件散列，
   生成 `SHA256SUMS`。仅发布门禁认可的干净 CI stage 可以发布，local 永远不行。
5. 新版本标题使用 `## X.Y.Z(YYYY-MM-DD)`；`(TBD)` 会阻止发布。tag 必须为同版本 `gx-shell-vX.Y.Z`，
   发布提交必须在 `main` 上，同名 Release 不得覆盖、tag 不得移动；授权后才提交/推送/tag/发布。
   手动 `release` 的 `publish=false` 仅构建验证，不能据此声称已经发布。

配置指纹、历史配置识别和迁移材料由 WezTerm fork 管理，并随 stage 的 `build-inputs` 提供；
根仓不再依赖旧 monorepo 发布提交复算它们。来源锁更新后仍需对获锁 fork 的这些材料重新验收。

## 验收与 PENDING

根目录安全可运行的验收入口（夹具测试不是完整产品构建）：

```bash
python -m unittest discover -s scripts -p 'test_gx_shell_*.py'
python scripts/gx_shell_sources.py --help
python scripts/gx_shell_package.py assemble --help
python scripts/gx_shell_package.py version
git diff --check
```

Windows 在根目录可运行
`powershell -NoProfile -File scripts/gx_shell_local_build.ps1 -Format Json` 做只读探测；脚本会从
`$PSCommandPath` 推导仓库根，也可显式传 `-RepoRoot`。`gx_shell_build.py --plan` 会进一步检查锁定的
独立 checkout 和资源预算，但不编译、不安装。按本机执行策略运行，不更改系统策略。已有 actionlint 时运行
`actionlint .github/workflows/release.yml`；缺工具明确记录，不为文档验收临时安装。

### 已批准的实测路线

以下为目标路线。最终锁 run `36998777427` 已完成路线 1 的 Windows 安装器生命周期与路线 2 的 DEB 容器验收，
**路线 3 的硬件 GPU 仍受阻**，结果见下节：

1. **GitHub-hosted Windows**：生成完整 payload，用 Inno Setup 7.1 编译安装器，再以
   `scripts/gx_shell_smoke_windows.ps1` 验证安装、使用、同版本重装、配置保护与卸载。
2. **Ubuntu GitHub runner**：完成 Linux 构建，以 `scripts/gx_shell_smoke_linux.sh` 在 Docker 的
   Ubuntu 20.04 和 24.04 容器验证**同一个 DEB** 的安装生命周期；不在本机安装 Docker 或 WSL。
3. **本机硬件 GPU/窗口**：新增入口 `scripts/gx_shell_smoke_gpu_windows.ps1` 的门禁仍返回
   `BLOCKED_UNSAFE_KNOWNFOLDERS`，真实 GPU 窗口与 runtime smoke 未验证。目标是对隔离的
   **完整 payload** 使用独立工作目录和配置做真实硬件 GPU/窗口检查，不运行安装器，不改现有用户配置、
   HKCU PATH 或字体。记录实际渲染适配器与窗口运行证据；不能只探测显卡或启动单个二进制就判定通过。

CPU 构建资源预算与 GPU 运行时验收分开，GPU 不用于编译加速。无 GPU 的 runner 可以验证软件 fallback
路径，但软件渲染不经过目标硬件 GPU/驱动，不能替代本机硬件 GPU 证据；本机窗口成功也不替代安装器生命周期。

### 本轮快照与当前待验证项

**分支与来源锁**：验证分支 `validation/default-branches-20261001` 已于 2026-10-02 快进合并到 `main`
（`origin/main` 由 `417d677e` 前进到 `a28e71e3`），并已在本地和远端删除，之后的工作直接在 `main` 上进行。
最终锁位于提交 `a9c7c4fd`：herdr `d36f1455e656cd12b20967357d12a8ddaeefaa04`（0.9.3）、ohmyzsh
`e7de531bab5671853caeb8360fa495e254561f4a`、wezterm `48aff481885592a0e1becbe6669800e23b74e268`。
`python -B scripts/gx_shell_sources.py check --lock components.lock.json` 给出 lock digest
`31ebd95d21abf3564e6db005f3d6b95ce65bb138c783bbc3a8b266b748195ef2`；`check --require-remote` 通过。

**根测试与静态检查**：本地 Windows 在 `TEMP` 指向 `.local/build/...` 时运行
`ISCC="C:/Users/guoxi/AppData/Local/Programs/Inno Setup 7/ISCC.exe" python -m unittest discover -s scripts -p 'test_gx_shell_*.py'`，
运行 229 项，跳过 7 项，失败 0。actionlint 1.7.12 在 `a9c7c4fd` 上检查 `.github/workflows/release.yml` 与
`.github/workflows/validate-artifacts.yml` 通过；`bash -n scripts/gx_shell_stage_shell.sh scripts/gx_shell_smoke_linux.sh` 通过。

**组件 fork**：herdr fork CI run `36993494473` 全绿：Windows nextest 5191 通过 / 24 跳过，Ubuntu 5759 通过 /
25 跳过 / 0 失败，macOS 5509 通过 / 23 跳过。ohmyzsh 的依赖锁中 herdr 为 `d36f1455` / 0.9.3；本地
`gx_dependencies.py audit` 两个平台均 ready，unittest 250 项中 248 通过、1 个错误（本机缺 zsh）、1 项跳过；
该 fork 默认分支没有 CI 运行记录。wezterm fork gx-ci run `36961878641` 通过。

**根 release workflow（旧锁）**：run `36993564664` 使用旧锁（HEAD `e30dc864`；herdr `b6a27411`、ohmyzsh `03d1731a`、
wezterm `48aff481`），其中 prepare、wezterm-tests、shell-linux、wezterm-linux、ohmyzsh-posix、package-linux、
smoke-linux（Ubuntu 20.04 与 24.04 的 DEB 安装、运行、重装、卸载）、wezterm-windows、shell-windows 成功；
package-windows 的根单测有 8 项失败，原因是 runner 的 `TEMP` 为 8.3 短名，已由 `dd329f81` 修复。

**根 release workflow（最终锁）**：run `36998777427` conclusion=success，head
`a9c7c4fd84643f43224af88079f6cd783d471b45`，时间 2026-10-02 11:02:11Z → 12:04:04Z。成功的 job：prepare、
wezterm-tests、wezterm-linux、shell-linux、ohmyzsh-posix、package-linux、smoke-linux (20.04)、smoke-linux (24.04)、
wezterm-windows、shell-windows、package-windows（25m30s）、verify（21s）。publish 因 publish=false 跳过，
validate-artifacts* 系列因不是复验模式跳过。Windows runner 上的根单测使用校验散列的 Inno Setup 7.1：
Ran 229，OK（skipped=7）。

- **产物**：Windows 安装器 `GX-Shell-0.2.0-Setup-x64.exe`，sha256
  `1ed5dba646a28a224473eb3aebe3510c8291a82cff70e4d3efbe3b19020b3a1d`；DEB `gx-shell_0.2.0_amd64.deb`，sha256
  `180a8ec8cc10a6617a496fb9a8717ae3dfbed360bb0a47b0bdd4481849e5c03d`。
- **verify**：两平台 provenance 与散列校验通过。`SHA256SUMS`（artifact verified-checksums，ID 11225011907）列出
  6 个文件：安装器、安装器 manifest、windows-x64 sources tar.xz、deb、deb manifest、amd64 sources tar.xz。
- **其余 artifact ID**：release-windows 11224701394、release-linux 11223632339、evidence-windows 11225635031、
  evidence-linux-20.04 11224056410、evidence-linux-24.04 11223352350。
- **Linux DEB 冒烟**：同一个 DEB 在 GitHub Ubuntu runner 的干净 Docker 容器 Ubuntu 20.04（20.04.6 LTS）与 24.04
  中完成安装、runtime smoke、重装与移除，均 PASS（Lua PURE_FN_TEST 635 cases）；旧版升级为 NOT_RUN。
- **Windows 生命周期冒烟**：在一次性 GitHub-hosted runner（Windows Server 2025）上由
  `scripts/gx_shell_smoke_windows.ps1` 执行，末行原文为
  `PASS: GX Shell Windows installer lifecycle only; GUI images await review, desktop input/echo/redraw and hardware GPU NOT_RUN; legacy release upgrade: NOT_RUN`。
  以下步骤依次全部通过：
  1. 安装；
  2. 新环境下 PATH 能解析 GX 入口；
  3. 开始菜单快捷方式在 WezTerm GX 中打开 GX Zsh；
  4. GX Zsh + Oh My Zsh 首次启动生成 GX 管理的 herdr 配置；
  5. 嵌套 shell 路径、`/tmp`、passwd home、zoxide 与内置 Linux 工具；
  6. gx-pwsh、iex、`param()` 安装脚本；
  7. app execution alias；
  8. herdr 包身份、受管更新与补全；
  9. herdr server 在内置 ConPTY 上运行真实 GX Zsh pane，MSYS 与原生程序的 Ctrl+C 正常；
  10. WezTerm 配置播种与内置字体（Lua PURE_FN_TEST ALL PASS 645 cases）；
  11. WezTerm GUI 默认启动 GX Zsh；
  12. 文件被占用时安装与卸载都拒绝且不删除安装，约 5.5 秒完成（此前 run `36969818934` 中的旧安装包在这一步
      超过 45 秒超时，由 ISS 静默卸载修复解决）；
  13. 同版本重装保留配置与完整 GX profile；
  14. 卸载只删除自有资源、保留全部用户数据；
  15. 二次安装后 GX Zsh、herdr、WezTerm 再次运行正常；
  16. 再次卸载。
- **GUI 截图**：evidence-windows 中 install、reinstall、install-again 三张截图已于 2026-10-02 由协调者人工审阅：
  WezTerm GX 窗口正常显示标签栏（default / zsh ~）、时钟、壁纸和 GX Zsh 提示符。窗口证据中 renderer 为
  `WebGpu software fallback`，只证明软件渲染路径；hardware GPU 和 desktop input/echo/redraw 仍为 NOT_RUN。

CI 通过的是两平台构建、verify、安装生命周期与软件渲染路径；该 run 使用 publish=false，发布本身未执行。
仍未验证：硬件 GPU 窗口（门禁仍为 `BLOCKED_UNSAFE_KNOWNFOLDERS`，`audited_wezterm_revision` 已过期）、
桌面输入/回显/重绘、旧版 Release 升级、本地完整 Windows 构建（Perl 缺模块）；ohmyzsh fork 默认分支没有 CI 记录；
根历史重建仍是独立 PENDING。

| 项目 | 当前验收边界 |
|---|---|
| 根测试 / planner / workflow 静态检查 | PASS：本地 Windows 根测试运行 229 项，跳过 7 项，失败 0；最终锁 run 的 Windows runner 根测试（校验散列的 Inno Setup 7.1）Ran 229，OK（skipped=7）；actionlint 1.7.12 与 `bash -n` 通过（见上）；旧锁 run 的 package-windows 根单测 8 项失败已由 `dd329f81` 修复 |
| 真实来源锁与默认分支 | PASS：最终锁 herdr `d36f1455`、ohmyzsh `e7de531b`、wezterm `48aff481`（完整 SHA 与 lock digest 见上），`check` 与 `check --require-remote` 通过；验证分支已合并到 `main` 并删除 |
| 组件 fork 自身测试 | herdr fork CI `36993494473` 全绿；wezterm fork gx-ci `36961878641` 通过；ohmyzsh 只有本地结果（audit 两平台 ready，unittest 248/250 通过、1 错误、1 跳过），默认分支没有 CI 运行记录 |
| 外部 source adapter / stage / workflow | PASS：最终锁 run `36998777427` conclusion=success，12 个 job 成功；publish（publish=false）与 validate-artifacts*（不是复验模式）跳过。旧锁 run `36993564664` 的 package-windows 失败已修复 |
| Rust/MSVC/SDK、Python、Perl、.NET | runner PASS：最终锁 run 的 wezterm-windows、shell-windows、wezterm-linux、shell-linux 成功。本地完整 Windows 构建未验证：Git 自带的 Perl 缺 `Locale/Maketext/Simple.pm`，按规则未自动安装工具；`gx_shell_build.py --plan --offline` 可以通过 |
| sccache / 可选 LLD | 默认不启用；如需启用，先验证已有工具，不自动安装 |
| Inno Setup 7.1 | PASS（GitHub-hosted Windows）：package-windows 成功（25m30s），产出 `GX-Shell-0.2.0-Setup-x64.exe`；Windows Server 2025 一次性 runner 上的安装生命周期冒烟全部通过，文件被占用时安装与卸载均拒绝且不删除安装 |
| Docker / Linux 工具链 | PASS：package-linux、smoke-linux (20.04) 与 smoke-linux (24.04) 成功；同一个 `gx-shell_0.2.0_amd64.deb` 在干净 Docker 容器 Ubuntu 20.04（20.04.6 LTS）与 24.04 中完成安装、runtime smoke、重装与移除；不在本机安装 Docker/WSL |
| zsh / PTY / nextest | PASS（CI）：最终锁 run 的 ohmyzsh-posix、wezterm-tests 成功；Windows 冒烟中 herdr server 在内置 ConPTY 上运行真实 GX Zsh pane；herdr nextest 由其 fork CI 覆盖。本机缺 zsh |
| verify / 发布 | verify PASS（21s）：两平台 provenance 与散列校验通过，`SHA256SUMS` 列出 6 个文件。publish 未执行（publish=false），尚未发布 |
| 硬件 GPU / 窗口 | BLOCKED：WezTerm 原生 KnownFolders 路径尚无安全隔离契约，`scripts/gx_shell_smoke_gpu_windows.ps1` 门禁仍返回 `BLOCKED_UNSAFE_KNOWNFOLDERS`，真实硬件 GPU 窗口与 runtime smoke 未验证；脚本中的 `audited_wezterm_revision` 仍为 `4b219eea`，相对锁定的 `48aff481` 已过期，新代码在 `clipboard_image_paste="Path"`（非默认）时会写 `%TEMP%`，尚未审计。CI 截图的 renderer 为 `WebGpu software fallback`，只证明软件渲染路径 |
| GUI 截图 / 桌面交互 | 截图已人工审阅（见上），只覆盖软件渲染路径；桌面输入/回显/重绘为 NOT_RUN，未验证 |
| 默认分支迁移与 `gx` 清理 | 已完成：验证分支已并入 `main`；三个 fork 的远端 `gx` 已于 2026-10-02 提前删除，删除时整包与 GPU 验收尚未完成（见「组件历史边界」）；迁移副本中 herdr、ohmyzsh 的本地 `gx` 已删除，不删除迁移副本 |
| 根协调仓无父初始化 commit | 独立 PENDING：原迁移计划保留；不在本轮执行范围，须在代码与两平台验收完成后另行授权、单独执行和验证 |
| 旧 Release 升级 | 未验证（既定设计）：两平台冒烟均为 NOT_RUN；旧资产退出验收输入，不报告为通过或 warning skip 后成功 |

出现失败先保留日志、lock digest 与 stage 回执，区分工具缺失、来源不符和测试失败。不要清空用户 checkout、
伪造 CI 环境或降低发布门禁。迁移尚未完成：最终锁 CI run `36998777427` 已通过，但使用 publish=false，发布本身
未执行；硬件 GPU 窗口、桌面输入/回显/重绘与旧版升级仍未验证，本文不宣称发布验收已完成。

## 许可

各组件沿用各自的许可证：WezTerm 与 Oh My Zsh 为 MIT，herdr 为 Apache-2.0；源码许可见各 fork
锁定 checkout 中的 LICENSE，根仓保留整包许可材料。打包的第三方许可随安装包分发：Windows 在
安装目录的 `licenses\`（WezTerm 部分在 `wezterm\` 下），Ubuntu 从
`/usr/share/doc/gx-shell/copyright` 列出各许可文本的位置。

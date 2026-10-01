# gx_shell（gx0404/gx_shell 协调仓）

主仓负责 GX Shell 的安装器、组件整合与发布；三个 fork 负责源码、上游同步与自身测试。
主仓通过 `components.lock.json` 锁定各 fork 既有默认分支的完整 SHA，分支对应关系见「来源锁与身份」。
构建链为外部 checkout → stage → 根 assemble。
安装、来源锁更新、本地资源规划和当前 PENDING 项见 `README.md`。

## 规则入口

- 本文件管根 `packaging/`、`scripts/`、`.github/`、`components.lock.json`、`.gitignore` 与根文档。
- 组件开发须在相应 fork 的独立 checkout 中读取其 `AGENTS.md`，按该文件运行规则路由器、遵守生成物
  与测试纪律。迁移工作区遗留的 `herdr/`、`ohmyzsh/`、`wezterm/` 不再是正式构建输入；在这些目录运行
  `git rev-parse HEAD` 可能继承主仓 HEAD，不能当作组件 revision。

## 语言与协作

- 与人交流用对方的语言；根文档用中文；代码、标识符、Inno/Debian 字段用英文。
- 提交格式 `type(scope): 中文描述`；type 为小写 conventional 前缀，根 scope 用
  `repo`/`packaging`/`ci`/`docs`，组件提交遵守 fork 规则；无 emoji、无 AI 署名。
  只暂存本次相关文件，不用 `git add -A`；先对齐提交信息，未经要求不提交、不 push、不打 tag、不发版。
- 并行协作只改分配的文件，不覆盖其他代理正在修改的脚本、测试或组件；文档不能把未运行的验证写成通过。

## 硬边界

- **来源锁与身份**：锁文件 `schema: 1`，`components` 恰含 `herdr`、`ohmyzsh`、`wezterm`；每项恰为
  `repository: gx0404/<name>`、`branch`、`revision: <40 位 commit SHA>`。`branch` 分别为既有默认分支
  `feature/gx_herdr`、`feature/gx_ohmyzsh`、`feature/gx_wezterm`。构建与 checkout 只使用锁定 SHA，
  不能解析浮动分支替代它。`scripts/gx_shell_sources.py check` 验结构与原始字节 SHA-256；
  `check --require-remote` 另验 commit 存在且可从对应默认分支到达。来源更新必须显式执行、审阅 diff。
- **外部 checkout**：CI 根 checkout 与组件 checkout 分离，组件放在 `RUNNER_TEMP`；本地放仓外短 ASCII
  路径。三个 fork 各有独立 Git 元数据；WezTerm 递归初始化自身 `.gitmodules`，根仓不再维护组件子模块。
  不复用有改动、SHA 不符、共享父仓 Git 元数据的目录，不 reset 或清除用户工作来凑齐构建条件。
- **stage 是组件的唯一打包输入**：组件按各自锁定 revision 生成完整 stage；根
  `scripts/gx_shell_stage_shell.sh` 对接外部 Oh My Zsh/herdr 入口，根 packager 不再读取根组件目录。
  组装记录根 coordinator SHA、三个不同来源的 revision、锁快照及 digest、构建回执与完整文件清单，
  不能再要求四仓 SHA 相同。herdr 必须带包身份及对应源码；缺文件、散列不符、同名字体内容不同、路径冲突
  或非契约允许的符号链接/junction 一律拒绝。packager 的 schema 2 与来源锁的 schema 1 不可混淆。
- **安装布局是跨组件契约**：Windows 为 `{app}\bin`、`lib`、`runtime\msys64`、
  `share\ohmyzsh-gx`、`fonts` 加 `{app}\wezterm\`；deb 为 `/usr/lib/{ohmyzsh-gx,wezterm-gx}`、
  `/usr/share/{ohmyzsh-gx,wezterm-gx}`。改布局须协调两个 fork 的启动器、WezTerm fork 内的
  `dotfiles/wezterm-config/utils/gx-shell.lua`、根 packager、安装生命周期与硬件 GPU 冒烟入口，更新锁并重新验收。
- **local 永远不可发布**：Windows 先用 `scripts/gx_shell_local_build.ps1` 做只读 CPU/内存规划。
  Cargo、CMake、Zsh 共用预算，组件串行，不把 jobs 乘以组件数；GPU 只用于后续 runtime smoke，不用于编译。
  本地构建用 `GX_LOCAL_BUILD_ROOT`，herdr 回执为 `builder=local`；组装必须 `--allow-dirty`，
  产物带 `-local`，不得提升为可发布包。环境不能带 `GH_TOKEN`/`GITHUB_TOKEN`，不得伪造 CI/runner 身份。
- **发版门禁**：只走 `.github/workflows/release.yml`；tag 必须等于根 CHANGELOG 最大 SemVer，日期
  不能是 `(TBD)`，coordinator commit 必须在 `main` 上。来源锁、组件测试、两平台构建、PTY/nextest、
  Inno Setup 7.1、安装与 runtime smoke、两平台 provenance/散列校验都通过后才能发布；上传清单以
  `verify` 生成的 `SHA256SUMS` 为准。不覆盖已发布版本、不移动 tag；fork workflow 留在各 fork 运行。
- **没有旧 Release 升级覆盖**：旧资产已按迁移决定退出验收输入；不下载旧安装包或根仓历史指纹 commit
  作为硬依赖，也不以 warning skip 冒充升级测试通过。保留安装/使用/卸载、同版本重装与配置保护检查；
  旧版到新版升级未验证，必须明确披露。配置指纹与迁移数据由 WezTerm fork 维护并随 stage 提供。
- **安装器只动自己拥有的东西**：Windows 仅写 HKCU 的 PATH、字体与 `Software\GX Shell`，
  文件占用时拒绝而不杀进程；deb 维护脚本不写用户 HOME。真实安装/卸载只在一次性 runner 或容器执行。
- **验收环境隔离**：完整 Windows 安装器与生命周期在 GitHub-hosted Windows 验证；同一个 DEB 在
  Ubuntu GitHub runner 的 Docker Ubuntu 20.04/24.04 容器验证。本机不安装 Docker/WSL，仅以隔离的
  完整 payload 做硬件 GPU/窗口验收；新增入口 `scripts/gx_shell_smoke_gpu_windows.ps1` 尚待实测。
  软件 fallback 只能证明软件渲染路径，不能替代硬件 GPU 验收；CPU 构建与 GPU 运行时证据分别记录。
- **历史与同步**：上游同步、组件提交历史与测试留在 fork；根仓不再做 subtree pull。将 `gx` 的独有
  提交以保留历史的合并纳入各自默认分支，验收后才删除 `gx`，不重写 fork 历史。根工作区不含组件目录；
  仓外迁移副本中 herdr、ohmyzsh 仍检出 `gx`，wezterm 不含独立 Git 元数据；不删除迁移副本，也不借清理覆盖用户工作。
- **根协调仓历史重建（独立 PENDING）**：保留未来以**无父初始化 commit** 建立根协调仓新历史、
  不继承旧 subtree 合并历史的迁移计划；组件默认分支切换与 `gx` 删除不取消此项。它不在本轮执行范围，
  须在代码与两平台验收完成后另行授权、单独执行和验证，不能宣称当前 HEAD 已完成重建。
  文档维护不修改 refs、不执行历史重建、分支清理或推送。

## 完成标准

- 根测试：`python -m unittest discover -s scripts -p 'test_gx_shell_*.py'`；Linux 另跑 deb/符号链接用例。
- 真实锁已存在；默认分支合并及锁更新后，重跑 `python scripts/gx_shell_sources.py check --lock components.lock.json`，
  再加 `--require-remote` 验远端。未完成的校验标 PENDING，不造 SHA 或用旧 `gx` 校验结果代替本轮证据。
- 改 `packaging/windows/gx-shell.iss` 须用 Inno Setup 7.1 实际编译；改 workflow 须跑已有 `actionlint`，
  缺工具则标 PENDING，不临时安装。组件测试按外部 fork 的规则执行，不能被根夹具单测替代。
- 工具探测与真实构建分开记录；工具缺口、验收路线和命令见 README。历史 101 项测试、7 项跳过不是本轮结果。
  本轮尚无真实产品验收结果，最终实测后回填实际命令、结果/跳过数与未验证项；不提前声称发布验收完成。

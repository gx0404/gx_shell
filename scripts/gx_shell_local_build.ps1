#requires -Version 5.1
<#
.SYNOPSIS
Read-only Windows local-build planning; never downloads, installs or builds.
.DESCRIPTION
Use -Format Json for machine-readable output or -Format Environment for
PowerShell process-environment assignments. Neither mode applies assignments
or creates directories. Both (default) prints JSON followed by assignments.
RepoRoot is the coordinator checkout and may contain non-ASCII characters.
BuildRoot must resolve to a new run directory directly below
<repo>\.local\build; when omitted, a fresh plan-<timestamp> name there is
proposed. ComponentRoots maps herdr/ohmyzsh/wezterm to independent checkouts
below <repo>\.local\sources; absent entries default to
<repo>\.local\sources\<name>. ComponentRevisions optionally pins their full
commit SHAs; absent checkouts remain unverified. A monorepo parent HEAD is
never a component revision. Per-component cache, target, log and work
directories stay inside the run directory, keyed by component name, pinned
revision, toolchain fingerprint and target. Jobs are a shared ceiling for ONE
active component, not a per-component allocation to multiply across
simultaneous builds. Memory limits are planning estimates, not OS-enforced
quotas. Missing prerequisites set ready=false; invalid input exits nonzero
without echoing supplied values or tool stderr.
.EXAMPLE
.\scripts\gx_shell_local_build.ps1 -Format Json
.EXAMPLE
$repo = 'D:\src\gx_shell'
.\scripts\gx_shell_local_build.ps1 -Format Environment -RepoRoot $repo `
    -BuildRoot (Join-Path $repo '.local\build\run-01') -Component herdr `
    -ComponentRoots @{herdr=(Join-Path $repo '.local\sources\herdr')} `
    -Toolchain 1.96.1-x86_64-pc-windows-msvc
#>
[CmdletBinding()]
param(
    [ValidateSet('Json', 'Environment', 'Both')][string]$Format = 'Both',
    [string]$BuildRoot = $env:GX_BUILD_ROOT,
    [string]$RepoRoot = '',
    [string]$Toolchain = $env:RUSTUP_TOOLCHAIN,
    [ValidateSet('x86_64-pc-windows-msvc')][string]$Target = 'x86_64-pc-windows-msvc',
    [ValidateSet('herdr', 'ohmyzsh', 'wezterm')][string]$Component = 'wezterm',
    [hashtable]$ComponentRoots = @{},
    [hashtable]$ComponentRevisions = @{},
    [switch]$UseSccache,
    [switch]$UseLld
)
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$script:Diagnostics = New-Object 'System.Collections.Generic.List[string]'

function Fail([string]$Message) { throw [InvalidOperationException]::new($Message) }

function Find-Executable([string]$Name, [string[]]$Candidates = @()) {
    foreach ($path in $Candidates) {
        if ($path -and [IO.File]::Exists($path)) { return [IO.Path]::GetFullPath($path) }
    }
    $command = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $command) { return $command.Source }
    return $null
}

function Invoke-Probe([string]$File, [string[]]$Arguments, [string]$Label) {
    if (-not $File) { return $null }
    $process = New-Object Diagnostics.Process
    try {
        $info = New-Object Diagnostics.ProcessStartInfo
        $info.FileName = $File
        $quoted = foreach ($arg in $Arguments) {
            if ($arg -match '["\r\n]') { Fail 'A probe argument contains unsupported characters.' }
            '"' + [regex]::Replace($arg, '(\\+)$', '$1$1') + '"'
        }
        $info.Arguments = $quoted -join ' '
        $info.WorkingDirectory = $env:SystemRoot
        $info.UseShellExecute = $false
        $info.CreateNoWindow = $true
        $info.RedirectStandardOutput = $true
        $info.RedirectStandardError = $true
        $info.EnvironmentVariables['RUSTUP_AUTO_INSTALL'] = '0'
        $info.EnvironmentVariables['CARGO_NET_OFFLINE'] = 'true'
        $info.EnvironmentVariables['GIT_OPTIONAL_LOCKS'] = '0'
        $info.EnvironmentVariables['GIT_TERMINAL_PROMPT'] = '0'
        $info.EnvironmentVariables.Remove('GITHUB_TOKEN')
        $info.EnvironmentVariables.Remove('GH_TOKEN')
        $process.StartInfo = $info
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(10000)) {
            $process.Kill()
            [void]$script:Diagnostics.Add($Label + ': timed out; no output retained.')
            return $null
        }
        $tasks = [Threading.Tasks.Task[]]@($stdout, $stderr)
        if (-not [Threading.Tasks.Task]::WaitAll($tasks, 2000) -or $process.ExitCode -ne 0) {
            [void]$script:Diagnostics.Add($Label + ': query failed; no output retained.')
            return $null
        }
        return $stdout.Result.Trim()
    } catch {
        [void]$script:Diagnostics.Add($Label + ': unavailable; no output retained.')
        return $null
    } finally { $process.Dispose() }
}

function Get-FileTool([string]$Path) {
    $version = $null
    if ($Path) {
        try {
            $metadata = [Diagnostics.FileVersionInfo]::GetVersionInfo($Path)
            foreach ($value in @($metadata.ProductVersion, $metadata.FileVersion)) {
                if ($value -match '^([0-9]+(?:[.,][0-9]+){1,3})' -and $Matches[1] -notmatch '^[0.,]+$') {
                    $version = $Matches[1]
                    break
                }
            }
        } catch { [void]$script:Diagnostics.Add('File version metadata unavailable.') }
    }
    return [ordered]@{ found = [bool]$Path; path = $Path; version = $version }
}

function Get-Hardware {
    $physical = $null
    $logical = [Environment]::ProcessorCount
    $total = $null
    $available = $null
    $cpuSource = 'Environment.ProcessorCount; physical cores unknown'
    try {
        $processors = @(Get-CimInstance -ClassName Win32_Processor -ErrorAction Stop)
        $cores = [int](($processors | Measure-Object NumberOfCores -Sum).Sum)
        $threads = [int](($processors | Measure-Object NumberOfLogicalProcessors -Sum).Sum)
        if ($cores -lt 1 -or $threads -lt $cores) { Fail 'Invalid CPU topology.' }
        $physical = $cores
        $logical = $threads
        $cpuSource = 'Win32_Processor'
    } catch { [void]$script:Diagnostics.Add('CPU topology query unavailable; conservative fallback in use.') }
    try {
        $computer = Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction Stop
        if ([double]$computer.TotalPhysicalMemory -gt 0) {
            $total = [Math]::Round([double]$computer.TotalPhysicalMemory / 1GB, 2)
        }
        $os = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop
        if ([double]$os.FreePhysicalMemory -gt 0) {
            $available = [Math]::Round([double]$os.FreePhysicalMemory / 1MB, 2)
        }
    } catch { [void]$script:Diagnostics.Add('Memory query incomplete; unknown measurements remain null.') }
    return [ordered]@{ physical_cores = $physical; logical_cores = $logical; cpu_source = $cpuSource
        total_memory_gib = $total; available_memory_gib = $available }
}

function Get-PositiveNumber([string]$Name, [string]$Value, [switch]$Integer) {
    if ([string]::IsNullOrEmpty($Value)) { return $null }
    $pattern = if ($Integer) { '^[1-9][0-9]{0,4}$' } else { '^[0-9]{1,5}(?:\.[0-9]{1,2})?$' }
    if ($Value -notmatch $pattern) { Fail ($Name + ' must be a positive number (decimal point: period).') }
    $number = [double]::Parse($Value, [Globalization.CultureInfo]::InvariantCulture)
    if ($number -le 0) { Fail ($Name + ' must be positive.') }
    return $number
}

function Get-Budget($Hardware, [string]$CpuOverride, [string]$ZshOverride, [string]$MemoryOverride) {
    $cpu = Get-PositiveNumber 'GX_CPU_JOBS' $CpuOverride -Integer
    $zsh = Get-PositiveNumber 'GX_ZSH_JOBS' $ZshOverride -Integer
    $memory = Get-PositiveNumber 'GX_MEMORY_BUDGET_GB' $MemoryOverride
    $logical = [int]$Hardware.logical_cores
    $reservedCpu = [int][Math]::Min([Math]::Max(2, [Math]::Ceiling($logical * 0.2)), $logical - 1)
    $cpuLimit = $logical - $reservedCpu
    if ($null -ne $Hardware.physical_cores) {
        $cpuLimit = [int][Math]::Min($cpuLimit, $Hardware.physical_cores + [Math]::Floor(($logical - $Hardware.physical_cores) / 2))
    } else { $cpuLimit = [Math]::Min(2, $cpuLimit) }
    $reservedMemory = $null
    $memoryLimit = 6.0
    if ($null -ne $Hardware.total_memory_gib) {
        $reservedMemory = [Math]::Max(6, [Math]::Ceiling($Hardware.total_memory_gib * 0.15))
        $memoryLimit = [Math]::Floor(($Hardware.total_memory_gib - $reservedMemory) * 100) / 100
    }
    if ($null -ne $Hardware.available_memory_gib) {
        $availableBudget = [Math]::Floor(([double]$Hardware.available_memory_gib - 2.0) * 100.0) / 100.0
        $memoryLimit = [Math]::Min([double]$memoryLimit, $availableBudget)
    }
    if ($memoryLimit -lt 6) { Fail 'Insufficient available memory: at least 6 GiB build budget plus system headroom is required.' }
    if ($null -eq $memory) { $memory = $memoryLimit }
    if ($memory -lt 6 -or $memory -gt $memoryLimit) { Fail 'GX_MEMORY_BUDGET_GB exceeds safe headroom or is below 6 GiB.' }
    $memoryJobs = [int][Math]::Floor(($memory - 4) / 2)
    $jobLimit = [int][Math]::Min($cpuLimit, $memoryJobs)
    if ($null -eq $cpu) { $cpu = [Math]::Min(16, $jobLimit) }
    if ($cpu -gt $jobLimit) { Fail 'GX_CPU_JOBS exceeds the shared CPU/memory budget, including system reserves.' }
    if ($null -eq $zsh) { $zsh = [Math]::Min(8, $cpu) }
    if ($zsh -gt $cpu) { Fail 'GX_ZSH_JOBS must not exceed GX_CPU_JOBS.' }
    return [ordered]@{ cpu_jobs = [int]$cpu; zsh_jobs = [int]$zsh; memory_budget_gib = $memory
        reserved_logical_cores = $reservedCpu; reserved_memory_gib = $reservedMemory
        memory_estimated = ($null -eq $Hardware.total_memory_gib); memory_gib_per_job = 2
        link_headroom_gib = 4; max_parallel_components = 1; enforcement = 'advisory; caller must serialize builds' }
}

function Get-BuildRoot([string]$Value, [string]$Repository) {
    $base = [IO.Path]::GetFullPath((Join-Path $Repository '.local\build'))
    if (-not $Value) {
        $stamp = [DateTime]::Now.ToString('yyyyMMdd-HHmmss', [Globalization.CultureInfo]::InvariantCulture)
        $Value = Join-Path $base ('plan-' + $stamp)
    }
    $Value = $Value.Replace('/', '\').TrimEnd('\')
    if ($Value -notmatch '^[A-Za-z]:\\') {
        Fail 'BuildRoot must be an absolute drive path to a new run directory directly below the repository .local\build directory.'
    }
    try { $full = [IO.Path]::GetFullPath($Value) } catch {
        Fail 'BuildRoot must be an absolute drive path to a new run directory directly below the repository .local\build directory.'
    }
    if ((Split-Path -Parent $full) -ine $base) {
        Fail 'BuildRoot must be a new run directory directly below the repository .local\build directory.'
    }
    $name = Split-Path -Leaf $full
    if ($name -notmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$' -or $name -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$') {
        Fail 'BuildRoot run name must be 1-32 ASCII letters, digits, underscores or hyphens, and never a reserved device name.'
    }
    if ([IO.Directory]::Exists($full) -or [IO.File]::Exists($full)) {
        Fail 'BuildRoot run directory must not exist yet; choose a fresh run name for every run.'
    }
    return $full
}

function Get-ComponentRoot([string]$Name, [string]$Value, [string]$SourcesBase) {
    $Value = $Value.Replace('/', '\').TrimEnd('\')
    if ($Value -notmatch '^[A-Za-z]:\\') {
        Fail ($Name + ': component root must be an absolute drive path below the repository .local\sources directory.')
    }
    try { $full = [IO.Path]::GetFullPath($Value) } catch {
        Fail ($Name + ': component root must be an absolute drive path below the repository .local\sources directory.')
    }
    $prefix = [IO.Path]::GetFullPath($SourcesBase).TrimEnd('\') + '\'
    if ($full.Length -le $prefix.Length -or $full.IndexOf($prefix, [StringComparison]::OrdinalIgnoreCase) -ne 0) {
        Fail ($Name + ': component roots must stay below the repository .local\sources directory.')
    }
    return $full
}

function Get-RustTools([string]$Requested, [string]$BuildTarget) {
    $rustup = Find-Executable 'rustup.exe'
    $installed = @()
    $listing = Invoke-Probe $rustup @('toolchain', 'list') 'rustup toolchain list'
    foreach ($line in ($listing -split '\r?\n')) {
        if ($line -match '^([A-Za-z0-9_.-]+-x86_64-pc-windows-msvc)(?:\s|$)') { $installed += $Matches[1] }
    }
    if ($Requested -and $Requested -notmatch '^[A-Za-z0-9_.-]+-x86_64-pc-windows-msvc$') {
        Fail 'Toolchain must name an installed x86_64-pc-windows-msvc toolchain, not a path or host alias.'
    }
    if (-not $Requested) {
        $pinned = @($installed | Where-Object { $_ -match '^\d+\.\d+\.\d+-' } |
            Sort-Object { [version](($_ -split '-')[0]) } -Descending)
        if ($pinned.Count) { $Requested = $pinned[0] }
        elseif ($installed.Count) { $Requested = ($installed | Sort-Object)[0] }
    }
    $rustc = $null
    $cargo = $null
    if ($Requested -and $installed -contains $Requested) {
        $rustc = Invoke-Probe $rustup @('which', '--toolchain', $Requested, 'rustc') 'rustc location'
        $cargo = Invoke-Probe $rustup @('which', '--toolchain', $Requested, 'cargo') 'cargo location'
        if (-not $rustc -or -not [IO.File]::Exists($rustc)) { $rustc = $null }
        if (-not $cargo -or -not [IO.File]::Exists($cargo)) { $cargo = $null }
    }
    $verbose = Invoke-Probe $rustc @('-vV') 'rustc version'
    $cargoText = Invoke-Probe $cargo @('-V') 'cargo version'
    $release = $null
    $commit = $null
    $hostTarget = $null
    $cargoVersion = $null
    if ($verbose -match '(?m)^release: ([0-9][A-Za-z0-9.+-]*)\r?$') { $release = $Matches[1] }
    if ($verbose -match '(?m)^commit-hash: ([0-9a-f]{40})\r?$') { $commit = $Matches[1] }
    if ($verbose -match '(?m)^host: ([A-Za-z0-9_-]+)\r?$') { $hostTarget = $Matches[1] }
    if ($cargoText -match '^cargo ([0-9][A-Za-z0-9.+-]*)') { $cargoVersion = $Matches[1] }
    $targetInstalled = $false
    if ($rustc) {
        $sysroot = Split-Path -Parent (Split-Path -Parent $rustc)
        $stdlib = Join-Path $sysroot ('lib\rustlib\' + $BuildTarget + '\lib')
        if (Test-Path -LiteralPath $stdlib -PathType Container) {
            $targetInstalled = @(Get-ChildItem -LiteralPath $stdlib -Filter 'libstd-*.rlib' -File).Count -gt 0
        }
    }
    return [ordered]@{ rustup = $rustup; installed_msvc_toolchains = $installed; selected = $Requested
        rustc = $rustc; cargo = $cargo; rustc_version = $release; rustc_commit = $commit
        cargo_version = $cargoVersion; host = $hostTarget; target = $BuildTarget; target_installed = $targetInstalled
        ready = [bool]($release -and $cargoVersion -and $hostTarget -eq $BuildTarget -and $targetInstalled) }
}

function Get-NativeTools {
    $pf = [Environment]::GetFolderPath('ProgramFilesX86')
    $vswhere = Find-Executable 'vswhere.exe' @((Join-Path $pf 'Microsoft Visual Studio\Installer\vswhere.exe'))
    $vs = Invoke-Probe $vswhere @('-latest', '-products', '*', '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath') 'MSVC discovery'
    $cl = $null
    $link = $null
    if ($vs -and [IO.Directory]::Exists((Join-Path $vs 'VC\Tools\MSVC'))) {
        $versions = @(Get-ChildItem -LiteralPath (Join-Path $vs 'VC\Tools\MSVC') -Directory |
            Where-Object { $_.Name -match '^\d+\.\d+\.\d+$' } | Sort-Object { [version]$_.Name } -Descending)
        foreach ($version in $versions) {
            $candidate = Join-Path $version.FullName 'bin\Hostx64\x64'
            if ([IO.File]::Exists((Join-Path $candidate 'cl.exe')) -and [IO.File]::Exists((Join-Path $candidate 'link.exe'))) {
                $cl = Join-Path $candidate 'cl.exe'
                $link = Join-Path $candidate 'link.exe'
                break
            }
        }
    }
    if (-not $cl) {
        $candidate = Find-Executable 'cl.exe'
        if ($candidate -and [Diagnostics.FileVersionInfo]::GetVersionInfo($candidate).CompanyName -match '^Microsoft') {
            $cl = $candidate
            $candidateLink = Join-Path (Split-Path -Parent $cl) 'link.exe'
            if ([IO.File]::Exists($candidateLink)) { $link = $candidateLink }
        }
    }
    $sdk = $null
    $sdkRoot = Join-Path $pf 'Windows Kits\10'
    if ([IO.Directory]::Exists((Join-Path $sdkRoot 'Lib'))) {
        foreach ($version in @(Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory |
                Where-Object { $_.Name -match '^10\.\d+\.\d+\.\d+$' } | Sort-Object { [version]$_.Name } -Descending)) {
            if ([IO.File]::Exists((Join-Path $version.FullName 'um\x64\kernel32.lib')) -and
                [IO.File]::Exists((Join-Path $version.FullName 'ucrt\x64\ucrt.lib')) -and
                [IO.File]::Exists((Join-Path $sdkRoot ('Include\' + $version.Name + '\um\Windows.h')))) {
                $sdk = $version.Name
                break
            }
        }
    }
    $innoCandidates = @()
    foreach ($base in @($pf, [Environment]::GetFolderPath('ProgramFiles'), [Environment]::GetFolderPath('LocalApplicationData'))) {
        foreach ($suffix in @('Inno Setup 7\ISCC.exe', 'Programs\Inno Setup 7\ISCC.exe')) { $innoCandidates += Join-Path $base $suffix }
    }
    $lldCandidates = @()
    if ($vs) { $lldCandidates += Join-Path $vs 'VC\Tools\Llvm\x64\bin\lld-link.exe' }
    $lldCandidates += Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'LLVM\bin\lld-link.exe'
    return [ordered]@{
        msvc = [ordered]@{ compiler = (Get-FileTool $cl); linker = (Get-FileTool $link); sdk_version = $sdk
            vcvars64 = $(if ($vs) { Join-Path $vs 'VC\Auxiliary\Build\vcvars64.bat' } else { $null })
            ready = [bool]($cl -and $link -and $sdk); environment_activated = $false }
        sccache = (Get-FileTool (Find-Executable 'sccache.exe'))
        lld = (Get-FileTool (Find-Executable 'lld-link.exe' $lldCandidates))
        ld_lld = (Get-FileTool (Find-Executable 'ld.lld.exe'))
        inno = (Get-FileTool (Find-Executable 'ISCC.exe' $innoCandidates))
        powershell = (Get-FileTool (Find-Executable 'powershell.exe'))
        pwsh = (Get-FileTool (Find-Executable 'pwsh.exe'))
        zig = (Get-FileTool (Find-Executable 'zig.exe'))
    }
}

function Get-Component([string]$Name, [string]$Root, [string]$Revision, [string]$Git) {
    if ($Revision -and $Revision -notmatch '^[0-9a-fA-F]{40}$') { Fail 'ComponentRevisions must contain full 40-character commit SHAs.' }
    $verified = $false
    $dirty = $null
    $kind = if ($Revision) { 'explicit-unverified' } else { 'unknown' }
    if ($Root -and [IO.Directory]::Exists($Root) -and $Git) {
        $Root = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
        $prefix = @('-c', 'core.fsmonitor=false', '-C', $Root)
        $top = Invoke-Probe $Git ($prefix + @('rev-parse', '--show-toplevel')) ($Name + ' checkout root')
        if ($top -and [IO.Path]::GetFullPath($top).TrimEnd('\', '/') -ieq $Root) {
            $head = Invoke-Probe $Git ($prefix + @('rev-parse', '--verify', 'HEAD^{commit}')) ($Name + ' revision')
            if ($head -match '^[0-9a-f]{40}$') {
                if ($Revision -and $Revision -ine $head) { Fail ($Name + ': pinned revision differs from checkout HEAD.') }
                $Revision = $head
                $kind = 'independent-checkout'
                $status = Invoke-Probe $Git ($prefix + @('status', '--porcelain', '--untracked-files=normal')) ($Name + ' clean state')
                if ($null -ne $status) { $dirty = [bool]$status; $verified = -not $dirty }
            }
        } else { [void]$script:Diagnostics.Add($Name + ': not an independent checkout; parent HEAD ignored.') }
    }
    if (-not $verified) { [void]$script:Diagnostics.Add($Name + ': clean independent source not verified; cache is only a proposal.') }
    return [ordered]@{ root = $Root; revision = $(if ($Revision) { $Revision.ToLowerInvariant() } else { $null })
        source_verified = $verified; source_kind = $kind; dirty = $dirty; paths = $null }
}

function Get-Key([string]$Text) {
    $hash = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text)))).Replace('-', '').ToLowerInvariant().Substring(0, 16) }
    finally { $hash.Dispose() }
}

try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { Fail 'This planner requires Windows PowerShell 5.1 or PowerShell 7 on Windows.' }
    if (-not $RepoRoot) {
        $RepoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
    }
    $RepoRoot = $RepoRoot.Replace('/', '\').TrimEnd('\')
    if ($RepoRoot -notmatch '^[A-Za-z]:\\') { Fail 'RepoRoot must be an absolute local drive path.' }
    try { $RepoRoot = [IO.Path]::GetFullPath($RepoRoot) } catch { Fail 'RepoRoot must be an absolute local drive path.' }
    if (-not [IO.Directory]::Exists($RepoRoot)) { Fail 'RepoRoot must be an existing coordinator checkout.' }
    foreach ($mapping in @($ComponentRoots, $ComponentRevisions)) {
        foreach ($key in $mapping.Keys) {
            if ($key -notin @('herdr', 'ohmyzsh', 'wezterm')) { Fail 'Component mappings accept only herdr, ohmyzsh and wezterm.' }
        }
    }
    $root = Get-BuildRoot $BuildRoot $RepoRoot
    $sourcesBase = Join-Path $RepoRoot '.local\sources'
    $hardware = Get-Hardware
    $budget = Get-Budget $hardware $env:GX_CPU_JOBS $env:GX_ZSH_JOBS $env:GX_MEMORY_BUDGET_GB
    $rust = Get-RustTools $Toolchain $Target
    $tools = Get-NativeTools
    if ($UseSccache -and -not $tools.sccache.found) { Fail 'UseSccache requires an installed sccache.exe.' }
    if ($UseLld -and -not $tools.lld.found) { Fail 'UseLld requires an installed lld-link.exe.' }
    $fingerprint = [ordered]@{ schema = 1; rustc = $rust.rustc_version; rustc_commit = $rust.rustc_commit
        cargo = $rust.cargo_version; host = $rust.host; toolchain = $rust.selected
        msvc = $tools.msvc.compiler.version; sdk = $tools.msvc.sdk_version
        linker = $(if ($UseLld) { $tools.lld } else { $tools.msvc.linker }); sccache = [bool]$UseSccache
        zig = $tools.zig }
    $toolchainKey = Get-Key ($fingerprint | ConvertTo-Json -Depth 6 -Compress)
    $components = [ordered]@{}
    $git = Find-Executable 'git.exe'
    foreach ($name in @('herdr', 'ohmyzsh', 'wezterm')) {
        $sourceRoot = Join-Path $sourcesBase $name
        if ($ComponentRoots.ContainsKey($name) -and [string]$ComponentRoots[$name]) {
            $sourceRoot = [string]$ComponentRoots[$name]
        }
        $sourceRoot = Get-ComponentRoot $name $sourceRoot $sourcesBase
        $entry = Get-Component $name $sourceRoot ([string]$ComponentRevisions[$name]) $git
        if ($entry.revision) {
            $leaf = $name + '-' + (Get-Key ($entry.revision + '|' + $toolchainKey + '|' + $Target))
            $cache = Join-Path (Join-Path $root 'c') $leaf
            $entry.paths = [ordered]@{ cache = $cache; work = (Join-Path (Join-Path $root 'w') $leaf)
                cargo_home = (Join-Path $cache 'cargo'); cargo_target = (Join-Path $cache 'target')
                sccache = (Join-Path $cache 'sccache'); zsh = (Join-Path $cache 'zsh')
                logs = (Join-Path $cache 'logs') }
            foreach ($planned in $entry.paths.Values) {
                if ($planned.Length -gt 120) {
                    Fail 'BuildRoot leaves too little path budget: planned per-component paths exceed 120 characters; choose a shorter run name.'
                }
            }
        }
        $components[$name] = $entry
    }
    $environment = [ordered]@{ GX_BUILD_ROOT = $root; GX_LOCAL_BUILD_ROOT = $root
        GX_CPU_JOBS = [string]$budget.cpu_jobs; GX_ZSH_JOBS = [string]$budget.zsh_jobs
        GX_MEMORY_BUDGET_GB = $budget.memory_budget_gib.ToString([Globalization.CultureInfo]::InvariantCulture)
        CARGO_BUILD_JOBS = [string]$budget.cpu_jobs; CMAKE_BUILD_PARALLEL_LEVEL = [string]$budget.cpu_jobs
        NUM_JOBS = [string]$budget.cpu_jobs; CARGO_BUILD_TARGET = $Target
        CARGO_NET_OFFLINE = 'true'; RUSTUP_AUTO_INSTALL = '0' }
    if ($rust.ready) { $environment['RUSTUP_TOOLCHAIN'] = $rust.selected }
    $selected = $components[$Component]
    if ($selected.paths) {
        $environment['GX_COMPONENT_REVISION'] = $selected.revision
        $environment['GX_COMPONENT_WORK_ROOT'] = $selected.paths.work
        $environment['GX_COMPONENT_CACHE_ROOT'] = $selected.paths.cache
        $environment['CARGO_HOME'] = $selected.paths.cargo_home
        $environment['CARGO_TARGET_DIR'] = $selected.paths.cargo_target
        if ($UseSccache) { $environment['SCCACHE_DIR'] = $selected.paths.sccache }
    }
    if ($UseSccache) { $environment['RUSTC_WRAPPER'] = $tools.sccache.path }
    if ($UseLld) { $environment['CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER'] = $tools.lld.path }
    $warnings = @(
        'Plan only: no directories created, environment changed, dependencies installed or build executed.',
        'Serialize component builds; Cargo, native jobs and Zsh share this ceiling. Memory usage is an estimate.',
        'Caches are proposals, not build evidence. Populate dependencies offline; every run uses a fresh directory below .local\build.',
        'Activate the MSVC/SDK environment separately. No linker or compiler is executed by this planner.',
        'ready covers selected source and Rust/MSVC planning only; package-specific dependencies and receipts remain unchecked.',
        'Optional tools are detected, not enabled, unless UseSccache/UseLld is supplied. Existing build flags are not inspected.'
    )
    $memoryAvailable = $null -ne $hardware.available_memory_gib -and $hardware.available_memory_gib -ge ($budget.memory_budget_gib + 2)
    if (-not $memoryAvailable) {
        $warnings += 'Currently available RAM is below the total-memory plan or unknown. Close applications or lower GX_MEMORY_BUDGET_GB and jobs before building.'
    }
    if (-not $rust.ready) { $warnings += 'An installed MSVC Rust toolchain, Cargo and target standard library are required; nothing was installed.' }
    if (-not $tools.msvc.ready) { $warnings += 'MSVC compiler/linker or Windows SDK is missing; nothing was installed.' }
    if ($env:GITHUB_ACTIONS -eq 'true' -or $env:GH_TOKEN -or $env:GITHUB_TOKEN) {
        $warnings += 'Local builds require a non-CI environment without GH_TOKEN/GITHUB_TOKEN. Values were not read into the report.'
    }
    $safeLocal = $env:GITHUB_ACTIONS -ne 'true' -and -not $env:GH_TOKEN -and -not $env:GITHUB_TOKEN
    $report = [ordered]@{ schema_version = 1; mode = 'plan-only'; builder = 'local'; publishable = $false
        ready = [bool]($rust.ready -and $tools.msvc.ready -and $selected.source_verified -and $safeLocal -and -not $budget.memory_estimated -and $memoryAvailable)
        selected_component = $Component; powershell_version = $PSVersionTable.PSVersion.ToString()
        hardware = $hardware; budget = $budget; toolchain = $rust; tools = $tools
        paths = [ordered]@{ build_root = $root; run_name = (Split-Path -Leaf $root); repo_root = $RepoRoot
            sources_root = $sourcesBase; exists = [IO.Directory]::Exists($root)
            toolchain_key = $toolchainKey; fingerprint = $fingerprint; components = $components }
        environment = $environment; diagnostics = @($script:Diagnostics.ToArray()); warnings = $warnings
        gpu = 'Not probed or used for compilation; GPU validation belongs only to later WezTerm runtime smoke.' }
    if ($Format -ne 'Environment') { $report | ConvertTo-Json -Depth 12 }
    if ($Format -ne 'Json') {
        '# Proposed PowerShell process environment; review before applying. Build steps must remain sequential.'
        foreach ($key in $environment.Keys) {
            '$env:' + $key + ' = ' + "'" + ([string]$environment[$key]).Replace("'", "''") + "'"
        }
    }
} catch {
    $message = 'Local planning failed; check input paths, permissions and installed tools. Tool output was suppressed.'
    if ($_.Exception -is [InvalidOperationException]) { $message = $_.Exception.Message }
    [Console]::Error.WriteLine('gx-shell-local-build: ' + $message)
    exit 1
}

# Project-local bootstrap; no existing Python is required. Windows x64 only.
[CmdletBinding()]
param([Alias('Doctor')][switch]$Check, [switch]$InnoSetup)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# Digests: GitHub release asset metadata; Inno pin matches gx_ghostty setup_env.py.
$PythonVersion = '3.12.12'
$PythonBuild = '20251014'
$PythonUrl = 'https://github.com/astral-sh/python-build-standalone/releases/download/20251014/cpython-3.12.12%2B20251014-x86_64-pc-windows-msvc-install_only.tar.gz'
$PythonSha256 = '2d670beb3b930d30e3a13cc909923a001dbdfcb5537692d5da40b6b41643ce1c'
$ActionlintVersion = '1.7.12'
$ActionlintUrl = 'https://github.com/rhysd/actionlint/releases/download/v1.7.12/actionlint_1.7.12_windows_amd64.zip'
$ActionlintSha256 = '6e7241b51e6817ea6a047693d8e6fed13b31819c9a0dd6c5a726e1592d22f6e9'
$InnoVersion = '7.1.0'
$InnoUrl = 'https://github.com/jrsoftware/issrc/releases/download/is-7_1_0/innosetup-7.1.0-x64.exe'
$InnoSha256 = '0362a383ed217d4c4239b5933866dd96d3eb2102737da92f80f6057a4b40df2f'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$LocalRoot = Join-Path $RepoRoot '.local'
$ToolsRoot = Join-Path $RepoRoot '.local/tools'
$CacheRoot = Join-Path $RepoRoot '.local/cache/setup'
$PythonKey = "cpython-$PythonVersion-windows-x86_64-none"
$PythonDir = Join-Path $ToolsRoot "python/$PythonKey"
$PythonExe = Join-Path $PythonDir 'python.exe'
$ActionlintDir = Join-Path $ToolsRoot 'actionlint'
$ActionlintExe = Join-Path $ActionlintDir 'actionlint.exe'
$InnoDir = Join-Path $ToolsRoot 'innosetup'
$IsccExe = Join-Path $InnoDir 'ISCC.exe'

function Assert-LocalPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    $boundary = [IO.Path]::GetFullPath($LocalRoot)
    if ($full -ne $boundary -and -not $full.StartsWith($boundary + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path escapes .local: $Path"
    }
    # Refuse redirects, including a linked .local, before reads or writes.
    for ($part = $full; $part.Length -ge $boundary.Length; $part = Split-Path -Parent $part) {
        if (Test-Path -LiteralPath $part) {
            if ((Get-Item -Force -LiteralPath $part).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Linked setup path is not allowed: $part"
            }
        }
    }
}

function Get-VerifiedDownload([string]$Url, [string]$Sha256, [string]$Name) {
    if ($Sha256 -notmatch '^[0-9a-f]{64}$') { throw 'Invalid SHA-256 pin' }
    $target = Join-Path $CacheRoot $Name
    Assert-LocalPath $target
    if (-not (Test-Path -LiteralPath $target)) {
        $partial = Join-Path $RunRoot ($Name + '.partial')
        Write-Host "Download: $Url"
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $partial
        if ((Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Sha256) {
            throw "SHA-256 mismatch: $partial (retained for diagnosis)"
        }
        Move-Item -LiteralPath $partial -Destination $target
    }
    if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Sha256) {
        throw "SHA-256 mismatch: $target; inspect the cache before retrying"
    }
    return $target
}

function Test-Ready([string]$Exe, [string]$Version, [string]$Sha256) {
    $marker = Join-Path (Split-Path -Parent $Exe) '.gx-shell-setup'
    Assert-LocalPath $Exe
    Assert-LocalPath $marker
    if (-not (Test-Path -LiteralPath $Exe -PathType Leaf) -or -not (Test-Path -LiteralPath $marker -PathType Leaf)) { return $false }
    $hash = (Get-FileHash -LiteralPath $Exe -Algorithm SHA256).Hash.ToLowerInvariant()
    return ([IO.File]::ReadAllText($marker).Trim() -eq "$Version $Sha256 $hash")
}

function Write-Receipt([string]$Exe, [string]$Version, [string]$Sha256) {
    Assert-LocalPath $Exe
    $hash = (Get-FileHash -LiteralPath $Exe -Algorithm SHA256).Hash.ToLowerInvariant()
    [IO.File]::WriteAllText((Join-Path (Split-Path -Parent $Exe) '.gx-shell-setup'), "$Version $Sha256 $hash`n")
}

function Assert-NewTarget([string]$Path) {
    Assert-LocalPath $Path
    if (Test-Path -LiteralPath $Path) { throw "Incomplete or unrecognized installation: $Path; inspect it before retrying (no automatic removal)" }
}

function Test-Tool([string]$Name, [string]$Exe, [string]$Version, [string]$Sha256, [string[]]$Arguments, [string]$Pattern) {
    if (-not (Test-Ready $Exe $Version $Sha256)) {
        Write-Host "MISSING $Name $Exe"
        return $false
    }
    try {
        $output = & $Exe @Arguments 2>&1 | Out-String
        if ($LASTEXITCODE -ne 0 -or $output -notmatch $Pattern) { throw "Unexpected version or exit code: $output" }
        Write-Host "PASS $Name $Version $Exe"
        return $true
    } catch {
        Write-Host "FAIL $Name $Exe : $_"
        return $false
    }
}

function Invoke-Doctor {
    $ok = Test-Tool 'python' $PythonExe $PythonVersion $PythonSha256 @('-I', '-B', '-c', 'import sys; print(sys.version.split()[0])') '^3\.12\.12\s'
    $ok = (Test-Tool 'actionlint' $ActionlintExe $ActionlintVersion $ActionlintSha256 @('-version') '^1\.7\.12\s') -and $ok
    if ($InnoSetup -or (Test-Path -LiteralPath $InnoDir)) {
        $ok = (Test-Tool 'ISCC' $IsccExe $InnoVersion $InnoSha256 @('--version') '7\.1\.0') -and $ok
    } else { Write-Host 'OPTIONAL Inno Setup: rerun with -InnoSetup' }
    return $ok
}

if ($env:OS -ne 'Windows_NT' -or [Environment]::GetEnvironmentVariable('PROCESSOR_ARCHITECTURE') -ne 'AMD64') {
    throw 'This bootstrap supports native Windows x64 only; use gx_shell_setup.sh on Linux x64'
}
if ($Check) {
    if (Invoke-Doctor) { exit 0 } else { exit 1 }
}

$RunRoot = Join-Path $RepoRoot ('.local/build/s' + [Guid]::NewGuid().ToString('N').Substring(0, 8))
$variables = @('TEMP', 'TMP', 'UV_PYTHON_INSTALL_DIR', 'UV_CACHE_DIR', 'UV_PYTHON_BIN_DIR', 'UV_PYTHON_INSTALL_REGISTRY', 'UV_PYTHON_DOWNLOADS', 'UV_OFFLINE', 'UV_NO_CACHE')
$saved = @{}
foreach ($name in $variables) { $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
try {
    foreach ($path in @($RunRoot, $CacheRoot, $ToolsRoot, (Join-Path $RepoRoot '.local/cache/uv'), (Join-Path $ToolsRoot 'python'), (Join-Path $ToolsRoot 'bin'))) {
        Assert-LocalPath $path
        New-Item -ItemType Directory -Force -Path $path | Out-Null
    }
    $env:TEMP = $RunRoot
    $env:TMP = $RunRoot
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $ToolsRoot 'python'
    $env:UV_CACHE_DIR = Join-Path $RepoRoot '.local/cache/uv'
    $env:UV_PYTHON_BIN_DIR = Join-Path $ToolsRoot 'bin'
    $env:UV_PYTHON_INSTALL_REGISTRY = 'false'
    $env:UV_PYTHON_DOWNLOADS = 'manual'
    $env:UV_OFFLINE = 'true'
    $env:UV_NO_CACHE = 'false'
    Write-Host "Setup evidence: $RunRoot"
    if (-not (Test-Ready $PythonExe $PythonVersion $PythonSha256)) {
        Assert-NewTarget $PythonDir
        $archive = Get-VerifiedDownload $PythonUrl $PythonSha256 "python-$PythonVersion-$PythonBuild-windows.tar.gz"
        $uv = 'C:\Users\guoxi\.local\bin\uv.exe'
        if (-not (Test-Path -LiteralPath $uv -PathType Leaf)) {
            $command = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue
            $uv = if ($command) { $command.Source } else { $null }
        }
        if ($uv) {
            # Supply a single, pinned entry. uv cannot pick a newer PBS build or access the network.
            $metadata = @{}
            $metadata[$PythonKey] = @{
                name = 'cpython'; arch = @{ family = 'x86_64'; variant = $null }; os = 'windows'; libc = 'none'
                major = 3; minor = 12; patch = 12; prerelease = ''; variant = $null; build = $PythonBuild
                url = ([Uri]$archive).AbsoluteUri; sha256 = $PythonSha256
            }
            $metadataPath = Join-Path $RunRoot 'python-downloads.json'
            [IO.File]::WriteAllText($metadataPath, ($metadata | ConvertTo-Json -Depth 5))
            $uvArgs = @('--no-config', '--offline', 'python', 'install', $PythonKey, '--no-bin', '--no-registry', '--python-downloads-json-url', ([Uri]$metadataPath).AbsoluteUri)
            # uv logs progress to stderr; do not turn it into a PowerShell 5.1 error.
            $uvProcess = Start-Process -FilePath $uv -ArgumentList $uvArgs -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput (Join-Path $RunRoot 'uv.log') -RedirectStandardError (Join-Path $RunRoot 'uv.stderr.log')
            Get-Content -LiteralPath (Join-Path $RunRoot 'uv.stderr.log') | Out-Host
            if ($uvProcess.ExitCode -ne 0) { throw 'uv installation failed; evidence retained (no unpinned fallback)' }
        } else {
            New-Item -ItemType Directory -Path $PythonDir | Out-Null
            & tar.exe -xzf $archive -C $PythonDir --strip-components=1
            if ($LASTEXITCODE -ne 0) { throw 'Python extraction failed' }
        }
        Write-Receipt $PythonExe $PythonVersion $PythonSha256
    }
    if (-not (Test-Ready $ActionlintExe $ActionlintVersion $ActionlintSha256)) {
        Assert-NewTarget $ActionlintDir
        $archive = Get-VerifiedDownload $ActionlintUrl $ActionlintSha256 "actionlint-$ActionlintVersion-windows.zip"
        Expand-Archive -LiteralPath $archive -DestinationPath $ActionlintDir
        Write-Receipt $ActionlintExe $ActionlintVersion $ActionlintSha256
    }
    if ($InnoSetup -and -not (Test-Ready $IsccExe $InnoVersion $InnoSha256)) {
        Assert-NewTarget $InnoDir
        $installer = Get-VerifiedDownload $InnoUrl $InnoSha256 "innosetup-$InnoVersion-x64.exe"
        $log = Join-Path $RunRoot 'innosetup.log'
        $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/CURRENTUSER', '/PORTABLE=1', "/DIR=`"$InnoDir`"", "/LOG=`"$log`"")
        $process = Start-Process -FilePath $installer -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
        if ($process.ExitCode -ne 0) { throw "Inno Setup exited $($process.ExitCode); see $log" }
        Write-Receipt $IsccExe $InnoVersion $InnoSha256
    }
    if (-not (Invoke-Doctor)) { throw 'Tool verification failed' }
    $envPath = Join-Path $ToolsRoot 'env.ps1'
    Assert-LocalPath $envPath
    $environmentScript = @'
# Dot-source this file; changes apply only to the current process.
$env:UV_PYTHON_INSTALL_DIR = Join-Path $PSScriptRoot 'python'
$env:UV_CACHE_DIR = Join-Path $PSScriptRoot '../cache/uv'
$env:UV_PYTHON_BIN_DIR = Join-Path $PSScriptRoot 'bin'
$env:UV_PYTHON_INSTALL_REGISTRY = 'false'
$env:GX_SHELL_PYTHON = Join-Path $PSScriptRoot 'python/cpython-3.12.12-windows-x86_64-none/python.exe'
$env:PATH = (Split-Path -Parent $env:GX_SHELL_PYTHON) + ';' + (Join-Path $PSScriptRoot 'actionlint') + ';' + $env:PATH
$localIscc = Join-Path $PSScriptRoot 'innosetup/ISCC.exe'
if (Test-Path -LiteralPath $localIscc) { $env:ISCC = $localIscc; $env:PATH = (Split-Path -Parent $localIscc) + ';' + $env:PATH }
'@
    [IO.File]::WriteAllText($envPath, $environmentScript + "`n")
    Write-Host "Ready. Dot-source: . '$envPath'"
} finally {
    foreach ($name in $variables) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
}

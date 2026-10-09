# GX Shell installer lifecycle smoke for a disposable GitHub-hosted Windows runner:
# silent install, PATH commands, the Ghostty GX and GX Zsh Start-menu shortcuts, GX Zsh (nested shell
# paths, /tmp, passwd home, zoxide data, bundled Linux tools, PowerShell bridge, app execution alias),
# the GX-managed herdr configuration, herdr identity / managed update / completion / real Zsh pane on
# the bundled ConPTY with Ctrl+C for MSYS and native programs, the bundled fonts, Ghostty GX starting
# GX Zsh on the bundled Mesa llvmpipe (GPU-less runner), occupied-file refusal, same-version reinstall,
# uninstall with user data preserved, a fresh install and uninstall, then optionally an upgrade over a
# used earlier GX Shell that bundled WezTerm GX (its program, shortcuts and App Paths entry go, user data
# stays) and its uninstall.
# Exit status: 0 when every check passes; any failed check throws (non-zero).
param(
    [Parameter(Mandatory = $true)][string]$Installer,
    [string]$Evidence = (Join-Path $PSScriptRoot '../.ui-evidence/gx-shell-windows'),
    [string]$Python = 'python',
    [string]$PreviousInstaller = '',
    [string]$HerdrProbe = $env:GX_SMOKE_HERDR_PROBE,
    [string]$ComponentsLock = $env:GX_SMOKE_COMPONENTS_LOCK,
    [string]$PackageManifest = $env:GX_SMOKE_PACKAGE_MANIFEST
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Text.UTF8Encoding]::new($false)
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
    throw 'Refusing to install on this machine: run only on a disposable GitHub-hosted runner.'
}
if (-not $HerdrProbe) { throw 'Set -HerdrProbe or GX_SMOKE_HERDR_PROBE to scripts/gx_probe_herdr.py in the locked external Oh My Zsh checkout.' }
if (-not $ComponentsLock) { throw 'Set -ComponentsLock or GX_SMOKE_COMPONENTS_LOCK to the lock used to assemble this package.' }
$Installer = (Resolve-Path -LiteralPath $Installer).Path
$HerdrProbe = (Resolve-Path -LiteralPath $HerdrProbe).Path
$ComponentsLock = (Resolve-Path -LiteralPath $ComponentsLock).Path
if (-not $PackageManifest) { $PackageManifest = "$Installer.manifest.json" }
$PackageManifest = (Resolve-Path -LiteralPath $PackageManifest).Path
$app = Join-Path $env:LOCALAPPDATA 'Programs\GXShell'
if (Test-Path -LiteralPath $app) { throw "GX Shell is already installed at $app" }
if (Test-Path -LiteralPath $Evidence) { throw "Evidence output must be new: $Evidence" }
New-Item -ItemType Directory -Path $Evidence -Force | Out-Null
$Evidence = (Resolve-Path -LiteralPath $Evidence).Path
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$provenanceCheck = @'
import hashlib
import json
from pathlib import Path
import subprocess
import sys

repo, artifact, metadata, lock_path, probe, evidence = map(Path, sys.argv[1:])
sys.path.insert(0, str(repo / 'scripts'))
import gx_shell_package as package

try:
    lock, checksum, raw_lock = package.read_components_lock(lock_path)
    info = package.read_json(metadata)
    package.require(info.get('platform') == 'windows', 'expected a Windows package manifest')
    package.verify_provenance(info, lock, checksum, info.get('source_commit'), allow_dirty=True)
    expected_name, _ = package.artifact_names(info['version'], 'windows', local=not info['publishable'])
    package.require(artifact.name == expected_name, 'package filename differs from provenance')
    record = info.get('artifacts', {}).get(artifact.name, {})
    artifact_hash = package.digest(artifact)
    package.require(record.get('sha256') == artifact_hash and record.get('size') == artifact.stat().st_size,
                    'package hash or size differs from provenance')
    probe = probe.resolve(strict=True)
    source = probe.parent.parent
    package.require(probe.name == 'gx_probe_herdr.py' and probe.parent.name == 'scripts',
                    'probe must be scripts/gx_probe_herdr.py from the locked external Oh My Zsh checkout')
    package.require(not source.is_relative_to(repo.resolve()), 'probe checkout must be outside the coordinator')
    def git(*args):
        return subprocess.check_output(['git', '-C', str(source), *args], stderr=subprocess.PIPE)
    package.require(Path(git('rev-parse', '--show-toplevel').decode().strip()).resolve() == source,
                    'probe source is not an independent checkout')
    common = Path(git('rev-parse', '--git-common-dir').decode().strip())
    package.require((source / common).resolve() == source / '.git', 'probe source shares Git metadata')
    revision = lock['components']['ohmyzsh']['revision']
    package.require(git('rev-parse', 'HEAD').decode().strip() == revision, 'probe checkout HEAD differs from locked Oh My Zsh revision')
    expected_probe = git('show', revision + ':scripts/gx_probe_herdr.py')
    probe_bytes = probe.read_bytes()
    package.require(probe_bytes.replace(b'\r\n', b'\n') == expected_probe.replace(b'\r\n', b'\n'),
                    'probe contents differ from the locked Oh My Zsh commit')
    herdr = info['components']['herdr']
    expected_version = f"herdr {herdr['version']}-gx.{herdr['package_manager']}.{herdr['revision']}"
    receipt = {
        'schema': 1, 'platform': 'windows', 'status': 'PREFLIGHT_PASS',
        'package': {'path': str(artifact.resolve()), 'sha256': artifact_hash, 'version': info['version']},
        'package_manifest': {'path': str(metadata.resolve()), 'sha256': package.digest(metadata)},
        'coordinator': info['coordinator'], 'components_lock_digest': checksum,
        'components': info['components'], 'stages': info['stages'],
        'publishable': info['publishable'], 'local_build': info['local_build'],
        'herdr_probe': {'path': str(probe), 'repository': 'gx0404/ohmyzsh', 'revision': revision,
                        'sha256': hashlib.sha256(probe_bytes).hexdigest()},
        'expected_herdr_version': expected_version, 'legacy_release_upgrade': 'NOT_RUN',
    }
    (evidence / 'package-manifest.json').write_bytes(metadata.read_bytes())
    (evidence / 'components.lock.json').write_bytes(raw_lock)
    (evidence / 'smoke-provenance.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
except (OSError, ValueError, KeyError, TypeError, package.PackageError, subprocess.SubprocessError) as error:
    raise SystemExit(f'smoke provenance failed: {error}')
'@
& $Python -B -c $provenanceCheck $repo $Installer $PackageManifest $ComponentsLock $HerdrProbe $Evidence
if ($LASTEXITCODE -ne 0) { throw 'Smoke provenance preflight failed; no installer has been run.' }
$smokeProvenance = Get-Content -LiteralPath (Join-Path $Evidence 'smoke-provenance.json') -Raw | ConvertFrom-Json

function Step([string]$Name) { Write-Host "=== $Name" }
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}
function Initialize-SetupJob {
    if ('GxSmokeProcessJob' -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

public sealed class GxSmokeProcessJob : IDisposable {
    [StructLayout(LayoutKind.Sequential)] struct BasicLimits {
        public long ProcessTime, JobTime;
        public uint Flags;
        public UIntPtr MinimumWorkingSet, MaximumWorkingSet;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass, SchedulingClass;
    }
    [StructLayout(LayoutKind.Sequential)] struct IoCounters {
        public ulong ReadOperations, WriteOperations, OtherOperations, ReadBytes, WriteBytes, OtherBytes;
    }
    [StructLayout(LayoutKind.Sequential)] struct ExtendedLimits {
        public BasicLimits Basic;
        public IoCounters Io;
        public UIntPtr ProcessMemory, JobMemory, PeakProcessMemory, PeakJobMemory;
    }
    [StructLayout(LayoutKind.Sequential)] struct Accounting {
        public long UserTime, KernelTime, PeriodUserTime, PeriodKernelTime;
        public uint PageFaults, TotalProcesses, ActiveProcesses, TerminatedProcesses;
    }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)] struct StartupInfo {
        public int Size;
        public string Reserved, Desktop, Title;
        public uint X, Y, XSize, YSize, XChars, YChars, Fill, Flags;
        public ushort ShowWindow, ReservedSize;
        public IntPtr ReservedPointer, Input, Output, Error;
    }
    [StructLayout(LayoutKind.Sequential)] struct ProcessInfo {
        public IntPtr Process, Thread;
        public uint ProcessId, ThreadId;
    }
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern IntPtr CreateJobObject(IntPtr attributes, string name);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool SetInformationJobObject(IntPtr job, int kind, ref ExtendedLimits info, uint size);
    [DllImport("kernel32.dll", EntryPoint = "QueryInformationJobObject", SetLastError = true)]
    static extern bool QueryAccounting(IntPtr job, int kind, out Accounting info, uint size, IntPtr returned);
    [DllImport("kernel32.dll", EntryPoint = "QueryInformationJobObject", SetLastError = true)]
    static extern bool QueryIds(IntPtr job, int kind, IntPtr info, uint size, IntPtr returned);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern bool CreateProcess(string application, StringBuilder command, IntPtr processAttributes,
        IntPtr threadAttributes, bool inheritHandles, uint flags, IntPtr environment, string directory,
        ref StartupInfo startup, out ProcessInfo process);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    [DllImport("kernel32.dll", SetLastError = true)] static extern uint ResumeThread(IntPtr thread);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool TerminateJobObject(IntPtr job, uint code);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool TerminateProcess(IntPtr process, uint code);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool GetExitCodeProcess(IntPtr process, out uint code);
    [DllImport("kernel32.dll")] static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);

    IntPtr job, root;
    public uint RootProcessId { get; private set; }
    static void Check(bool success) { if (!success) throw new Win32Exception(Marshal.GetLastWin32Error()); }

    public GxSmokeProcessJob(string file, string arguments, string directory) {
        if (!System.IO.Path.IsPathFullyQualified(file) || file.Contains("\""))
            throw new ArgumentException("Executable must be an absolute path without quotes");
        var process = new ProcessInfo();
        try {
            job = CreateJobObject(IntPtr.Zero, null);
            Check(job != IntPtr.Zero);
            var limits = new ExtendedLimits();
            limits.Basic.Flags = 0x2000; // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway.
            Check(SetInformationJobObject(job, 9, ref limits, (uint)Marshal.SizeOf<ExtendedLimits>()));
            var startup = new StartupInfo();
            startup.Size = Marshal.SizeOf<StartupInfo>();
            Check(CreateProcess(file, new StringBuilder("\"" + file + "\" " + arguments),
                IntPtr.Zero, IntPtr.Zero, false, 0x4, IntPtr.Zero, directory, ref startup, out process));
            root = process.Process;
            RootProcessId = process.ProcessId;
            Check(AssignProcessToJobObject(job, root));
            Check(ResumeThread(process.Thread) != uint.MaxValue);
        } catch {
            if (process.Process != IntPtr.Zero) {
                TerminateProcess(process.Process, 1);
                WaitForSingleObject(process.Process, 5000);
            }
            Dispose();
            throw;
        } finally {
            if (process.Thread != IntPtr.Zero) CloseHandle(process.Thread);
        }
    }
    Accounting ReadAccounting() {
        Accounting result;
        Check(QueryAccounting(job, 1, out result, (uint)Marshal.SizeOf<Accounting>(), IntPtr.Zero));
        return result;
    }
    public uint ActiveProcesses { get { return ReadAccounting().ActiveProcesses; } }
    public uint TotalProcesses { get { return ReadAccounting().TotalProcesses; } }
    public bool WaitForEmpty(int milliseconds) {
        var watch = Stopwatch.StartNew();
        while (ActiveProcesses != 0) {
            if (watch.ElapsedMilliseconds >= milliseconds) return false;
            Thread.Sleep(50);
        }
        return true;
    }
    public int[] ProcessIds() {
        for (int capacity = 64; capacity <= 65536; capacity *= 2) {
            int size = 8 + capacity * IntPtr.Size;
            IntPtr buffer = Marshal.AllocHGlobal(size);
            try {
                if (!QueryIds(job, 3, buffer, (uint)size, IntPtr.Zero)) {
                    int error = Marshal.GetLastWin32Error();
                    if (error == 234) continue;
                    throw new Win32Exception(error);
                }
                int count = Marshal.ReadInt32(buffer, 4);
                if (count < 0 || count > capacity) throw new InvalidOperationException("Invalid job process list");
                var result = new int[count];
                for (int i = 0; i < count; i++)
                    result[i] = checked((int)Marshal.ReadIntPtr(buffer, 8 + i * IntPtr.Size).ToInt64());
                return result;
            } finally { Marshal.FreeHGlobal(buffer); }
        }
        throw new InvalidOperationException("Job process list exceeds diagnostic limit");
    }
    public uint ExitCode {
        get {
            if (WaitForSingleObject(root, 0) != 0) throw new InvalidOperationException("Root process has not exited");
            uint code;
            Check(GetExitCodeProcess(root, out code));
            return code;
        }
    }
    public void Terminate() { Check(TerminateJobObject(job, 1460)); }
    public void Dispose() {
        if (job != IntPtr.Zero) { CloseHandle(job); job = IntPtr.Zero; }
        if (root != IntPtr.Zero) { CloseHandle(root); root = IntPtr.Zero; }
        GC.SuppressFinalize(this);
    }
    ~GxSmokeProcessJob() { Dispose(); }
}
'@
}
function Invoke-OwnedProcessTree([string]$File, [string]$Arguments,
    [ValidatePattern('^[A-Za-z0-9._-]+$')][string]$Label, [ValidateRange(1, 1800)][int]$Seconds) {
    Initialize-SetupJob
    $job = $null
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $record = [ordered]@{ status = 'STARTING'; file = $File; arguments = $Arguments; timeout_seconds = $Seconds;
        started_utc = [DateTime]::UtcNow.ToString('o'); root_pid = $null; exit_code = $null;
        total_processes = 0; timeout_process_ids = @(); timeout_processes = @();
        cleanup_complete = $false; remaining_process_ids = @(); error = $null; elapsed_seconds = 0 }
    try {
        $job = [GxSmokeProcessJob]::new($File, $Arguments, $Evidence)
        $record.root_pid = $job.RootProcessId
        $record.status = 'RUNNING'
        if (-not $job.WaitForEmpty($Seconds * 1000)) {
            $record.status = 'TIMEOUT'
            try {
                $record.timeout_process_ids = @($job.ProcessIds())
                $record.timeout_processes = @(foreach ($processId in $record.timeout_process_ids) {
                    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
                    if ($process) {
                        try { [pscustomobject]@{ pid = $processId; name = $process.ProcessName; path = $process.Path; start_time = $process.StartTime.ToUniversalTime().ToString('o') } }
                        finally { $process.Dispose() }
                    }
                })
            } catch { $record.error = "Timeout diagnostics: $_" }
            throw [TimeoutException]::new("$Label exceeded $Seconds seconds; this is a smoke failure, not an occupied-file refusal.")
        }
        $record.exit_code = $job.ExitCode
        $record.total_processes = $job.TotalProcesses
        $record.status = 'EXITED'
        return [pscustomobject]@{ ExitCode = $record.exit_code; RootProcessId = $record.root_pid }
    } catch {
        if ($record.status -ne 'TIMEOUT') { $record.status = 'ERROR' }
        $record.error = "$($record.error) $_".Trim()
        throw
    } finally {
        try {
            if ($job) {
                if ($record.status -ne 'EXITED') { $job.Terminate() }
                $record.cleanup_complete = $job.WaitForEmpty(10000)
                $record.remaining_process_ids = @($job.ProcessIds())
                $record.total_processes = $job.TotalProcesses
                if (-not $record.cleanup_complete) { throw "$Label process-tree cleanup exceeded 10 seconds" }
            }
        } finally {
            if ($job) { $job.Dispose() }
            $record.elapsed_seconds = $watch.Elapsed.TotalSeconds
            $record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $Evidence "$Label-process.json") -Encoding utf8
        }
    }
}
function Run-Setup([string]$File, [string]$Label, [string[]]$Extra = @(),
    [ValidateRange(1, 1800)][int]$Seconds = 600, [switch]$ExpectRefusal) {
    $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/LOG=`"$(Join-Path $Evidence "$Label.log")`"") + $Extra
    $process = Invoke-OwnedProcessTree $File ($arguments -join ' ') $Label $Seconds
    if ($ExpectRefusal) {
        if ($process.ExitCode -eq 0) { throw "$Label did not refuse an occupied runtime file" }
    } elseif ($process.ExitCode -ne 0) { throw "$Label exited with $($process.ExitCode)" }
}
function Capture([string]$Name, [string]$File, [string[]]$Arguments) {
    $text = & $File @Arguments 2>&1 | Out-String
    $code = $LASTEXITCODE
    Set-Content -LiteralPath (Join-Path $Evidence $Name) -Value $text -Encoding utf8
    Write-Host $text.TrimEnd()
    return [pscustomobject]@{ Text = $text; Code = $code }
}
# Like Capture, but a run that outlives $Seconds has its whole process tree killed and fails the smoke.
function Capture-Bounded([string]$Name, [string]$File, [string[]]$Arguments, [int]$Seconds) {
    $info = [Diagnostics.ProcessStartInfo]::new($File)
    foreach ($argument in $Arguments) { $info.ArgumentList.Add($argument) }
    $info.UseShellExecute = $false
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.StandardOutputEncoding = [Text.UTF8Encoding]::new($false)
    $info.StandardErrorEncoding = [Text.UTF8Encoding]::new($false)
    $process = [Diagnostics.Process]::Start($info)
    $reads = [Threading.Tasks.Task[]]@($process.StandardOutput.ReadToEndAsync(), $process.StandardError.ReadToEndAsync())
    $finished = $process.WaitForExit($Seconds * 1000)
    if (-not $finished) {
        $process.Kill($true)
        [void]$process.WaitForExit(10000)
    }
    $drained = [Threading.Tasks.Task]::WaitAll($reads, 15000)
    $text = if ($drained) { $reads[0].Result + $reads[1].Result } else { "(output pipes are still held open)`n" }
    Set-Content -LiteralPath (Join-Path $Evidence $Name) -Value $text -Encoding utf8
    Write-Host $text.TrimEnd()
    Assert ($finished -and $drained) "$Name did not finish within $Seconds s; its process tree was killed"
    return [pscustomobject]@{ Text = $text; Code = $process.ExitCode }
}
function Config-Files([string]$Root) {
    $files = @{}
    if (-not (Test-Path -LiteralPath $Root)) { return $files }
    foreach ($file in Get-ChildItem -LiteralPath $Root -Recurse -File -Force) {
        $files[[IO.Path]::GetRelativePath($Root, $file.FullName)] = (Get-FileHash -LiteralPath $file.FullName).Hash
    }
    return $files
}
function Assert([bool]$Condition, [string]$Message) { if (-not $Condition) { throw $Message } }
function Owned-Fonts {
    $path = 'HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Fonts'
    if (-not (Test-Path -LiteralPath $path)) { return @() }
    $key = Get-Item -LiteralPath $path
    try { return @($key.GetValueNames() | Where-Object { $expectedFontKeys.ContainsKey($_) }) }
    finally { $key.Dispose() }
}
function Owned-PathEntries {
    $bin = Join-Path $app 'bin'
    return @([Environment]::GetEnvironmentVariable('Path', 'User') -split ';' | Where-Object { $_.TrimEnd('\') -ieq $bin })
}
function Shortcut([string]$Path) { return (New-Object -ComObject WScript.Shell).CreateShortcut($Path) }
$programs = [Environment]::GetFolderPath('Programs')
$desktop = [Environment]::GetFolderPath('DesktopDirectory')
$ghosttyExe = Join-Path $app 'ghostty\ghostty.exe'
$gxZshExe = Join-Path $app 'bin\gx-zsh.exe'
$appPathKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\ghostty.exe'
$oldAppPathKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\wezterm-gx.exe'
# "Ghostty GX" relies on Ghostty GX finding {app}\bin\gx-zsh.exe next to its directory; "GX Zsh" names GX Zsh
# explicitly with -e, so it opens GX Zsh even when another default shell is configured.
function Assert-Shortcuts([string]$Label) {
    $ghostty = Shortcut (Join-Path $programs 'Ghostty GX.lnk')
    Assert ($ghostty.TargetPath -ieq $ghosttyExe -and $ghostty.Arguments -eq '' -and $ghostty.WorkingDirectory -ieq $env:USERPROFILE) "${Label}: Ghostty GX shortcut runs: $($ghostty.TargetPath) $($ghostty.Arguments)"
    $zsh = Shortcut (Join-Path $programs 'GX Zsh.lnk')
    Assert ($zsh.TargetPath -ieq $ghosttyExe -and $zsh.Arguments -ieq "-e `"$gxZshExe`"" -and $zsh.WorkingDirectory -ieq $env:USERPROFILE) "${Label}: GX Zsh shortcut runs: $($zsh.TargetPath) $($zsh.Arguments)"
}
# Sets (or, for $null, removes) process environment variables for the programs started next and returns the
# previous values, so that passing the result back restores them.
function Set-Environment([hashtable]$Values) {
    $previous = @{}
    foreach ($key in $Values.Keys) {
        $previous[$key] = [Environment]::GetEnvironmentVariable($key)
        # Not [Environment]::SetEnvironmentVariable: PowerShell passes $null as '', which leaves an empty variable.
        if ($null -eq $Values[$key]) { Remove-Item -LiteralPath "Env:$key" -ErrorAction SilentlyContinue }
        else { Set-Item -LiteralPath "Env:$key" -Value $Values[$key] }
    }
    return $previous
}
$herdrMarker = '# gx-shell: manages [terminal] default_shell and shell_mode; delete this line to manage them yourself'
# The herdr configuration GX Zsh created (or adopted from an older release) marks [terminal] as GX-managed and
# starts the bundled Zsh as a login shell through a native, backslash-only path.
function Assert-HerdrConfig([string]$Label, [string]$LocalAppData) {
    $path = Join-Path $LocalAppData 'ohmyzsh-gx\profile\herdr\config.toml'
    Assert (Test-Path -LiteralPath $path -PathType Leaf) "${Label}: GX Zsh did not create $path"
    Copy-Item -LiteralPath $path -Destination (Join-Path $Evidence "$Label-herdr-config.toml")
    $text = [IO.File]::ReadAllText($path)
    $shell = [regex]::Match($text, '(?m)^[ \t]*default_shell[ \t]*=[ \t]*"((?:[^"\\]|\\.)*)"')
    $value = $shell.Groups[1].Value -replace '\\(.)', '$1'
    Assert (($text -split '\r?\n') -ccontains $herdrMarker) "${Label}: the herdr configuration lacks the GX marker line"
    Assert ($shell.Success -and $value -ieq (Join-Path $app 'runtime\msys64\usr\bin\zsh.exe') -and -not $value.Contains('/')) "${Label}: herdr default_shell is '$value', not the bundled Zsh as a backslash-only path"
    Assert ($text -cmatch '(?m)^[ \t]*shell_mode[ \t]*=[ \t]*"login"') "${Label}: herdr does not start Zsh as a login shell"
}
# A starting GX Zsh keeps forking MSYS2 children, so one pass can miss some; the installer then (correctly)
# refuses because msys-2.0.dll is in use. Repeat until nothing from the installation has run for a second.
function Stop-Installation {
    Assert ($env:GITHUB_ACTIONS -eq 'true' -and $env:RUNNER_ENVIRONMENT -eq 'github-hosted') 'process cleanup is hosted-runner only'
    $quiet = 0
    $running = @()
    $prefix = $app.TrimEnd('\') + '\'
    for ($i = 0; $i -lt 60 -and $quiet -lt 2; $i++) {
        $running = @(Get-Process | Where-Object { $_.Path -and $_.Path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) })
        if ($running.Count) { $quiet = 0; $running | Stop-Process -Force -ErrorAction SilentlyContinue } else { $quiet++ }
        Start-Sleep -Milliseconds 500
    }
    Assert ($quiet -ge 2) "processes from $app keep running: $(@($running | ForEach-Object { $_.Path }) -join ', ')"
}
function Run-Uninstall([string]$Label) {
    $userBefore = UserData-State
    Run-Setup (Join-Path $app 'unins000.exe') $Label -Seconds 180
    for ($i = 0; $i -lt 120 -and (Test-Path -LiteralPath $app); $i++) { Start-Sleep -Milliseconds 500 }
    $left = @(Get-ChildItem -LiteralPath $app -Recurse -Force -Name -ErrorAction SilentlyContinue | Select-Object -First 50)
    Assert (-not (Test-Path -LiteralPath $app)) "$app remains after uninstall; remaining files: $($left -join ', ')"
    Assert (@(Owned-PathEntries).Count -eq 0) 'owned PATH entry remains'
    Assert (@(Owned-Fonts).Count -eq 0) 'owned font registrations remain'
    Assert (-not (Test-Path -LiteralPath 'HKCU:\Software\GX Shell')) 'ownership registry key remains'
    Assert (-not (Test-Path -LiteralPath $appPathKey)) 'App Paths\ghostty.exe registration remains'
    foreach ($path in $ownedShortcuts) { Assert (-not (Test-Path -LiteralPath $path)) "owned shortcut remains: $path" }
    Assert-UserData $userBefore $Label
    Assert-NonOwnedState $Label
}
function Save-Screenshot([string]$Name) {
    $bitmap = $null
    $graphics = $null
    try {
        Add-Type -AssemblyName System.Windows.Forms, System.Drawing
        $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
        Assert ($bounds.Width -ge 320 -and $bounds.Height -ge 200) 'no usable desktop for screenshot'
        $bitmap = [System.Drawing.Bitmap]::new($bounds.Width, $bounds.Height)
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
        $path = Join-Path $Evidence $Name
        $bitmap.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
        Assert ((Get-Item -LiteralPath $path).Length -gt 0) 'empty screenshot'
    } catch {
        throw "Screenshot failed ($Name): $_"
    } finally {
        if ($graphics) { $graphics.Dispose() }
        if ($bitmap) { $bitmap.Dispose() }
    }
}
function Save-GuiDiagnostics([string]$Label) {
    Get-CimInstance Win32_Process |
        Where-Object { $_.Name -match '^(ghostty|gx-zsh|zsh|OpenConsole|conhost|pwsh|powershell)' } |
        Sort-Object ProcessId |
        Format-List ProcessId, ParentProcessId, Name, ExecutablePath, CommandLine | Out-String -Width 4096 |
        Set-Content -LiteralPath (Join-Path $Evidence "$Label-processes.txt") -Encoding utf8
    $logs = Join-Path $Evidence "$Label-ghostty-logs"
    New-Item -ItemType Directory -Force -Path $logs | Out-Null
    Get-ChildItem -Path (Join-Path $ghosttyLogs 'ghostty.log*') -ErrorAction SilentlyContinue |
        Copy-Item -Destination $logs -ErrorAction SilentlyContinue
}
function Assert-MapSame([hashtable]$Before, [hashtable]$After, [string]$Label) {
    Assert ($Before.Count -eq $After.Count) "${Label}: file/value set changed"
    foreach ($name in $Before.Keys) {
        Assert ($After.ContainsKey($name) -and $After[$name] -ceq $Before[$name]) "${Label}: changed or missing $name"
    }
}
function Registry-Values([string]$Path, [string[]]$Names = @()) {
    $values = @{}
    if (Test-Path -LiteralPath $Path) {
        $key = Get-Item -LiteralPath $Path
        try {
            $available = @($key.GetValueNames())
            $selected = if ($Names.Count) { $Names } else { $available }
            foreach ($name in $selected) {
                if ($name -notin $available) { continue }
                $values[$name] = [ordered]@{ Kind = $key.GetValueKind($name).ToString(); Value = $key.GetValue($name, $null, [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames) } | ConvertTo-Json -Compress
            }
        } finally { $key.Dispose() }
    }
    return $values
}
function NonOwned-State {
    $state = @{}
    $userValues = Registry-Values 'HKCU:\Environment' @('Path')
    $userPath = if ($userValues.ContainsKey('Path')) { ($userValues['Path'] | ConvertFrom-Json).Value } else { '' }
    $entries = @($userPath -split ';' | Where-Object { $_ -ne '' -and $_.Trim().Trim('"').TrimEnd('\') -ine (Join-Path $app 'bin') })
    $state['user-path-entries'] = ConvertTo-Json -InputObject $entries -Compress
    $machineValues = Registry-Values 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Environment' @('Path')
    $state['machine-path'] = $machineValues['Path']
    foreach ($entry in (Registry-Values 'HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Fonts').GetEnumerator()) {
        if (-not $expectedFontKeys.ContainsKey($entry.Key)) { $state['font:' + $entry.Key] = $entry.Value }
    }
    $fontFolder = Join-Path $env:LOCALAPPDATA 'Microsoft\Windows\Fonts'
    if (Test-Path -LiteralPath $fontFolder) {
        foreach ($entry in (Config-Files $fontFolder).GetEnumerator()) { $state['font-file:' + $entry.Key] = $entry.Value }
    }
    foreach ($folder in @($programs, $desktop)) {
        foreach ($file in Get-ChildItem -LiteralPath $folder -Recurse -File -Force) {
            if ($file.Extension -notin '.lnk', '.url' -or $ownedShortcuts -contains $file.FullName) { continue }
            $state['shortcut:' + $file.FullName] = (Get-FileHash -LiteralPath $file.FullName).Hash
        }
    }
    foreach ($entry in (Registry-Values $oldAppPathKey).GetEnumerator()) { $state['app-path:wezterm-gx.exe:' + $entry.Key] = $entry.Value }
    return $state
}
function Assert-NonOwnedState([string]$Label) {
    $after = NonOwned-State
    $after | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $Evidence "$Label-nonowned.json") -Encoding utf8
    Assert-MapSame $hostBaseline $after "${Label}: non-owned PATH/font/shortcut baseline"
}
# User data GX Shell must never touch: the GX Zsh profile, the Ghostty GX configuration next to its logs, and
# the configuration an earlier WezTerm GX left behind (never read, migrated or removed).
function UserData-State {
    $state = @{}
    foreach ($entry in (Config-Files $profile).GetEnumerator()) { $state['profile/' + $entry.Key] = $entry.Value }
    foreach ($entry in (Config-Files $ghosttyConfig).GetEnumerator()) {
        if ($entry.Key -notmatch '^logs[\\/]') { $state['ghostty/' + $entry.Key] = $entry.Value }
    }
    foreach ($entry in (Config-Files $weztermConfig).GetEnumerator()) { $state['wezterm/' + $entry.Key] = $entry.Value }
    return $state
}
function Assert-UserData([hashtable]$Before, [string]$Label) {
    $after = UserData-State
    @{ Before = $Before; After = $after } | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $Evidence "$Label-user-data.json") -Encoding utf8
    Assert-MapSame $Before $after "${Label}: configuration and full GX profile contents"
}
function Assert-InstalledState([string]$Label) {
    Assert (@(Owned-PathEntries).Count -eq 1) "${Label}: expected exactly one owned PATH entry"
    Assert ((Get-ItemProperty -LiteralPath 'HKCU:\Software\GX Shell').InstallDir -ieq $app) "${Label}: ownership directory changed"
    $fontKey = Get-Item -LiteralPath 'HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Fonts'
    $ownerKey = Get-Item -LiteralPath 'HKCU:\Software\GX Shell\Fonts'
    try {
        Assert (@($ownerKey.GetValueNames()).Count -eq $expectedFontKeys.Count) "${Label}: font ownership set differs"
        foreach ($name in $expectedFontKeys.Keys) {
            $record = $expectedFontKeys[$name]
            $path = Join-Path $app ("fonts/" + $record.Name)
            Assert ($fontKey.GetValue($name) -ceq $path -and $ownerKey.GetValue($name) -ceq $path) "${Label}: font registration changed: $name"
            Assert ((Get-FileHash -LiteralPath $path).Hash -ieq $record.Sha256) "${Label}: font bytes differ: $name"
        }
    } finally { $fontKey.Dispose(); $ownerKey.Dispose() }
    Assert-Shortcuts $Label
    $registered = (Get-Item -LiteralPath $appPathKey).GetValue('')
    Assert ($registered -ieq $ghosttyExe) "${Label}: App Paths\ghostty.exe registration changed: $registered"
    Assert (-not (Test-Path -LiteralPath $ownedShortcuts[2])) "${Label}: unchecked desktop shortcut was created"
    Assert (-not (Test-Path -LiteralPath (Join-Path $app 'wezterm'))) "${Label}: the WezTerm GX of an earlier GX Shell is still installed"
    Assert-NonOwnedState $Label
}
function Runtime-Recheck([string]$Label) {
    Refresh-Path
    foreach ($name in 'gx-zsh', 'herdr') {
        $resolved = (Get-Command $name -CommandType Application | Select-Object -First 1).Source
        Assert ($resolved -ieq (Join-Path $app "bin/$name.exe")) "${Label}: $name resolves outside installation"
    }
    Assert-InstalledState $Label
    $shell = Capture-Bounded "$Label-zsh.txt" $gxZshExe @('-c',
        'print -r -- "GX_RECHECK zsh=$ZSH_VERSION omz=$ZSH"; print -r -- "profile=$GX_PROFILE_DIR"; print -r -- "user=${GX_SMOKE_PRESERVE-unset}"') 180
    Assert ($shell.Code -eq 0 -and $shell.Text -match 'GX_RECHECK zsh=5\.9\.2 omz=\S*/share/ohmyzsh-gx' -and $shell.Text -match 'user=gx-user-data-kept') "${Label}: GX Zsh or preserved user layer did not run"
    Assert-HerdrConfig $Label $env:LOCALAPPDATA
    $version = Capture-Bounded "$Label-herdr.txt" (Join-Path $app 'bin/herdr.exe') @('--version') 60
    Assert ($version.Code -eq 0 -and $version.Text.Trim() -ceq $smokeProvenance.expected_herdr_version) "${Label}: herdr identity differs"
    Run-HostedGuiWindow $Label 'GX Zsh.lnk'
    $protectedAfter = @{}
    foreach ($path in $protectedUserFiles.Keys) { $protectedAfter[$path] = (Get-FileHash -LiteralPath $path).Hash }
    Assert-MapSame $protectedUserFiles $protectedAfter "${Label}: runtime changed protected user files"
    Assert-NonOwnedState "$Label-runtime"
}
$expectedFontKeys = @{}
foreach ($item in @($smokeProvenance.stages.gx_ghostty.files) + @($smokeProvenance.stages.ohmyzsh.payload)) {
    if ($item.path -match '^fonts/([^/]+\.(ttf|ttc))$') {
        $name = $Matches[1]
        $key = "GXShell $name (TrueType)"
        if ($expectedFontKeys.ContainsKey($key)) { Assert ($expectedFontKeys[$key].Sha256 -ceq $item.sha256) "Conflicting font receipt: $name" }
        $expectedFontKeys[$key] = @{ Name = $name; Sha256 = $item.sha256 }
    }
}
Assert ($expectedFontKeys.Count -eq 8) 'stage receipts do not describe the eight expected Windows fonts'
$ownedShortcuts = @(
    (Join-Path $programs 'Ghostty GX.lnk'),
    (Join-Path $programs 'GX Zsh.lnk'),
    (Join-Path $desktop 'Ghostty GX.lnk')
)
foreach ($path in $ownedShortcuts) { Assert (-not (Test-Path -LiteralPath $path)) "Refusing to overwrite pre-existing shortcut: $path" }
Assert (-not (Test-Path -LiteralPath 'HKCU:\Software\GX Shell')) 'pre-existing ownership registry key'
Assert (-not (Test-Path -LiteralPath $appPathKey)) 'pre-existing App Paths\ghostty.exe registration'
$existingFonts = Registry-Values 'HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Fonts'
foreach ($name in $expectedFontKeys.Keys) { Assert (-not $existingFonts.ContainsKey($name)) "pre-existing owned font name: $name" }
$profile = Join-Path $env:LOCALAPPDATA 'ohmyzsh-gx\profile'
$ghosttyConfig = Join-Path $env:LOCALAPPDATA 'ghostty'
$ghosttyLogs = Join-Path $ghosttyConfig 'logs'
$weztermConfig = Join-Path $env:USERPROFILE '.config\wezterm'

Step 'user data of Ghostty GX and of an earlier WezTerm GX exists before the installation'
foreach ($path in $ghosttyConfig, $weztermConfig) { Assert (-not (Test-Path -LiteralPath $path)) "Refusing to overwrite existing user data: $path" }
New-Item -ItemType Directory -Path $ghosttyConfig, $weztermConfig | Out-Null
Set-Content -LiteralPath (Join-Path $ghosttyConfig 'config.ghostty') -Value 'font-size = 13' -Encoding utf8
Set-Content -LiteralPath (Join-Path $weztermConfig 'wezterm.lua') -Value '-- WezTerm GX configuration left by an earlier GX Shell' -Encoding utf8
$hostBaseline = NonOwned-State
$hostBaseline | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $Evidence 'before-install-nonowned.json') -Encoding utf8

Step 'install'
Run-Setup $Installer 'install'
Assert (Test-Path -LiteralPath (Join-Path $app 'unins000.exe')) 'uninstaller missing'
$installDir = (Get-ItemProperty -LiteralPath 'HKCU:\Software\GX Shell').InstallDir
Assert ($installDir -ieq $app) 'installation ownership not recorded'

Step 'PATH resolves the GX entry points in a fresh environment'
Refresh-Path
foreach ($name in 'gx-zsh', 'herdr') {
    $resolved = (Get-Command $name -CommandType Application | Select-Object -First 1).Source
    Assert ($resolved -ieq (Join-Path $app "bin\$name.exe")) "$name resolved to $resolved"
}

Step 'the Ghostty GX and GX Zsh Start-menu shortcuts and App Paths start the installed Ghostty GX'
Assert-Shortcuts 'install'
Assert ((Get-Item -LiteralPath $appPathKey).GetValue('') -ieq $ghosttyExe) 'App Paths\ghostty.exe does not point to the installed Ghostty GX'

Step 'GX Zsh with Oh My Zsh; its first start creates the GX-managed herdr configuration'
$zsh = Capture 'gx-zsh.txt' $gxZshExe @('-c', 'print -r -- "zsh=$ZSH_VERSION omz=$ZSH"')
Assert ($zsh.Code -eq 0 -and $zsh.Text -match 'zsh=5\.9\.2 omz=\S*/share/ohmyzsh-gx') 'GX Zsh did not load Oh My Zsh from the package'
Assert-HerdrConfig 'install' $env:LOCALAPPDATA

Step 'GX Zsh on Windows: nested shell paths, /tmp, the passwd home, zoxide data and the bundled Linux tools'
# One login shell for every path check: each GX Zsh start costs seconds on a hosted runner. The nested gx-zsh
# receives the variables MSYS2 converted to Windows form and must still see POSIX paths and its theme cache.
# The tools must come from the private runtime (/usr/bin), not from a Git for Windows directory on PATH, and
# must run: a missing DLL only shows when the program starts.
$checks = @(
    'print -r -- "profile=$GX_PROFILE_DIR"', 'print -r -- "custom=$ZSH_CUSTOM"', 'print -r -- "home=$HOME"',
    'print -r -- "passwd=$(getent passwd $USERNAME | cut -d: -f6)"', 'print -r -- "zo=$_ZO_DATA_DIR"',
    'tmp=$(mktemp /tmp/gx-smoke.XXXXXX) && print -r -- gx-tmp-ok > $tmp && print -r -- "tmp=$(<$tmp)"; rm -f -- $tmp',
    'broken=(); for spec in "diff --version" "patch --version" "unzip -v" "zip -v" "tree --version" "bc --version" "top --version" "vim --version" "rsync --version" "jq --version"; do tool=${spec%% *}; [[ ${commands[$tool]-} == /usr/bin/* ]] && ${=spec} >/dev/null 2>&1 </dev/null || broken+=($tool); done',
    'print -r -- "tools-broken=${broken[*]}"',
    'gx-zsh -c ''print -r -- "nested-custom=$ZSH_CUSTOM"; print -r -- "nested-p10k=$POWERLEVEL9K_INSTALLATION_DIR"; print -r -- "nested-fpath=${#${fpath:#/*}}"'''
) -join '; '
$paths = Capture-Bounded 'gx-zsh-windows.txt' $gxZshExe @('-c', $checks) 300
$seen = @{}
foreach ($line in $paths.Text -split '\r?\n') { if ($line -match '^([a-z0-9-]+)=(.*)$') { $seen[$Matches[1]] = $Matches[2] } }
Assert ($paths.Code -eq 0 -and $seen['profile'] -like '/*' -and $seen['custom'] -like '/*') "GX Zsh did not report POSIX paths: $($paths.Text)"
Assert ($seen['nested-custom'] -ceq $seen['custom']) "nested gx-zsh sees ZSH_CUSTOM=$($seen['nested-custom']), expected $($seen['custom'])"
$themes = '^' + [regex]::Escape($seen['profile']) + '/\.cache/themes/[0-9a-fA-F]{64}/powerlevel10k$'
Assert ($seen['nested-p10k'] -cmatch $themes) "nested gx-zsh sees POWERLEVEL9K_INSTALLATION_DIR=$($seen['nested-p10k']), not the profile theme cache"
Assert ($seen['nested-fpath'] -eq '0') "nested gx-zsh has $($seen['nested-fpath']) non-POSIX fpath entries"
Assert ($seen['tmp'] -ceq 'gx-tmp-ok') "/tmp is not writable in GX Zsh: $($paths.Text)"
Assert ($seen['passwd'] -and $seen['passwd'] -ceq $seen['home']) "getent passwd home $($seen['passwd']) differs from HOME=$($seen['home'])"
# Native zoxide needs a Windows path; the launcher exports it inside the profile and creates the directory.
$zoxide = Join-Path $env:LOCALAPPDATA 'ohmyzsh-gx\profile\.local\share\zoxide'
Assert ($seen['zo'] -ieq $zoxide -and (Test-Path -LiteralPath $zoxide -PathType Container)) "GX Zsh exports _ZO_DATA_DIR=$($seen['zo']), expected the existing $zoxide"
Assert ($seen.ContainsKey('tools-broken') -and $seen['tools-broken'] -eq '') "private MSYS2 runtime tools are missing or fail to run: $($seen['tools-broken'])"

Step 'GX Zsh runs PowerShell one-liners and param() installer scripts through gx-pwsh and iex'
$bridgeScript = 'gx-pwsh ''Write-Output gx-pwsh-ok''; print -r -- "pwsh-exit=$?"; ' +
    'printf ''%s\n'' ''param([string]$Dir = "gx-param-default")'' ''Write-Output "gx-param=$Dir"'' ''exit 5'' | iex; print -r -- "param-exit=$?"; ' +
    'print -r -- ''Write-Output gx-iex-ok; exit 7'' | iex'
$bridge = Capture-Bounded 'gx-zsh-iex.txt' $gxZshExe @('-c', $bridgeScript) 180
foreach ($expected in 'gx-pwsh-ok', 'pwsh-exit=0', 'gx-param=gx-param-default', 'param-exit=5', 'gx-iex-ok') {
    Assert ($bridge.Text -match "(?m)^$([regex]::Escape($expected))\r?$") "the PowerShell bridge did not print $expected (exit $($bridge.Code))"
}
Assert ($bridge.Code -eq 7) "iex did not return the exit code of its script: $($bridge.Code)"

Step 'GX Zsh returns after running an app execution alias'
# msys2-runtime before 3.6.10-6 could hang after running an app execution alias such as winget.
$alias = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\winget.exe'
if (Test-Path -LiteralPath $alias -PathType Leaf) {
    $aliasRun = Capture-Bounded 'gx-zsh-alias.txt' $gxZshExe @('-c',
        '"$(cygpath -u -- "$LOCALAPPDATA")/Microsoft/WindowsApps/winget.exe" --version; print -r -- "gx-alias-returned=$?"') 120
    Assert ($aliasRun.Code -eq 0 -and $aliasRun.Text -match '(?m)^gx-alias-returned=0\r?$' -and $aliasRun.Text -match '(?m)^v\d+\.') "winget did not run and return through GX Zsh (exit $($aliasRun.Code))"
} else {
    Write-Host "::warning::This runner has no $alias app execution alias; the GX Zsh alias hang check did not run."
}

Step 'herdr package identity, managed update and packaged completion'
$herdrFiles = @($smokeProvenance.stages.ohmyzsh.payload | Where-Object { $_.path -ceq 'lib/herdr/herdr.exe' })
Assert ($herdrFiles.Count -eq 1) 'stage provenance lacks the installed herdr binary'
Assert ((Get-FileHash -LiteralPath (Join-Path $app 'lib\herdr\herdr.exe')).Hash -ieq $herdrFiles[0].sha256) 'installed herdr hash differs from stage provenance'
$version = Capture 'herdr-version.txt' (Join-Path $app 'bin\herdr.exe') @('--version')
Assert ($version.Code -eq 0 -and $version.Text.Trim() -ceq $smokeProvenance.expected_herdr_version) 'herdr version differs from the locked herdr revision and package identity'
$update = Capture 'herdr-update.txt' (Join-Path $app 'bin\herdr.exe') @('update')
Assert ($update.Code -ne 0 -and $update.Text -match 'managed by Oh My Zsh GX') 'herdr update was not blocked'
$completion = Join-Path $app 'share\ohmyzsh-gx\gx\omz-custom\plugins\herdr\_herdr'
Assert ((Test-Path -LiteralPath $completion -PathType Leaf) -and (Get-Content -LiteralPath $completion -TotalCount 1) -ceq '#compdef herdr') 'the packaged herdr completion is missing'

Step 'herdr server with a real GX Zsh pane on the bundled ConPTY; Ctrl+C for MSYS and native programs'
Assert ((Get-FileHash -LiteralPath $HerdrProbe).Hash -ieq $smokeProvenance.herdr_probe.sha256) 'herdr probe changed after provenance preflight'
$probe = Capture 'herdr-probe.json' $Python @('-B', $HerdrProbe,
    '--herdr', (Join-Path $app 'lib\herdr\herdr.exe'), '--zsh', (Join-Path $app 'runtime\msys64\usr\bin\zsh.exe'),
    '--msys-root', (Join-Path $app 'runtime\msys64'), '--output', (Join-Path $Evidence 'herdr-probe'))
Assert ($probe.Code -eq 0 -and $probe.Text -match '"status": "PASS"' -and $probe.Text -match 'loaded_conpty' -and
    $probe.Text -match '"ctrl-c-win32-input-native"') 'herdr probe failed'

Step 'the bundled fonts are registered for the current user'
$registered = @(Owned-Fonts)
Assert ($registered.Count -eq 8) "expected 8 registered GX Shell fonts, found $($registered.Count)"
Assert-InstalledState 'fonts'

Step 'Ghostty GX starts GX Zsh by default'
# The login shell is the zsh started by gx-zsh under ghostty.exe; other zsh.exe processes are MSYS2 forks.
function Find-GuiShell {
    $processes = @(Get-CimInstance Win32_Process)
    foreach ($gui in @($processes | Where-Object { $_.ExecutablePath -ieq $ghosttyExe })) {
        foreach ($launcher in @($processes | Where-Object { $_.ParentProcessId -eq $gui.ProcessId -and $_.ExecutablePath -ieq $gxZshExe })) {
            $shell = $processes | Where-Object { $_.ParentProcessId -eq $launcher.ProcessId -and $_.ExecutablePath -ieq (Join-Path $app 'runtime\msys64\usr\bin\zsh.exe') } | Select-Object -First 1
            if ($shell) { return [pscustomobject]@{ Gui = $gui.ProcessId; Shell = $shell.ProcessId } }
        }
    }
    return $null
}
function Fail-Gui([string]$Message, [string]$Label) {
    Save-GuiDiagnostics $Label
    Save-Screenshot "$Label-failed.png"
    throw "${Label}: $Message; see $Label-processes.txt, $Label-ghostty-logs and $Label-failed.png"
}
# The OpenGL implementation Ghostty GX loaded, from its log: "loaded OpenGL X.Y vendor=... renderer=... software=...".
function Renderer-Line {
    $log = Join-Path $ghosttyLogs 'ghostty.log'
    if (-not (Test-Path -LiteralPath $log -PathType Leaf)) { return $null }
    $line = @(Select-String -LiteralPath $log -Pattern 'loaded OpenGL (\d+)\.(\d+) vendor=.* renderer=.* software=(true|false)' | Select-Object -Last 1)
    if ($line.Count -eq 0) { return $null }
    return $line[0]
}
# Hosted runners have no GPU. GHOSTTY_GX_OPENGL=software makes Ghostty GX load the bundled Mesa
# (ghostty\mesa\opengl32.dll) and GALLIUM_DRIVER selects its llvmpipe rasterizer; this proves the software
# rendering path only, not hardware GPU rendering or desktop input.
function Run-HostedGuiWindow([string]$Label, [string]$Shortcut) {
    Assert ($env:GITHUB_ACTIONS -eq 'true' -and $env:RUNNER_ENVIRONMENT -eq 'github-hosted') 'software GUI smoke is hosted-runner only'
    Assert (-not (Find-GuiShell)) 'refusing to reuse an existing GX GUI shell'
    $link = Shortcut (Join-Path $programs $Shortcut)
    Assert ($link.TargetPath -ieq $ghosttyExe) "${Label}: $Shortcut does not start the installed Ghostty GX"
    $start = @{ FilePath = $link.TargetPath; WorkingDirectory = $link.WorkingDirectory }
    if ($link.Arguments) { $start.ArgumentList = $link.Arguments }
    $saved = Set-Environment @{ GHOSTTY_GX_OPENGL = 'software'; GALLIUM_DRIVER = 'llvmpipe' }
    try { Start-Process @start | Out-Null } finally { [void](Set-Environment $saved) }
    $started = $null
    for ($i = 0; $i -lt 120 -and -not $started; $i++) {
        Start-Sleep -Milliseconds 500
        $started = Find-GuiShell
    }
    if (-not $started) { Fail-Gui "Ghostty GX ($Shortcut) did not start the bundled GX Zsh (ghostty -> gx-zsh -> zsh) within 60 s" $Label }
    Start-Sleep -Seconds 5
    $running = Find-GuiShell
    if (-not $running -or $running.Shell -ne $started.Shell) { Fail-Gui "GX Zsh (pid $($started.Shell)) did not keep running under Ghostty GX" $Label }
    $window = $null
    for ($i = 0; $i -lt 20 -and -not $window; $i++) {
        $window = Get-Process -Id $started.Gui -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne [IntPtr]::Zero }
        if (-not $window) { Start-Sleep -Milliseconds 500 }
    }
    if (-not $window) { Fail-Gui "ghostty.exe (pid $($started.Gui)) shows no visible window" $Label }
    $renderer = $null
    for ($i = 0; $i -lt 40 -and -not $renderer; $i++) {
        $renderer = Renderer-Line
        if (-not $renderer) { Start-Sleep -Milliseconds 500 }
    }
    if (-not $renderer) { Fail-Gui 'the Ghostty GX log has no "loaded OpenGL" line' $Label }
    $groups = $renderer.Matches[0].Groups
    $major, $minor = [int]$groups[1].Value, [int]$groups[2].Value
    if ($major -lt 4 -or ($major -eq 4 -and $minor -lt 3) -or $groups[3].Value -cne 'true') {
        Fail-Gui "Ghostty GX did not load OpenGL 4.3+ from the bundled Mesa: $($renderer.Line)" $Label
    }
    Save-GuiDiagnostics $Label
    Save-Screenshot "$Label-windows.png"
    @{ status = 'EVIDENCE_READY'; shortcut = $Shortcut; gui_pid = $started.Gui; shell_pid = $started.Shell
        renderer = 'Mesa llvmpipe (GHOSTTY_GX_OPENGL=software)'; opengl = "$major.$minor"; renderer_line = $renderer.Line.Trim()
        images_reviewed = $false; desktop_input_echo_redraw = 'NOT_RUN'; hardware_gpu = 'NOT_RUN' } |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Evidence "$Label-window.json") -Encoding utf8
    Stop-Installation
}
Run-HostedGuiWindow 'install' 'Ghostty GX.lnk'

Step 'install and uninstall refuse an occupied runtime file without removing the installation'
$occupied = Join-Path $app 'runtime\msys64\usr\bin\msys-2.0.dll'
$occupiedHash = (Get-FileHash -LiteralPath $occupied).Hash
$handle = [IO.File]::Open($occupied, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
try {
    foreach ($case in @(@{ File = $Installer; Label = 'install-in-use' }, @{ File = (Join-Path $app 'unins000.exe'); Label = 'uninstall-in-use' })) {
        Run-Setup $case.File $case.Label -Seconds 45 -ExpectRefusal
        Assert ((Test-Path -LiteralPath $gxZshExe) -and (Test-Path -LiteralPath $ghosttyExe) -and (Test-Path -LiteralPath (Join-Path $app 'unins000.exe'))) 'an in-use refusal removed installed entry points'
        Assert ((Get-ItemProperty -LiteralPath 'HKCU:\Software\GX Shell').InstallDir -ceq $installDir) 'an in-use refusal changed ownership'
        Assert (@(Owned-PathEntries).Count -eq 1 -and @(Owned-Fonts).Count -eq 8) 'an in-use refusal changed PATH or fonts'
    }
} finally { $handle.Dispose() }
Assert ((Get-FileHash -LiteralPath $occupied).Hash -ceq $occupiedHash) 'an in-use refusal changed the runtime file'

Step 'same-version reinstall preserves the Ghostty GX configuration and full GX profile contents'
Assert-InstalledState 'before-reinstall'
Set-Content -LiteralPath (Join-Path $profile 'gx-shell-preserve-marker.txt') -Value 'user profile data: 中文' -Encoding utf8
Add-Content -LiteralPath (Join-Path $profile '.zshrc.local') -Value "`nexport GX_SMOKE_PRESERVE=gx-user-data-kept" -Encoding utf8
$protectedUserFiles = @{}
foreach ($path in @((Join-Path $ghosttyConfig 'config.ghostty'), (Join-Path $weztermConfig 'wezterm.lua'),
    (Join-Path $profile '.zshrc.local'), (Join-Path $profile 'gx-shell-preserve-marker.txt'))) {
    $protectedUserFiles[$path] = (Get-FileHash -LiteralPath $path).Hash
}
$beforeReinstall = UserData-State
Run-Setup $Installer 'reinstall'
Assert-UserData $beforeReinstall 'reinstall'
Runtime-Recheck 'reinstall'
Stop-Installation

Step 'uninstall removes only owned resources and preserves every user-data file'
Run-Uninstall 'uninstall'

Step 'a second installation preserves data and runs GX Zsh, herdr and Ghostty GX again'
$beforeSecondInstall = UserData-State
Run-Setup $Installer 'install-again'
Assert-UserData $beforeSecondInstall 'install-again'
Runtime-Recheck 'install-again'
Stop-Installation

Step 'uninstalling again removes everything the same way'
Run-Uninstall 'uninstall-again'

if ($PreviousInstaller) {
    # This leg keeps its GX Zsh profile apart from the checks above; both releases place it under LOCALAPPDATA.
    $upgradeLocal = Join-Path ([IO.Path]::GetTempPath()) 'gx-shell-upgrade\local'
    New-Item -ItemType Directory -Force -Path $upgradeLocal | Out-Null
    $oldWezTerm = Join-Path $app 'wezterm'
    $staleRecord = Join-Path $app 'runtime\msys64\var\lib\pacman\local\msys2-runtime-3.6.10-5'

    Step 'an earlier GX Shell is installed and its GX Zsh creates a profile'
    Run-Setup (Resolve-Path -LiteralPath $PreviousInstaller).Path 'previous-install'
    $saved = Set-Environment @{ LOCALAPPDATA = $upgradeLocal }
    try {
        $previousZsh = Capture-Bounded 'previous-gx-zsh.txt' $gxZshExe @('-c', 'print -r -- "zsh=$ZSH_VERSION omz=$ZSH"') 180
    } finally { [void](Set-Environment $saved) }
    Assert ($previousZsh.Code -eq 0 -and $previousZsh.Text -match 'zsh=5\.9\.2 omz=\S*/share/ohmyzsh-gx') 'GX Zsh of the earlier GX Shell did not start'
    $previousWezTerm = Test-Path -LiteralPath (Join-Path $oldWezTerm 'wezterm-gx.exe')
    Stop-Installation
    $beforeUpgrade = UserData-State

    Step 'the new build installs over the earlier GX Shell and removes its WezTerm GX'
    Run-Setup $Installer 'upgrade'
    Assert-UserData $beforeUpgrade 'upgrade'
    Assert (-not (Test-Path -LiteralPath $oldWezTerm)) "the upgrade kept $oldWezTerm"
    Assert (-not (Test-Path -LiteralPath $staleRecord)) "the upgrade kept the stale pacman record $staleRecord"
    foreach ($path in (Join-Path $programs 'WezTerm GX.lnk'), (Join-Path $desktop 'WezTerm GX.lnk')) {
        Assert (-not (Test-Path -LiteralPath $path)) "the upgrade kept the WezTerm GX shortcut $path"
    }
    Assert (-not (Test-Path -LiteralPath $oldAppPathKey)) 'the upgrade kept App Paths\wezterm-gx.exe'
    Assert-InstalledState 'upgrade'

    Step 'GX Zsh of the new build starts on the earlier profile and adopts its herdr configuration'
    $saved = Set-Environment @{ LOCALAPPDATA = $upgradeLocal }
    try {
        $upgradedZsh = Capture-Bounded 'upgrade-gx-zsh.txt' $gxZshExe @('-c', 'print -r -- "zsh=$ZSH_VERSION omz=$ZSH"') 180
    } finally { [void](Set-Environment $saved) }
    Assert ($upgradedZsh.Code -eq 0 -and $upgradedZsh.Text -match 'zsh=5\.9\.2 omz=\S*/share/ohmyzsh-gx') 'GX Zsh did not start on the earlier profile'
    Assert-HerdrConfig 'upgrade' $upgradeLocal
    Run-HostedGuiWindow 'upgrade' 'Ghostty GX.lnk'

    Step 'uninstalling the upgraded installation keeps what a separately installed WezTerm GX created since'
    # The uninstall log of the earlier release still names its WezTerm GX shortcuts and App Paths entry; a WezTerm GX
    # installed separately after the upgrade reuses those names.
    $foreignTarget = Join-Path $env:LOCALAPPDATA 'Programs\WezTerm GX\wezterm-gx.exe'
    $foreignLinks = @{}
    foreach ($path in (Join-Path $programs 'WezTerm GX.lnk'), (Join-Path $desktop 'WezTerm GX.lnk')) {
        $link = Shortcut $path
        $link.TargetPath = $foreignTarget
        $link.Save()
        $foreignLinks[$path] = (Get-FileHash -LiteralPath $path).Hash
    }
    New-Item -Path $oldAppPathKey -Force | Out-Null
    Set-Item -LiteralPath $oldAppPathKey -Value $foreignTarget
    $hostBaseline = NonOwned-State
    Stop-Installation
    Run-Uninstall 'uninstall-upgrade'
    foreach ($path in $foreignLinks.Keys) {
        Assert ((Test-Path -LiteralPath $path) -and (Get-FileHash -LiteralPath $path).Hash -eq $foreignLinks[$path]) "uninstall removed or changed the separate WezTerm GX shortcut $path"
        Remove-Item -LiteralPath $path
    }
    Assert ((Get-Item -LiteralPath $oldAppPathKey).GetValue('') -ieq $foreignTarget) 'uninstall removed App Paths\wezterm-gx.exe of the separate WezTerm GX'
    Remove-Item -LiteralPath $oldAppPathKey -Recurse
    $smokeProvenance | Add-Member -NotePropertyName previous_release -NotePropertyValue @{ bundled_wezterm = $previousWezTerm }
}
$smokeProvenance.status = 'PASS'
$smokeProvenance.legacy_release_upgrade = if ($PreviousInstaller) { 'PASS_EXPLICIT_INPUT_ONLY' } else { 'NOT_RUN' }
$smokeProvenance | Add-Member -NotePropertyName coverage -NotePropertyValue @{
    install = 'PASS'; same_version_reinstall = 'PASS'; uninstall = 'PASS'; user_configuration = 'PASS'; occupied_file_refusal = 'PASS'
    reinstall_runtime = 'PASS'; second_install_runtime = 'PASS'; profile_contents = 'PASS'; non_owned_baseline = 'PASS'
    hosted_software_window = 'EVIDENCE_READY'; desktop_input_echo_redraw = 'NOT_RUN'; hardware_gpu = 'NOT_RUN'; images_reviewed = $false
    previous_gx_shell = $(if ($PreviousInstaller) { 'PASS_EXPLICIT_INPUT_ONLY' } else { 'NOT_RUN' })
}
$smokeProvenance | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath (Join-Path $Evidence 'smoke-provenance.json') -Encoding utf8
"PASS: GX Shell Windows installer lifecycle only; GUI images await review, desktop input/echo/redraw and hardware GPU NOT_RUN; legacy release upgrade: $($smokeProvenance.legacy_release_upgrade)" | Tee-Object -FilePath (Join-Path $Evidence 'result.txt')

"""Offline planner checks; ExecutionPolicy Bypass applies only to test child processes."""
import base64
import json
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("gx_shell_local_build.ps1")
HOSTS = [(name, shutil.which(name)) for name in ("powershell", "pwsh")] if os.name == "nt" else []
HOSTS = [(name, exe) for name, exe in HOSTS if exe]
SENTINEL = "GX_TEST_SECRET_NOT_FOR_OUTPUT"


def quote(text):
    return "'" + str(text).replace("'", "''") + "'"


def run_ps(exe, body, overrides=None):
    env = os.environ.copy()
    for key in ("GX_BUILD_ROOT", "GX_CPU_JOBS", "GX_ZSH_JOBS", "GX_MEMORY_BUDGET_GB",
                "RUSTUP_TOOLCHAIN", "GH_TOKEN", "GITHUB_TOKEN", "GITHUB_ACTIONS"):
        env.pop(key, None)
    env.update(overrides or {})
    prefix = ("[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false); "
              "$ErrorActionPreference = 'Stop'; $ProgressPreference = 'SilentlyContinue'; ")
    encoded = base64.b64encode((prefix + body).encode("utf-16le")).decode("ascii")
    return subprocess.run([exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                           "-EncodedCommand", encoded], env=env, capture_output=True,
                          encoding="utf-8-sig", errors="replace", timeout=120)


def functions_only():
    return ("$tokens=$null; $errors=$null; $ast=[Management.Automation.Language.Parser]::ParseFile("
            + quote(SCRIPT) + ", [ref]$tokens, [ref]$errors); if ($errors.Count) { throw 'Parse failed' }; "
            "$definitions=$ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]}, $false); "
            ". ([scriptblock]::Create(($definitions | ForEach-Object {$_.Extent.Text}) -join [Environment]::NewLine)); "
            "$script:Diagnostics=New-Object 'System.Collections.Generic.List[string]'; ")


class SourceChecks(unittest.TestCase):
    def test_ascii_and_no_side_effect_entrypoints(self):
        text = SCRIPT.read_text(encoding="ascii")
        self.assertTrue(text.startswith("#requires -Version 5.1"))
        self.assertIsNone(re.search(r"(?im)^\s*(?:Invoke-WebRequest|Invoke-RestMethod|Install-Module|"
                                    r"Set-ExecutionPolicy|New-Item|Set-Content|Remove-Item|Start-Job)\b", text))
        for forbidden in ("Get-ChildItem Env:", "GetEnvironmentVariables(", "WriteAllText(",
                          "Win32_VideoController", "cargo build", "rustup update"):
            self.assertNotIn(forbidden, text)


@unittest.skipUnless(HOSTS, "Windows PowerShell or PowerShell 7 on Windows required")
class PlannerTests(unittest.TestCase):
    def decoded(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(SENTINEL, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_both_host_parsers(self):
        body = ("$tokens=$null; $errors=$null; [void][Management.Automation.Language.Parser]::ParseFile("
                + quote(SCRIPT) + ", [ref]$tokens, [ref]$errors); if ($errors.Count) { throw ($errors -join '; ') }; "
                "$PSVersionTable.PSVersion.ToString() | ConvertTo-Json")
        for name, exe in HOSTS:
            with self.subTest(host=name):
                self.assertRegex(self.decoded(run_ps(exe, body)), r"^(5\.1|7\.)")

    def test_reference_budget_and_overrides(self):
        body = functions_only() + """
$h=@{physical_cores=14; logical_cores=20; total_memory_gib=48; available_memory_gib=46}
$busy=@{physical_cores=14; logical_cores=20; total_memory_gib=48; available_memory_gib=20}
[ordered]@{
    reference=(Get-Budget $h '' '' '')
    overridden=(Get-Budget $h '12' '6' '32')
    constrained=(Get-Budget $busy '' '' '18')
    unknown=(Get-Budget @{physical_cores=$null; logical_cores=4; total_memory_gib=$null; available_memory_gib=$null} '' '' '')
} | ConvertTo-Json -Depth 5
"""
        for name, exe in HOSTS:
            with self.subTest(host=name):
                data = self.decoded(run_ps(exe, body))
                self.assertEqual(data["reference"]["cpu_jobs"], 16)
                self.assertEqual(data["reference"]["zsh_jobs"], 8)
                self.assertEqual(data["reference"]["reserved_logical_cores"], 4)
                self.assertEqual(data["reference"]["memory_budget_gib"], 40)
                self.assertEqual(data["reference"]["max_parallel_components"], 1)
                self.assertEqual(data["overridden"]["cpu_jobs"], 12)
                self.assertEqual(data["overridden"]["zsh_jobs"], 6)
                self.assertEqual(data["constrained"]["cpu_jobs"], 7)
                self.assertEqual(data["unknown"]["cpu_jobs"], 1)
                self.assertTrue(data["unknown"]["memory_estimated"])

    def test_invalid_resource_overrides_are_rejected(self):
        body = functions_only() + """
$h=@{physical_cores=14; logical_cores=20; total_memory_gib=48; available_memory_gib=46}
$cases=@(@('0','',''), @('-1','',''), @('1.5','',''), @('99','',''), @('12','13',''), @('','','41'), @('','','NaN'), @('','','5'))
$result=foreach ($case in $cases) {
    try { $null=Get-Budget $h $case[0] $case[1] $case[2]; $false } catch { $true }
}
ConvertTo-Json -InputObject @($result)
"""
        for name, exe in HOSTS:
            with self.subTest(host=name):
                self.assertEqual(self.decoded(run_ps(exe, body)), [True] * 8)

    def test_build_root_is_short_absolute_ascii(self):
        body = functions_only() + r"""
$bad=@('relative', 'C:', 'C:\', 'C:\bad name', 'C:\NUL.txt', 'C:\a\..\b', 'C:\a.', ('C:\' + [char]0x4e2d), ('C:\' + ('a'*40)))
$result=foreach ($path in $bad) { try { $null=Get-BuildRoot $path 'C:\repo'; $false } catch { $true } }
[ordered]@{bad=@($result); good=(Get-BuildRoot 'C:/gx-b' 'C:\repo')} | ConvertTo-Json
"""
        for name, exe in HOSTS:
            with self.subTest(host=name):
                data = self.decoded(run_ps(exe, body))
                self.assertEqual(data["bad"], [True] * 9)
                self.assertEqual(data["good"], r"C:\gx-b")

    def test_component_identity_clean_dirty_parent_and_mismatch(self):
        body = functions_only() + """
$script:top=$env:SystemRoot; $script:status=''; $script:head='b'*40
function Invoke-Probe([string]$File, [string[]]$Arguments, [string]$Label) {
    switch -Wildcard ($Label) { '*checkout root' {return $script:top}; '*revision' {return $script:head}; '*clean state' {return $script:status} }
}
$clean=Get-Component 'herdr' $env:SystemRoot '' 'fixture'
$script:status=' M file'; $dirty=Get-Component 'herdr' $env:SystemRoot '' 'fixture'
try { $null=Get-Component 'herdr' $env:SystemRoot ('a'*40) 'fixture'; $mismatch=$false } catch { $mismatch=$true }
$script:top=Split-Path -Parent $env:SystemRoot; $parent=Get-Component 'herdr' $env:SystemRoot '' 'fixture'
[ordered]@{clean=$clean; dirty=$dirty; parent=$parent; mismatch=$mismatch} | ConvertTo-Json -Depth 5
"""
        for name, exe in HOSTS:
            with self.subTest(host=name):
                data = self.decoded(run_ps(exe, body))
                self.assertTrue(data["clean"]["source_verified"])
                self.assertFalse(data["dirty"]["source_verified"])
                self.assertTrue(data["dirty"]["dirty"])
                self.assertIsNone(data["parent"]["revision"])
                self.assertTrue(data["mismatch"])

    def test_real_json_cache_partitioning_and_secrets(self):
        reports = []
        drive = Path(SCRIPT.resolve().anchor)
        root = drive / "gx-plan-test-unused"
        existed = root.exists()
        for name, exe in HOSTS:
            with self.subTest(host=name):
                body = ("& " + quote(SCRIPT) + " -Format Json -BuildRoot " + quote(root)
                        + " -RepoRoot " + quote(root / "absent")
                        + " -Component herdr -ComponentRevisions @{herdr=('a'*40); ohmyzsh=('b'*40); wezterm=('c'*40)}")
                data = self.decoded(run_ps(exe, body, {"GH_TOKEN": SENTINEL, "GX_PRIVATE_PASSWORD": SENTINEL,
                                                     "GX_CPU_JOBS": "1", "GX_ZSH_JOBS": "1", "GX_MEMORY_BUDGET_GB": "6"}))
                self.assertEqual(data["mode"], "plan-only")
                self.assertFalse(data["ready"])
                self.assertFalse(data["publishable"])
                self.assertEqual(data["environment"]["CARGO_NET_OFFLINE"], "true")
                self.assertEqual(data["environment"]["RUSTUP_AUTO_INSTALL"], "0")
                self.assertNotIn("RUSTC_WRAPPER", data["environment"])
                caches = []
                for component, sha in zip(("herdr", "ohmyzsh", "wezterm"), ("a"*40, "b"*40, "c"*40)):
                    entry = data["paths"]["components"][component]
                    cache = entry["paths"]["cache"]
                    caches.append(cache)
                    self.assertIn(sha, cache)
                    self.assertIn(data["paths"]["toolchain_key"], cache)
                    self.assertTrue(cache.endswith("x86_64-pc-windows-msvc"))
                    self.assertTrue(cache.isascii())
                    self.assertFalse(entry["source_verified"])
                self.assertEqual(len(set(caches)), 3)
                self.assertEqual(root.exists(), existed)
                reports.append(data)
        if len(reports) > 1:
            self.assertEqual(reports[0]["paths"]["toolchain_key"], reports[1]["paths"]["toolchain_key"])

    def test_script_file_invocation_resolves_its_default_repository(self):
        for name, exe in HOSTS:
            with self.subTest(host=name):
                body = "& " + quote(SCRIPT) + " -Format Json -Component herdr"
                data = self.decoded(run_ps(exe, body, {"GX_CPU_JOBS": "1", "GX_ZSH_JOBS": "1", "GX_MEMORY_BUDGET_GB": "6"}))
                self.assertEqual(data["paths"]["components"]["herdr"]["root"], str(SCRIPT.parent.parent / "herdr"))

    def test_available_memory_reduces_automatic_parallelism(self):
        body = functions_only() + "Get-Budget @{physical_cores=14; logical_cores=20; total_memory_gib=48; available_memory_gib=20} '' '' '' | ConvertTo-Json"
        for name, exe in HOSTS:
            with self.subTest(host=name):
                data = self.decoded(run_ps(exe, body))
                self.assertEqual(data["cpu_jobs"], 7)
                self.assertEqual(data["memory_budget_gib"], 18)

    def test_fingerprint_changes_with_toolchain(self):
        body = functions_only() + "@((Get-Key 'rust-1'), (Get-Key 'rust-2'), (Get-Key 'rust-1')) | ConvertTo-Json"
        for name, exe in HOSTS:
            with self.subTest(host=name):
                a, b, repeat = self.decoded(run_ps(exe, body))
                self.assertEqual(a, repeat)
                self.assertNotEqual(a, b)

    def test_real_environment_and_error_redaction(self):
        for name, exe in HOSTS:
            with self.subTest(host=name):
                result = run_ps(exe, "& " + quote(SCRIPT) + " -Format Environment",
                                {"GX_CPU_JOBS": "1", "GX_ZSH_JOBS": "1", "GX_MEMORY_BUDGET_GB": "6",
                                 "GX_BUILD_ROOT": "C:/gx-b", "GH_TOKEN": SENTINEL})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn(SENTINEL, result.stdout + result.stderr)
                self.assertIn("$env:GX_CPU_JOBS = '1'", result.stdout)
                self.assertIn(r"$env:GX_LOCAL_BUILD_ROOT = 'C:\gx-b'", result.stdout)
                invalid = run_ps(exe, "& " + quote(SCRIPT) + " -Format Json", {"GX_BUILD_ROOT": SENTINEL})
                self.assertNotEqual(invalid.returncode, 0)
                self.assertNotIn(SENTINEL, invalid.stdout + invalid.stderr)
                self.assertIn("GX_BUILD_ROOT", invalid.stderr)


if __name__ == "__main__":
    unittest.main()

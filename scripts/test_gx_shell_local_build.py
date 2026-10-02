"""Offline planner checks; ExecutionPolicy Bypass applies only to test child processes."""
import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("gx_shell_local_build.ps1")
HOSTS = [(name, shutil.which(name)) for name in ("powershell", "pwsh")] if os.name == "nt" else []
HOSTS = [(name, exe) for name, exe in HOSTS if exe]
SENTINEL = "GX_TEST_SECRET_NOT_FOR_OUTPUT"


def quote(text):
    return "'" + str(text).replace("'", "''") + "'"


def canonical(path):
    return os.path.normcase(os.path.realpath(path))


def short_alias(path):
    import ctypes
    buffer = ctypes.create_unicode_buffer(1024)
    length = ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, len(buffer))
    return buffer.value if 0 < length < len(buffer) and "~" in buffer.value else None


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


def make_repo(testcase, unicode_name=False):
    temp = tempfile.TemporaryDirectory(prefix="gx-plan-")
    testcase.addCleanup(temp.cleanup)
    repo = Path(temp.name)
    if unicode_name:
        repo = repo / "gx项目-repo"
        repo.mkdir()
    return repo


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
        for required in (".local\\build", ".local\\sources", "Get-ComponentRoot", "plan-"):
            self.assertIn(required, text)


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

    def test_build_root_run_directory_contract(self):
        repo = make_repo(self)
        base = repo / ".local" / "build"
        taken = base / "run-taken"
        taken.mkdir(parents=True)
        cases = [
            ("relative", "relative"),
            ("drive_letter", "C:"),
            ("drive_root", "C:\\"),
            ("outside", str(repo / "other" / "run")),
            ("nested", str(base / "a" / "b")),
            ("base_itself", str(base)),
            ("spaced", str(base / "bad name")),
            ("reserved", str(base / "NUL")),
            ("too_long", str(base / ("a" * 33))),
            ("unicode_run", str(base / "运行")),
            ("taken", str(taken)),
        ]
        lines = ["$repo=" + quote(repo)]
        for key, value in cases:
            lines.append("$" + key + "=(& { try { $null=Get-BuildRoot " + quote(value)
                         + " $repo; $false } catch { $true } })")
        lines.append("$good=(Get-BuildRoot " + quote(base / "run-1") + " $repo)")
        lines.append("$slashes=(Get-BuildRoot " + quote(str(base / "run-2").replace("\\", "/")) + " $repo)")
        lines.append("$defaulted=(Get-BuildRoot '' $repo)")
        entries = "; ".join(key + "=$" + key for key, _ in cases)
        lines.append("[ordered]@{" + entries + "; good=$good; slashes=$slashes; defaulted=$defaulted} | ConvertTo-Json")
        body = functions_only() + "; ".join(lines)
        for name, exe in HOSTS:
            with self.subTest(host=name):
                data = self.decoded(run_ps(exe, body))
                for key, _ in cases:
                    self.assertTrue(data[key], key)
                self.assertEqual(canonical(data["good"]), canonical(base / "run-1"))
                self.assertEqual(canonical(data["slashes"]), canonical(base / "run-2"))
                defaulted = Path(data["defaulted"])
                self.assertEqual(canonical(defaulted.parent), canonical(base))
                self.assertRegex(defaulted.name, r"^plan-\d{8}-\d{6}$")
                self.assertFalse(defaulted.exists())

    def test_component_root_must_stay_under_sources(self):
        repo = make_repo(self, unicode_name=True)
        sources = repo / ".local" / "sources"
        bad = [
            str(repo / "herdr"),
            str(repo),
            str(repo / ".local"),
            str(sources),
            str(repo / ".local" / "sources2" / "herdr"),
            str(sources / "herdr" / ".." / ".." / "herdr"),
            "herdr",
            "D:",
        ]
        lines = ["$base=" + quote(sources)]
        for index, value in enumerate(bad):
            lines.append("$b" + str(index) + "=(& { try { $null=Get-ComponentRoot 'herdr' " + quote(value)
                         + " $base; $false } catch { $true } })")
        lines.append("$good=(Get-ComponentRoot 'herdr' " + quote(sources / "herdr") + " $base)")
        lines.append("$deep=(Get-ComponentRoot 'herdr' " + quote(sources / "nested" / "herdr") + " $base)")
        entries = "; ".join("b" + str(index) + "=$b" + str(index) for index in range(len(bad)))
        lines.append("[ordered]@{" + entries + "; good=$good; deep=$deep} | ConvertTo-Json")
        body = functions_only() + "; ".join(lines)
        for name, exe in HOSTS:
            with self.subTest(host=name):
                data = self.decoded(run_ps(exe, body))
                for index, value in enumerate(bad):
                    self.assertTrue(data["b{0}".format(index)], value)
                self.assertEqual(canonical(data["good"]), canonical(sources / "herdr"))
                self.assertEqual(canonical(data["deep"]), canonical(sources / "nested" / "herdr"))

    def test_short_name_aliases_are_normalized_before_comparison(self):
        long_base = os.environ.get("ProgramFiles", "")
        alias = short_alias(long_base) if long_base else None
        if not alias:
            self.skipTest("no existing 8.3 short-name alias to probe")
        absent = "gx-plan-absent-" + os.urandom(4).hex()
        short, full = Path(alias) / absent, Path(long_base) / absent
        self.assertFalse(full.exists())
        build, sources = Path(".local", "build"), Path(".local", "sources")
        accepted = {
            "short_run": ("Get-BuildRoot " + quote(short / build / "run-1") + " $repo", full / build / "run-1"),
            "long_run": ("Get-BuildRoot " + quote(full / build / "run-2") + " $repo", full / build / "run-2"),
            "short_component": ("Get-ComponentRoot 'herdr' " + quote(short / sources / "herdr") + " $sources",
                                full / sources / "herdr"),
            "long_component": ("Get-ComponentRoot 'herdr' " + quote(full / sources / "herdr") + " $sources",
                               full / sources / "herdr"),
        }
        rejected = {
            "outside_run": "Get-BuildRoot " + quote(short / "other" / "run") + " $repo",
            "nested_run": "Get-BuildRoot " + quote(full / build / "a" / "b") + " $repo",
            "sibling_component": "Get-ComponentRoot 'herdr' " + quote(short / ".local" / "sources2" / "herdr") + " $sources",
            "sources_itself": "Get-ComponentRoot 'herdr' " + quote(full / sources) + " $sources",
        }
        lines = ["$repo=" + quote(short), "$sources=" + quote(short / sources)]
        lines += ["$" + key + "=(" + call + ")" for key, (call, _) in accepted.items()]
        lines += ["$" + key + "=(& { try { $null=" + call + "; $false } catch { $true } })"
                  for key, call in rejected.items()]
        lines.append("[ordered]@{" + "; ".join(key + "=$" + key for key in [*accepted, *rejected])
                     + "} | ConvertTo-Json")
        body = functions_only() + "; ".join(lines)
        for name, exe in HOSTS:
            with self.subTest(host=name):
                data = self.decoded(run_ps(exe, body))
                for key, (_, expected) in accepted.items():
                    self.assertNotIn("~", data[key], key)
                    self.assertEqual(canonical(data[key]), canonical(expected), key)
                for key in rejected:
                    self.assertTrue(data[key], key)

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
        repo = make_repo(self)
        run = repo / ".local" / "build" / "run-plan"
        boundary = canonical(run) + os.sep
        for name, exe in HOSTS:
            with self.subTest(host=name):
                body = ("& " + quote(SCRIPT) + " -Format Json -BuildRoot " + quote(run)
                        + " -RepoRoot " + quote(repo)
                        + " -Component herdr -ComponentRevisions @{herdr=('a'*40); ohmyzsh=('b'*40); wezterm=('c'*40)}")
                data = self.decoded(run_ps(exe, body, {"GH_TOKEN": SENTINEL, "GX_PRIVATE_PASSWORD": SENTINEL,
                                                     "GX_CPU_JOBS": "1", "GX_ZSH_JOBS": "1", "GX_MEMORY_BUDGET_GB": "6"}))
                self.assertEqual(data["mode"], "plan-only")
                self.assertFalse(data["ready"])
                self.assertFalse(data["publishable"])
                self.assertEqual(data["environment"]["CARGO_NET_OFFLINE"], "true")
                self.assertEqual(data["environment"]["RUSTUP_AUTO_INSTALL"], "0")
                self.assertNotIn("RUSTC_WRAPPER", data["environment"])
                paths = data["paths"]
                self.assertEqual(canonical(paths["build_root"]), canonical(run))
                self.assertEqual(paths["run_name"], "run-plan")
                self.assertEqual(canonical(paths["repo_root"]), canonical(repo))
                self.assertEqual(canonical(paths["sources_root"]), canonical(repo / ".local" / "sources"))
                self.assertFalse(paths["exists"])
                self.assertEqual(paths["build_root"], data["environment"]["GX_BUILD_ROOT"])
                self.assertEqual(paths["build_root"], data["environment"]["GX_LOCAL_BUILD_ROOT"])
                leaves = []
                for component, sha in zip(("herdr", "ohmyzsh", "wezterm"), ("a"*40, "b"*40, "c"*40)):
                    entry = paths["components"][component]
                    self.assertEqual(entry["revision"], sha)
                    self.assertEqual(canonical(entry["root"]), canonical(repo / ".local" / "sources" / component))
                    self.assertFalse(entry["source_verified"])
                    planned = entry["paths"]
                    leaf = Path(planned["cache"]).name
                    self.assertRegex(leaf, r"^" + component + r"-[0-9a-f]{16}$")
                    leaves.append(leaf)
                    for key in ("cache", "work", "cargo_home", "cargo_target", "sccache", "zsh", "logs"):
                        value = planned[key]
                        self.assertTrue(canonical(value).startswith(boundary), key)
                        self.assertLessEqual(len(value), 120, key)
                    self.assertEqual(planned["cargo_home"], planned["cache"] + "\\cargo")
                    self.assertEqual(planned["cargo_target"], planned["cache"] + "\\target")
                    self.assertEqual(planned["logs"], planned["cache"] + "\\logs")
                    self.assertEqual(Path(planned["work"]).name, leaf)
                self.assertEqual(len(set(leaves)), 3)
                self.assertFalse(run.exists())
                reports.append(data)
        if len(reports) > 1:
            self.assertEqual(reports[0]["paths"]["toolchain_key"], reports[1]["paths"]["toolchain_key"])
            for component in ("herdr", "ohmyzsh", "wezterm"):
                self.assertEqual(reports[0]["paths"]["components"][component]["paths"],
                                 reports[1]["paths"]["components"][component]["paths"])

    def test_non_ascii_repo_root_resolves(self):
        repo = make_repo(self, unicode_name=True)
        run = repo / ".local" / "build" / "r1"
        for name, exe in HOSTS:
            with self.subTest(host=name):
                body = ("& " + quote(SCRIPT) + " -Format Json -RepoRoot " + quote(repo)
                        + " -BuildRoot " + quote(run) + " -Component herdr"
                        + " -ComponentRevisions @{herdr=('a'*40)}")
                data = self.decoded(run_ps(exe, body, {"GX_CPU_JOBS": "1", "GX_ZSH_JOBS": "1",
                                                       "GX_MEMORY_BUDGET_GB": "6"}))
                paths = data["paths"]
                self.assertEqual(canonical(paths["repo_root"]), canonical(repo))
                self.assertEqual(canonical(paths["build_root"]), canonical(run))
                cache = paths["components"]["herdr"]["paths"]["cache"]
                self.assertTrue(canonical(cache).startswith(canonical(run) + os.sep))
                self.assertLessEqual(len(cache) + len("\\sccache"), 120)
                self.assertFalse(run.exists())

    def test_component_roots_outside_sources_are_rejected(self):
        repo = make_repo(self)
        run = repo / ".local" / "build" / "run-src"
        cases = [
            "@{herdr=" + quote(repo / "elsewhere" / "herdr") + "}",
            "@{wezterm=" + quote(run / "wezterm") + "}",
            "@{ohmyzsh=" + quote(repo / ".local" / "sources") + "}",
        ]
        for name, exe in HOSTS:
            for roots in cases:
                with self.subTest(host=name, roots=roots):
                    result = run_ps(exe, "& " + quote(SCRIPT) + " -Format Json -RepoRoot " + quote(repo)
                                    + " -BuildRoot " + quote(run) + " -ComponentRoots " + roots,
                                    {"GX_CPU_JOBS": "1", "GX_ZSH_JOBS": "1", "GX_MEMORY_BUDGET_GB": "6"})
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("component roots must stay below", result.stderr)
                    self.assertNotIn(str(repo), result.stderr)

    def test_build_root_leaves_budget_for_component_paths(self):
        temp = tempfile.TemporaryDirectory(prefix="gx-plan-")
        self.addCleanup(temp.cleanup)
        repo = Path(temp.name) / ("d" * 40)
        repo.mkdir()
        run = repo / ".local" / "build" / ("r" * 32)
        for name, exe in HOSTS:
            with self.subTest(host=name):
                result = run_ps(exe, "& " + quote(SCRIPT) + " -Format Json -RepoRoot " + quote(repo)
                                + " -BuildRoot " + quote(run)
                                + " -ComponentRevisions @{herdr=('a'*40)}",
                                {"GX_CPU_JOBS": "1", "GX_ZSH_JOBS": "1", "GX_MEMORY_BUDGET_GB": "6"})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("120", result.stderr)
                self.assertNotIn(str(repo), result.stderr)

    def test_script_file_invocation_resolves_its_default_repository(self):
        real = SCRIPT.parent.parent
        for name, exe in HOSTS:
            with self.subTest(host=name):
                body = "& " + quote(SCRIPT) + " -Format Json -Component herdr"
                data = self.decoded(run_ps(exe, body, {"GX_CPU_JOBS": "1", "GX_ZSH_JOBS": "1", "GX_MEMORY_BUDGET_GB": "6"}))
                paths = data["paths"]
                self.assertEqual(os.path.normcase(paths["repo_root"]), os.path.normcase(str(real)))
                self.assertEqual(os.path.normcase(paths["components"]["herdr"]["root"]),
                                 os.path.normcase(str(real / ".local" / "sources" / "herdr")))
                defaulted = Path(paths["build_root"])
                self.assertEqual(os.path.normcase(str(defaulted.parent)),
                                 os.path.normcase(str(real / ".local" / "build")))
                self.assertRegex(defaulted.name, r"^plan-\d{8}-\d{6}$")
                self.assertFalse(defaulted.exists())

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
        repo = SCRIPT.parent.parent
        run = repo / ".local" / "build" / "plan-env-check"
        self.assertFalse(run.exists())
        for name, exe in HOSTS:
            with self.subTest(host=name):
                result = run_ps(exe, "& " + quote(SCRIPT) + " -Format Environment",
                                {"GX_CPU_JOBS": "1", "GX_ZSH_JOBS": "1", "GX_MEMORY_BUDGET_GB": "6",
                                 "GX_BUILD_ROOT": str(run), "GH_TOKEN": SENTINEL})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn(SENTINEL, result.stdout + result.stderr)
                self.assertIn("$env:GX_CPU_JOBS = '1'", result.stdout)
                self.assertIn("$env:GX_LOCAL_BUILD_ROOT = " + quote(run), result.stdout)
                invalid = run_ps(exe, "& " + quote(SCRIPT) + " -Format Json", {"GX_BUILD_ROOT": SENTINEL})
                self.assertNotEqual(invalid.returncode, 0)
                self.assertNotIn(SENTINEL, invalid.stdout + invalid.stderr)
                self.assertIn("BuildRoot", invalid.stderr)
                outside = run_ps(exe, "& " + quote(SCRIPT) + " -Format Json",
                                 {"GX_BUILD_ROOT": str(repo / "other" / "run")})
                self.assertNotEqual(outside.returncode, 0)
                self.assertNotIn(str(repo), outside.stderr)


if __name__ == "__main__":
    unittest.main()

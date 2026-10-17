"""Offline bootstrap contract checks; never download or install a tool."""
import base64
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parent
PS1 = (SCRIPTS / "gx_shell_setup.ps1").read_text(encoding="utf-8")
SH = (SCRIPTS / "gx_shell_setup.sh").read_text(encoding="utf-8")
HOSTS = [shutil.which(name) for name in ("powershell", "pwsh")] if os.name == "nt" else []
HOSTS = [host for host in HOSTS if host]


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def run_ps(host, source):
    encoded = base64.b64encode(source.encode("utf-16le")).decode("ascii")
    # A Python child of pwsh must not inject PowerShell 7 module paths into 5.1.
    env = {key: value for key, value in os.environ.items() if key.upper() != "PSMODULEPATH"}
    return subprocess.run(
        [host, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
        env=env, capture_output=True, encoding="utf-8-sig", errors="replace", timeout=30,
    )


class SetupStaticTests(unittest.TestCase):
    def test_every_download_has_a_full_sha256_pin(self):
        for source, names in ((PS1, ("Python", "Actionlint", "Inno")), (SH, ("PYTHON_", "ACTIONLINT_"))):
            for name in names:
                with self.subTest(name=name):
                    suffix = "SHA256" if name.endswith("_") else "Sha256"
                    match = re.search(rf"{name}{suffix}\s*=\s*'([^']+)'", source)
                    self.assertIsNotNone(match)
                    self.assertRegex(match[1], r"^[0-9a-f]{64}$")
                    self.assertGreater(len(set(match[1])), 8)

    def test_download_urls_are_immutable_release_versions(self):
        for source, count in ((PS1, 3), (SH, 2)):
            urls = re.findall(r"(?:Url|URL)\s*=\s*'(https://[^']+)'", source)
            self.assertEqual(len(urls), count)
            for url in urls:
                self.assertRegex(url, r"^https://github\.com/[^/]+/[^/]+/releases/download/[^/]+/")
                self.assertNotRegex(url, r"latest|/main/|/master/")
                self.assertRegex(url, r"3\.12\.12|1\.7\.12|7\.1\.0")

    def test_inno_matches_ghostty_portable_contract(self):
        self.assertIn("0362a383ed217d4c4239b5933866dd96d3eb2102737da92f80f6057a4b40df2f", PS1)
        for option in ("/CURRENTUSER", "/PORTABLE=1", "/VERYSILENT", "/NORESTART", "/DIR=", "/LOG="):
            self.assertIn(option, PS1)
        self.assertNotIn("/ALLUSERS", PS1)

    def test_no_system_package_manager_or_persistent_environment_mutation(self):
        for source in (PS1, SH):
            self.assertNotRegex(source.lower(), r"\b(?:winget|choco|scoop|msiexec|apt|apt-get|sudo|setx)\b")
            self.assertNotRegex(source, r"HKLM:|HKCU:|/usr/local|/etc/profile|\.bashrc|\.profile")
        self.assertNotRegex(PS1, r"SetEnvironmentVariable[^\n]*(?:'User'|'Machine')")

    def test_uv_uses_local_pinned_catalog_without_global_shims(self):
        for source in (PS1, SH):
            for required in ("UV_PYTHON_INSTALL_DIR", "UV_CACHE_DIR", "UV_PYTHON_BIN_DIR", "--no-bin", "--no-config", "--offline", "--python-downloads-json-url", "python-downloads.json"):
                self.assertIn(required, source)
            self.assertIn(".local/cache/uv", source)
            self.assertIn(".local/tools", source)
            self.assertIn("3.12.12", source)
            self.assertIn("20251014", source)
        self.assertIn("--no-registry", PS1)

    def test_check_exits_before_setup_writes(self):
        self.assertLess(PS1.index("if ($Check)"), PS1.index("$RunRoot ="))
        self.assertLess(SH.index("if $check;"), SH.index('mkdir -p -- "$path"'))
        self.assertIn("'.local/build/s'", PS1)
        self.assertIn('$local_root/build/sXXXXXXXX', SH)
        self.assertIn("$env:TEMP = $RunRoot", PS1)
        self.assertIn('TMPDIR="$run_root"', SH)

    def test_unverified_downloads_are_never_executed(self):
        for source in (PS1, SH):
            self.assertIn("SHA-256 mismatch", source)
            self.assertIn("retained for diagnosis", source)
            self.assertIn("Incomplete or unrecognized installation", source)
            self.assertIn("Linked setup path is not allowed", source)
        self.assertLess(PS1.index('Get-FileHash -LiteralPath $partial'), PS1.index('Move-Item -LiteralPath $partial'))
        self.assertLess(SH.index('file_hash "$partial"'), SH.index('mv -- "$partial"'))


@unittest.skipUnless(HOSTS, "requires Windows PowerShell")
class SetupPowerShellTests(unittest.TestCase):
    def fixture(self):
        # Keep fixtures under a new local run even when unittest's TEMP is global.
        build = SCRIPTS.parent / ".local" / "build"
        build.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(prefix="setup-test-", dir=build)
        self.addCleanup(temp.cleanup)
        return Path(temp.name)

    def test_check_is_read_only_and_reports_all_missing_tools(self):
        root = self.fixture()
        scripts = root / "scripts"
        scripts.mkdir()
        script = scripts / "gx_shell_setup.ps1"
        shutil.copyfile(SCRIPTS / script.name, script)
        for host in HOSTS:
            with self.subTest(host=host):
                result = run_ps(host, "& " + ps_quote(script) + " -Check -InnoSetup; exit $LASTEXITCODE")
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                for name in ("python", "actionlint", "ISCC"):
                    self.assertIn("MISSING " + name, result.stdout)
                self.assertFalse((root / ".local").exists())

    def test_corrupt_cached_download_fails_without_replacing_it(self):
        root = self.fixture()
        cache = root / ".local" / "cache" / "setup"
        cache.mkdir(parents=True)
        archive = cache / "bad.zip"
        archive.write_bytes(b"invalid cached archive")
        for host in HOSTS:
            with self.subTest(host=host):
                source = (
                    "$ErrorActionPreference='Stop'; $tokens=$null; $errors=$null; "
                    "$ast=[Management.Automation.Language.Parser]::ParseFile("
                    + ps_quote(SCRIPTS / "gx_shell_setup.ps1")
                    + ", [ref]$tokens, [ref]$errors); if ($errors.Count) { throw 'Parse failed' }; "
                    "$ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst]}, $false) "
                    "| ForEach-Object { . ([scriptblock]::Create($_.Extent.Text)) }; "
                    "$LocalRoot=" + ps_quote(root / ".local") + "; $CacheRoot=" + ps_quote(cache) + "; "
                    "try { Get-VerifiedDownload 'https://invalid.example/unreachable' ('a'*64) 'bad.zip'; exit 2 } "
                    "catch { if ($_.Exception.Message -notlike '*SHA-256 mismatch*') { throw }; exit 0 }"
                )
                result = run_ps(host, source)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(archive.read_bytes(), b"invalid cached archive")
                self.assertEqual(list(cache.iterdir()), [archive])


if __name__ == "__main__":
    unittest.main()

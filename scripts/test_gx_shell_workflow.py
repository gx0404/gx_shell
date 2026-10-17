import os
from pathlib import Path
import re
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ValidationWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / '.github/workflows/release.yml').read_text(encoding='utf-8')
        cls.dockerfile = (ROOT / 'packaging/debian/smoke.Dockerfile').read_text(encoding='utf-8')

    def job(self, name):
        match = re.search(r'^  ' + re.escape(name) + r':\n(.*?)(?=^  [a-z][a-z0-9-]*:|\Z)',
                          self.workflow, re.M | re.S)
        self.assertIsNotNone(match, name)
        return match.group(1)

    def test_deb_smoke_runs_on_ubuntu_24_04_only(self):
        smoke = self.job('smoke-linux')
        self.assertIn("ubuntu: ['24.04']", smoke)
        self.assertNotIn('20.04', self.workflow)
        self.assertNotIn('22.04', self.workflow)
        self.assertIn('name: release-linux', smoke)
        self.assertIn('--build-arg "UBUNTU_VERSION=$GX_UBUNTU"', smoke)
        self.assertIn('--env GX_SMOKE_DIST=/workspace/dist', smoke)
        self.assertIn('--volume "$PWD:/workspace:ro"', smoke)

    def test_smoke_evidence_is_a_new_child_of_the_mount(self):
        smoke = self.job('smoke-linux')
        self.assertIn('--volume "$RUNNER_TEMP/evidence:/evidence"', smoke)
        self.assertIn('--env GX_SMOKE_EVIDENCE=/evidence/lifecycle', smoke)
        self.assertNotRegex(smoke, r'GX_SMOKE_EVIDENCE=/evidence(?:\s|$)')
        self.assertIn('git config --global --add safe.directory /sources/ohmyzsh', smoke)
        self.assertNotIn('safe.directory *', smoke)
        self.assertIn('--env GITHUB_ACTIONS --env', smoke)
        self.assertNotIn('--env GITHUB_ACTIONS=true', smoke)

    def test_smoke_python_is_private_pinned_and_shared_by_the_entrypoint(self):
        versions = set(re.findall(r"python-version: '([0-9.]+)'", self.workflow))
        self.assertEqual(len(versions), 1)
        version = next(iter(versions))
        self.assertIn(f'https://www.python.org/ftp/python/{version}/Python-{version}.tar.xz', self.dockerfile)
        self.assertRegex(self.dockerfile, r"echo '[0-9a-f]{64}  /tmp/Python-[0-9.]+\.tar\.xz' \| sha256sum --check --strict")
        self.assertLess(self.dockerfile.index('sha256sum --check --strict'), self.dockerfile.index('tar -xf'))
        self.assertIn('--prefix=/opt/gx-smoke-python', self.dockerfile)
        self.assertIn('make altinstall', self.dockerfile)
        self.assertNotIn('update-alternatives', self.dockerfile)
        interpreter = '/opt/gx-smoke-python/bin/python' + '.'.join(version.split('.')[:2])
        self.assertIn('ENV GX_SMOKE_PYTHON=' + interpreter, self.dockerfile)
        self.assertIn('--env GX_SMOKE_PYTHON=' + interpreter, self.job('smoke-linux'))

    def test_wezterm_is_gone_and_ghostty_gx_follows_its_consumer_contract(self):
        self.assertNotRegex(self.workflow, r'(?i)wezterm|nextest|cargo ')
        setup_zig = ('uses: mlugg/setup-zig@d1434d08867e3ee9daa34448df10607b98908d29 # v2.2.1\n'
                     '        with:\n          version: ${{ needs.prepare.outputs.zig }}\n          use-cache: false')
        windows = self.job('ghostty-windows')
        self.assertIn('runs-on: windows-2025', windows)
        self.assertLess(windows.index('git config --global core.autocrlf false'), windows.index('uses: actions/checkout@v5'))
        self.assertIn('["gx_ghostty"]', windows)
        self.assertIn(setup_zig, windows)
        self.assertIn("$stage = Join-Path $env:RUNNER_TEMP 'ghostty-gx-stage'", windows)
        build = windows.index('python scripts/gx_package.py windows --build --stage-dir $stage '
                              '--version-string $env:GX_VERSION_STRING\n'
                              '          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }')
        self.assertLess(build, windows.index('python scripts/gx_package.py verify-stage $stage\n'
                                             '          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }'))
        self.assertIn('GX_VERSION_STRING: ${{ needs.prepare.outputs.ghostty_version_string }}', windows)
        linux = self.job('ghostty-linux')
        self.assertIn('container:\n      image: ubuntu:24.04', linux)
        self.assertLess(linux.index('apt-get install -y --no-install-recommends ca-certificates git python3'),
                        linux.index('uses: actions/checkout@v5'))
        self.assertIn('--component gx_ghostty', linux)
        self.assertLess(linux.index('python3 scripts/gx_package.py deb --build --install-deps '
                                    '--stage-dir "$RUNNER_TEMP/ghostty-gx-stage"'),
                        linux.index('python3 scripts/gx_package.py verify-stage "$RUNNER_TEMP/ghostty-gx-stage"'))
        self.assertNotIn('setup-python', linux)
        for name in ('ghostty-windows', 'ghostty-linux', 'ghostty-tests'):
            timeout = int(re.search(r'^    timeout-minutes: (\d+)$', self.job(name), re.M).group(1))
            self.assertTrue(90 <= timeout <= 120, f'{name} timeout-minutes {timeout}')
        tests = self.job('ghostty-tests')
        self.assertIn(setup_zig, tests)
        self.assertIn('python scripts/run_unittests.py test_gx_package test_gx_release', tests)
        self.assertIn('python scripts/zig_test.py --suite main -Dapp-runtime=none', tests)
        self.assertIn('ghostty-tests', self.job('verify'))
        prepare = self.job('prepare')
        self.assertIn('--component ohmyzsh --component gx_ghostty', prepare)
        for output in ('rust', 'zig', 'ghostty_version_string', 'lock_digest'):
            self.assertIn(f'{output}: ${{{{ steps.sources.outputs.{output} }}}}', prepare)
        self.assertIn('build.ghostty_version_string(ghostty, dict(os.environ))', prepare)

    def test_windows_installer_runs_coordinator_tests_with_pinned_inno_setup(self):
        coordinator = "python -B -m unittest discover -s scripts -p 'test_gx_shell_*.py'"
        self.assertNotIn(coordinator, self.job('ghostty-windows'))
        package = self.job('package-windows')
        self.assertIn('needs: [prepare, ghostty-windows, shell-windows]', package)
        self.assertIn('--ghostty-stage "$env:RUNNER_TEMP/ghostty-stage"', package)
        self.assertIn('--ghostty-stage "$RUNNER_TEMP/ghostty-stage"', self.job('package-linux'))
        ordered = (
            'name: Install checksum-pinned Inno Setup',
            '$installed = Start-Process -FilePath $installer',
            'if ($installed.ExitCode -ne 0) { throw "Inno Setup failed: $($installed.ExitCode)" }',
            "\"ISCC=$(Join-Path $destination 'ISCC.exe')\" >> $env:GITHUB_ENV",
            'name: Coordinator tests with pinned Inno Setup',
            coordinator,
            'name: Assemble and build the GX Shell installer',
            'python scripts/gx_shell_package.py assemble --platform windows',
            'python scripts/gx_shell_package.py build --assembly',
        )
        for before, after in zip(ordered, ordered[1:]):
            with self.subTest(before=before, after=after):
                self.assertLess(package.index(before), package.index(after))
        self.assertIn('if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }',
                      package[package.index(coordinator):package.index(ordered[6])])

    def test_runtime_payload_is_archived_only_after_lifecycle(self):
        package = self.job('package-windows')
        lifecycle = package.index('./scripts/gx_shell_smoke_windows.ps1')
        archive = package.index('name: Archive the Windows payload after lifecycle validation')
        upload = package.index('name: runtime-windows')
        self.assertLess(lifecycle, archive)
        self.assertLess(archive, upload)
        self.assertIn('p.check_assembly(', package[archive:upload])
        self.assertIn('tar -cf $archive -C $env:RUNNER_TEMP assembly', package[archive:upload])
        self.assertIn('runtime-windows.tar.sha256', package)

    def test_nonpublish_runs_both_platform_verification(self):
        verify = self.job('verify')
        self.assertIn("if: needs.prepare.outputs.source_run_id == ''", verify)
        self.assertIn('package-windows, package-linux, smoke-linux', verify)
        self.assertIn('pattern: release-*', verify)
        self.assertIn('python scripts/gx_shell_package.py verify --dir dist', verify)
        self.assertIn('--components-lock components.lock.json', verify)
        self.assertIn('path: dist/SHA256SUMS', verify)
        self.assertNotIn('version --release', verify)
        self.assertNotIn('gh release create', verify)
        publish = self.job('publish')
        self.assertIn('needs: [prepare, verify]', publish)
        self.assertIn("needs.prepare.outputs.publish == 'true'", publish)


    IDENTITY_ZIG = '''const Identity = @This();
pub const installed_aumid = "gx0404.GhosttyGX";
pub const installed_activator = "978ab84b-3cac-4593-95d5-2e04d68eed4f";
pub const action_switch = "--gx-shell-action=";
pub const server_argument = "--gx-shell-action=toast-server";
pub const profile_argument = "--gx-shell-action=profile";
pub const manifest = .{ .aumid = installed_aumid, .activator_clsid = installed_activator, .local_server_argument = server_argument, .profile_action_argument = profile_argument };
'''
    INSTALLER = '''#define GhosttyAumid "gx0404.GhosttyGX"
#define GhosttyActivator "978AB84B-3CAC-4593-95D5-2E04D68EED4F"
[Setup]
AppId={{EDDE7553-FF3A-4F95-B9A5-E4D037FEE617}
[Registry]
Root: HKCU; Subkey: "Software\\Classes\\CLSID\\{{{#GhosttyActivator}}\\LocalServer32"; ValueData: """{app}\\ghostty\\ghostty.exe"" --gx-shell-action=toast-server"
'''

    def shell_identity_check(self):
        step = self.job('prepare')
        start = step.index('name: Bind lock digest, component dependency identity and toolchains')
        step = step[start:]
        begin = step.index("          # The installer hard-codes Ghostty GX's Windows shell identity")
        end = step.index('          version_string = build.ghostty_version_string(')
        return step, textwrap.dedent(step[begin:end])

    def run_shell_identity_check(self, identity, installer):
        _, code = self.shell_identity_check()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ghostty = root / 'sources/gx_ghostty'
            (ghostty / 'src/apprt/win32/shell').mkdir(parents=True)
            (ghostty / 'src/apprt/win32/shell/Identity.zig').write_text(identity, encoding='utf-8')
            (root / 'packaging/windows').mkdir(parents=True)
            (root / 'packaging/windows/gx-shell.iss').write_text(installer, encoding='utf-8-sig')
            previous = os.getcwd()
            os.chdir(root)
            try:
                exec(code, {'re': re, 'Path': Path, 'ghostty': ghostty})
            finally:
                os.chdir(previous)

    def test_installer_shell_identity_matches_the_locked_ghostty_revision(self):
        step, code = self.shell_identity_check()
        self.assertLess(step.index('ghostty = root / "sources/gx_ghostty"'), step.index(code.splitlines()[0].strip()))
        for needle in ('ghostty / "src/apprt/win32/shell/Identity.zig"', 'Path("packaging/windows/gx-shell.iss")',
                       'installed_aumid', 'installed_activator', 'server_argument', 'pub const manifest',
                       'local_server_argument', 'activator_clsid'):
            self.assertIn(needle, code)
        self.assertLess(step.index('Ghostty GX must pin an exact Zig version'), step.index('Identity.zig'))
        self.assertLess(step.index('Identity.zig'), step.index('GITHUB_OUTPUT'))
        self.run_shell_identity_check(self.IDENTITY_ZIG, self.INSTALLER)
        mismatches = {
            'aumid': (self.IDENTITY_ZIG, self.INSTALLER.replace('gx0404.GhosttyGX', 'gx0404.GhosttyGX.Other')),
            'activator': (self.IDENTITY_ZIG, self.INSTALLER.replace('978AB84B', '978AB84C')),
            'server': (self.IDENTITY_ZIG, self.INSTALLER.replace('toast-server', 'toast')),
            'locked aumid': (self.IDENTITY_ZIG.replace('"gx0404.GhosttyGX"', '"gx0404.Ghostty"'), self.INSTALLER),
            'manifest': (self.IDENTITY_ZIG.replace('local_server_argument = server_argument',
                                                   'local_server_argument = profile_argument'), self.INSTALLER),
            'no manifest': (self.IDENTITY_ZIG.replace('pub const manifest', 'const manifest'), self.INSTALLER),
        }
        for name, (identity, installer) in mismatches.items():
            with self.subTest(name), self.assertRaises(SystemExit):
                self.run_shell_identity_check(identity, installer)

if __name__ == '__main__':
    unittest.main()

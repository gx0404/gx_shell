from pathlib import Path
import re
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

    def test_same_deb_reaches_both_ubuntu_versions(self):
        smoke = self.job('smoke-linux')
        self.assertIn("ubuntu: ['20.04', '24.04']", smoke)
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

    def test_windows_runs_native_nextest_and_coordinator_tests(self):
        windows = self.job('wezterm-windows')
        self.assertIn('runs-on: windows-2025', windows)
        self.assertIn('tool: cargo-nextest@${{ needs.prepare.outputs.nextest }}', windows)
        self.assertIn('cargo nextest run --locked -p config -p mux -p wezterm-gui --no-fail-fast --test-threads 2', windows)
        self.assertIn("python -B -m unittest discover -s scripts -p 'test_gx_shell_*.py'", windows)
        self.assertIn('if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }', windows)

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
        self.assertNotRegex(verify, re.compile(r'^    if:', re.M))
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


if __name__ == '__main__':
    unittest.main()

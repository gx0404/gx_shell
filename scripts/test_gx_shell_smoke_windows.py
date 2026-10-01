"""Windows smoke safety/receipt fixtures: never install or execute product binaries."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import types
import unittest
import zlib

import gx_shell_package as package
import gx_shell_sources as sources
from test_gx_shell_package import SHA, ohmyzsh_stage, wezterm_stage, write, write_lock

ROOT = Path(__file__).resolve().parents[1]
GPU = ROOT / 'scripts/gx_shell_smoke_gpu_windows.ps1'
LIFECYCLE = ROOT / 'scripts/gx_shell_smoke_windows.ps1'
PWSH = shutil.which('pwsh')


def load_helper():
    text = GPU.read_text(encoding='utf-8')
    code = re.search(r"(?ms)^\$gpuHelper = @'\n(.*?)^'@", text).group(1)
    module = types.ModuleType('gpu_smoke_fixture')
    exec(compile(code, str(GPU), 'exec'), module.__dict__)
    return module


HELPER = load_helper()


def png(path, shade):
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
    header = struct.pack('>IIBBBBB', 320, 200, 8, 2, 0, 0, 0)
    pixels = (b'\0' + bytes([shade]) * (320 * 3)) * 200
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b''))


class GpuInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='gx-smoke-fixture-')
        self.addCleanup(self.cleanup_fixture)
        self.root = Path(self.temp.name)
        self.lock = write_lock(self.root / 'source')
        self.assembly = self.root / 'assembly'
        self.info = package.assemble('windows', wezterm_stage(self.root, 'windows'),
                                     ohmyzsh_stage(self.root, 'windows'), self.assembly,
                                     version='0.1.0', sha=SHA, dirty=False, epoch=1700000000,
                                     components_lock=self.lock)
        self.dist = self.root / 'dist'
        self.dist.mkdir()
        name, source_name = package.artifact_names('0.1.0', 'windows')
        self.installer = self.dist / name
        self.installer.write_bytes(b'fixture only; this is NOT an executable')
        package.source_archive(self.assembly / 'redistribution', self.dist / source_name, 1700000000)
        package.finish_artifacts(self.dist, self.info, name, source_name)
        self.metadata = self.dist / (name + '.manifest.json')
        self.digest = package.digest(self.metadata)

    def cleanup_fixture(self):
        import time

        for attempt in range(5):
            try:
                self.temp.cleanup()
                return
            except OSError as error:
                if getattr(error, 'winerror', None) not in (32, 145) or attempt == 4:
                    raise
                time.sleep(0.1 * 2 ** attempt)

    def verify(self, **overrides):
        args = dict(installer=self.installer, metadata=self.metadata, lock_path=self.lock,
                    assembly=self.assembly, coordinator=SHA, lock_digest=package.digest(self.lock), manifest_hash=self.digest)
        args.update(overrides)
        return HELPER.verify_inputs(package, **args)

    def arguments(self, action='VerifyInputs', evidence=None):
        return [str(ROOT), action, str(self.installer), str(self.metadata), str(self.lock),
                str(self.assembly), SHA, package.digest(self.lock), self.digest,
                str(evidence or self.root / 'evidence'), 'OpenGL', '']

    def test_verified_fixture_never_claims_runtime_acceptance(self):
        result = self.verify()
        self.assertEqual(result['status'], 'INPUTS_VERIFIED')
        self.assertEqual(result['gpu_acceptance'], 'NOT_RUN')
        self.assertFalse(result['images_reviewed'])
        self.assertEqual(result['payload_files'], len(self.info['payload']))
        lock = json.loads(self.lock.read_text())
        self.assertEqual({name: entry['branch'] for name, entry in lock['components'].items()}, sources.COMPONENT_BRANCHES)

    def test_corrupt_installer_is_rejected(self):
        self.installer.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'hash or size'):
            self.verify()

    def test_trusted_manifest_digest_is_required(self):
        with self.assertRaisesRegex(ValueError, 'trusted package manifest'):
            self.verify(manifest_hash='0' * 64)

    def test_trusted_lock_digest_is_required(self):
        with self.assertRaisesRegex(ValueError, 'trusted components lock'):
            self.verify(lock_digest='0' * 64)

    def test_coordinator_is_not_taken_from_untrusted_manifest(self):
        with self.assertRaisesRegex(ValueError, 'coordinator'):
            self.verify(coordinator='f' * 40)

    def test_payload_missing_changed_and_extra_files_are_rejected(self):
        target = self.assembly / 'payload/bin/gx-zsh.exe'
        original = target.read_bytes()
        for change in ('missing', 'changed', 'extra'):
            with self.subTest(change=change):
                if change == 'missing':
                    target.unlink()
                elif change == 'changed':
                    target.write_bytes(b'changed payload')
                else:
                    write(self.assembly / 'payload/extra.dll')
                with self.assertRaisesRegex(ValueError, 'inventory mismatch'):
                    self.verify()
                target.write_bytes(original)
                (self.assembly / 'payload/extra.dll').unlink(missing_ok=True)

    def test_full_assembly_not_just_payload_is_verified(self):
        for directory in ('redistribution', 'build-inputs'):
            path = next(p for p in (self.assembly / directory).rglob('*') if p.is_file())
            original = path.read_bytes()
            with self.subTest(directory=directory):
                path.write_bytes(b'not the CI input')
                with self.assertRaisesRegex(ValueError, 'inventory mismatch'):
                    self.verify()
                path.write_bytes(original)

    def test_mixed_assembly_identity_is_rejected(self):
        self.info['version'] = '0.9.9'
        package.write_json(self.assembly / 'assembly-manifest.json', self.info)
        with self.assertRaisesRegex(ValueError, 'complete assembly identity'):
            self.verify()

    def test_local_build_cannot_enter_gpu_ci_receipt_gate(self):
        manifest = package.read_json(self.metadata)
        manifest.update(publishable=False, local_build=True)
        package.write_json(self.metadata, manifest)
        with self.assertRaisesRegex(ValueError, 'development build'):
            self.verify(manifest_hash=package.digest(self.metadata))

    def test_old_gx_branch_lock_is_rejected(self):
        lock = json.loads(self.lock.read_text())
        lock['components']['wezterm']['branch'] = 'gx'
        package.write_json(self.lock, lock)
        with self.assertRaisesRegex(ValueError, 'feature/gx_wezterm'):
            self.verify()

    def test_sidecar_and_corresponding_source_are_required(self):
        sidecar = self.dist / (self.installer.name + '.sha256')
        original = sidecar.read_bytes()
        sidecar.write_text('stale\n')
        with self.assertRaisesRegex(ValueError, 'sidecar'):
            self.verify()
        sidecar.write_bytes(original)
        next(self.dist.glob('*sources.tar.xz')).unlink()
        with self.assertRaisesRegex(ValueError, 'regular input'):
            self.verify()

    def test_run_writes_explicit_blocked_receipt_without_launching(self):
        self.assertEqual(HELPER.main(self.arguments('Run')), 3)
        receipt = package.read_json(self.root / 'evidence/gpu-smoke.json')
        self.assertEqual(receipt['status'], 'BLOCKED_UNSAFE_KNOWNFOLDERS')
        self.assertEqual(receipt['gpu_acceptance'], 'NOT_RUN')
        self.assertFalse((self.root / 'evidence/profile').exists())

    def test_evidence_refuses_existing_or_input_directory(self):
        for path in (self.root, self.assembly / 'evidence', self.dist / 'evidence'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                HELPER.main(self.arguments(evidence=path))
        self.assertFalse((self.assembly / 'evidence').exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows junction fixture')
    def test_assembly_parent_junction_is_rejected(self):
        junction = self.root / 'assembly-alias'
        result = subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(junction), str(self.assembly)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        try:
            with self.assertRaisesRegex(ValueError, 'reparse point'):
                self.verify(assembly=junction)
        finally:
            junction.rmdir()

    @unittest.skipUnless(PWSH, 'PowerShell 7 not installed')
    def test_real_powershell_gpu_entry_only_verifies_or_refuses(self):
        for action in ('VerifyInputs', 'Run'):
            evidence = self.root / action
            command = [PWSH, '-NoProfile', '-NonInteractive', '-File', str(GPU), '-Action', action,
                       '-Installer', str(self.installer), '-PackageManifest', str(self.metadata),
                       '-ComponentsLock', str(self.lock), '-Assembly', str(self.assembly),
                       '-ExpectedCoordinator', SHA, '-ExpectedLockDigest', package.digest(self.lock),
                       '-ExpectedManifestSha256', self.digest, '-Evidence', str(evidence), '-Python', sys.executable]
            result = subprocess.run(command, text=True, capture_output=True, timeout=60)
            self.assertEqual(result.returncode == 0, action == 'VerifyInputs', result.stdout + result.stderr)
            self.assertEqual(package.read_json(evidence / 'gpu-smoke.json')['gpu_acceptance'], 'NOT_RUN')


class GpuEvidenceTests(unittest.TestCase):
    def test_hardware_renderer_log_formats(self):
        self.assertTrue(HELPER.renderer_evidence('OpenGL initialized! OpenGL: Intel(R) Iris(R) Xe Graphics 4.6 wezterm version: x', 'OpenGL'))
        text = ('Using adapter: AdapterInfo { name: "NVIDIA GeForce RTX 4060", device_type: DiscreteGpu, backend: Dx12 }\n'
                'OpenGL initialized! WebGPU: NVIDIA GeForce RTX 4060 wezterm version: x')
        self.assertTrue(HELPER.renderer_evidence(text, 'WebGpu'))

    def test_software_unknown_and_adapter_enumeration_do_not_pass(self):
        for renderer in ('llvmpipe', 'GDI Generic', 'Microsoft Basic Render Driver', 'WARP', 'unknown'):
            with self.subTest(renderer=renderer), self.assertRaises(ValueError):
                HELPER.renderer_evidence('OpenGL initialized! OpenGL: ' + renderer, 'OpenGL')
        for text in ('available adapters: NVIDIA',
                     'Using adapter: AdapterInfo { name: "CPU", device_type: Cpu, backend: Dx12 }',
                     'Using adapter: AdapterInfo { name: "NVIDIA", device_type: DiscreteGpu, backend: Dx12 }'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                HELPER.renderer_evidence(text, 'WebGpu')

    def test_evidence_ready_is_not_desktop_or_gpu_acceptance(self):
        with tempfile.TemporaryDirectory(prefix='gx-evidence-fixture-') as directory:
            root = Path(directory)
            receipt = {key: 'a' * 64 for key in ('package_sha256', 'package_manifest_sha256',
                       'assembly_manifest_sha256', 'components_lock_digest')}
            token = 'b' * 32
            observation = dict(receipt, renderer='OpenGL', default_front_end=True, token=token)
            (root / 'renderer.log').write_text('OpenGL initialized! OpenGL: NVIDIA GeForce RTX 4060 4.6')
            (root / 'input.txt').write_text('GX_GPU_INPUT_' + token)
            (root / 'echo.txt').write_text('GX_GPU_ECHO_' + token + '\nGX_GPU_REDRAW_' + token + '\n')
            png(root / 'before.png', 0)
            png(root / 'after.png', 100)
            observation['files'] = {p.name: package.digest(p) for p in root.iterdir()}
            package.write_json(root / 'observation.json', observation)
            result = HELPER.check_evidence(package, root, receipt, 'OpenGL')
            self.assertEqual(result['status'], 'EVIDENCE_READY')
            self.assertEqual(result['gpu_acceptance'], 'PENDING')
            self.assertFalse(result['images_reviewed'])
            self.assertFalse(result['desktop_interaction_verified'])
            (root / 'after.png').unlink()
            with self.assertRaisesRegex(ValueError, 'regular input'):
                HELPER.check_evidence(package, root, receipt, 'OpenGL')

    def test_screenshot_failure_cannot_be_ignored(self):
        with tempfile.TemporaryDirectory(prefix='gx-png-fixture-') as directory:
            path = Path(directory) / 'image.png'
            for data in (b'', b'not png', b'\x89PNG\r\n\x1a\n'):
                path.write_bytes(data)
                with self.assertRaises(ValueError):
                    HELPER.png_dimensions(path)
            png(path, 0)
            path.write_bytes(path.read_bytes()[:-10])
            with self.assertRaises(ValueError):
                HELPER.png_dimensions(path)


class WindowsSafetyTests(unittest.TestCase):
    @unittest.skipUnless(PWSH, 'PowerShell 7 not installed')
    def test_powershell_parser_checks_both_scripts_without_execution(self):
        for path in (GPU, LIFECYCLE):
            command = ("$tokens=$null; $errors=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('"
                       + str(path).replace("'", "''") + "',[ref]$tokens,[ref]$errors); if($errors.Count){$errors | Out-String; exit 1}")
            result = subprocess.run([PWSH, '-NoProfile', '-NonInteractive', '-Command', command],
                                    text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(PWSH, 'PowerShell 7 not installed')
    def test_installer_entry_refuses_non_hosted_machine_before_writes(self):
        with tempfile.TemporaryDirectory(prefix='gx-refusal-fixture-') as directory:
            evidence = Path(directory) / 'must-not-exist'
            env = dict(os.environ)
            env.pop('GITHUB_ACTIONS', None)
            env.pop('RUNNER_ENVIRONMENT', None)
            result = subprocess.run([PWSH, '-NoProfile', '-NonInteractive', '-File', str(LIFECYCLE),
                                     '-Installer', str(Path(directory) / 'not-an-installer.exe'), '-Evidence', str(evidence)],
                                    env=env, text=True, capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Refusing to install on this machine', result.stdout + result.stderr)
            self.assertFalse(evidence.exists())

    @unittest.skipUnless(PWSH, 'PowerShell 7 not installed')
    def test_profile_hash_comparison_detects_changes_and_missing_files(self):
        script = r'''
$ErrorActionPreference = 'Stop'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:GX_SMOKE_TEST_SCRIPT,[ref]$tokens,[ref]$errors)
$names=@('Assert','Assert-MapSame','Config-Files','UserData-State')
foreach($f in $ast.FindAll({param($a) $a -is [System.Management.Automation.Language.FunctionDefinitionAst]},$true)){
    if($f.Name -in $names){ . ([scriptblock]::Create($f.Extent.Text)) }
}
$config=Join-Path $env:GX_SMOKE_TEST_ROOT 'config'
$profile=Join-Path $env:GX_SMOKE_TEST_ROOT 'profile'
New-Item -ItemType Directory $config,$profile | Out-Null
Set-Content (Join-Path $config 'gui-settings.json') '{"font_size":12}'
Set-Content (Join-Path $profile '.zshrc.local') 'user-layer'
$before=UserData-State
Assert-MapSame $before (UserData-State) 'same'
Set-Content (Join-Path $profile '.zshrc.local') 'corrupted'
$caught=$false; try { Assert-MapSame $before (UserData-State) 'changed' } catch { $caught=$true }
if(-not $caught){ throw 'changed profile accepted' }
Remove-Item -Force (Join-Path $profile '.zshrc.local')
$caught=$false; try { Assert-MapSame $before (UserData-State) 'missing' } catch { $caught=$true }
if(-not $caught){ throw 'missing profile accepted' }
$baseline=@{'user-path-entries'='["%USERPROFILE%/tools"]'; 'font:third-party'='original font'; 'shortcut:third-party'='original hash'}
foreach($name in $baseline.Keys){
    $changed=$baseline.Clone(); $changed[$name]='changed'
    $caught=$false; try { Assert-MapSame $baseline $changed 'non-owned' } catch { $caught=$true }
    if(-not $caught){ throw "non-owned mutation accepted: $name" }
    $missing=$baseline.Clone(); $missing.Remove($name)
    $caught=$false; try { Assert-MapSame $baseline $missing 'non-owned' } catch { $caught=$true }
    if(-not $caught){ throw "non-owned removal accepted: $name" }
}
'''
        with tempfile.TemporaryDirectory(prefix='gx-profile-fixture-') as directory:
            result = subprocess.run([PWSH, '-NoProfile', '-NonInteractive', '-Command', script],
                                    env=dict(os.environ, GX_SMOKE_TEST_SCRIPT=str(LIFECYCLE), GX_SMOKE_TEST_ROOT=directory),
                                    text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_gpu_entry_has_no_payload_or_desktop_execution_backend(self):
        text = GPU.read_text(encoding='utf-8')
        for forbidden in ('Start-Process', 'Stop-Process', 'SendKeys', 'SendInput', 'SetEnvironmentVariable',
                          'AddFontResource', 'Set-ItemProperty', 'subprocess.', 'os.system', 'Popen('):
            self.assertNotIn(forbidden, text)
        self.assertIn('return 3 if action == \'Run\' else 0', text)

    def test_lifecycle_rechecks_are_wired_after_both_installations(self):
        text = LIFECYCLE.read_text(encoding='utf-8')
        for label in ('reinstall', 'install-again'):
            setup = text.index("Run-Setup $Installer '" + label + "'")
            runtime = text.index("Runtime-Recheck '" + label + "'")
            self.assertLess(setup, runtime)
            self.assertIn('Assert-UserData', text[setup:runtime])
        self.assertIn('Assert-UserData $userBefore $Label', text)
        self.assertIn('Assert-NonOwnedState $Label', text)
        self.assertIn('Run-HostedGuiWindow $Label', text)
        self.assertIn("Run-HostedGuiWindow 'install'", text)
        self.assertIn("desktop_input_echo_redraw = 'NOT_RUN'", text)
        self.assertIn('images_reviewed = $false', text)
        self.assertNotIn('Write-Host "Screenshot unavailable', text)


if __name__ == '__main__':
    unittest.main()

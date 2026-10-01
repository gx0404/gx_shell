"""Linux smoke contracts and isolated helpers; never run an installer or lifecycle."""
import ast
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/gx_shell_smoke_linux.sh'
TEXT = SCRIPT.read_text(encoding='utf-8')
BLOCKS = re.findall(r"^([^\n]*<<'PY'[^\n]*)\n(.*?)^PY$", TEXT, re.M | re.S)
if os.name == 'nt':
    git_bash = Path('C:/Program Files/Git/bin/bash.exe')
    BASH = str(git_bash) if git_bash.is_file() else None
else:
    BASH = shutil.which('bash')
PROTECTED = ('.config/wezterm/wezterm.lua', '.config/wezterm/gui-settings.json',
             '.config/ohmyzsh-gx/profile/.zshrc', '.local/share/gx-smoke/preserve.txt',
             '.local/state/gx-smoke/preserve.txt')


def block(marker):
    matches = [body for header, body in BLOCKS if marker in header]
    if len(matches) != 1:
        raise AssertionError(f'expected one Python block for {marker!r}: {len(matches)}')
    return matches[0]


def shell_path(path):
    path = Path(path).absolute()
    if os.name == 'nt':
        return '/' + path.drive[0].lower() + path.as_posix()[2:]
    return str(path)


class SmokeContracts(unittest.TestCase):
    def test_every_python_invocation_uses_the_selected_isolated_interpreter(self):
        self.assertEqual(len(BLOCKS), 7)
        for header, body in BLOCKS:
            with self.subTest(header=header):
                self.assertIn('"$GX_SMOKE_PYTHON" -I -B - ', header)
                ast.parse(body, feature_version=(3, 9))
        self.assertNotRegex(TEXT, r'(?m)^\s*(?:run_user\s+)?python(?:[0-9.]*)\s')
        self.assertIn("subprocess.run([sys.executable, '-I', '-B', str(probe)", block('$evidence/herdr-probe'))
        self.assertNotIn('eval ', TEXT)

    def test_python_floor_precedes_imports_and_all_mutating_lifecycle_steps(self):
        check = block('python_runtime=')
        self.assertLess(check.index('sys.version_info[:2]'), check.index('import gx_shell_package'))
        self.assertIn('minimum = (3, 9)', check)
        self.assertIn('import gx_shell_sources', check)
        self.assertNotIn('runpy', check)
        self.assertNotIn('gx_probe_herdr', check)
        self.assertLess(TEXT.index('python_runtime='), TEXT.index('mkdir -- "$evidence"'))
        self.assertLess(TEXT.index('python-user-runtime.json'), TEXT.index('apt-get install'))

    def test_locked_external_probe_is_verified_before_non_root_import(self):
        provenance = block('$package_manifest')
        for contract in ('not source.is_relative_to(repo.resolve())', "'--show-toplevel'",
                         "'--git-common-dir'", "source / '.git'", "'HEAD'",
                         "revision + ':scripts/gx_probe_herdr.py'", 'probe_bytes.replace'):
            self.assertIn(contract, provenance)
        self.assertNotIn('runpy', provenance)
        self.assertNotIn('importlib', provenance)
        user = block('python-user-runtime.json')
        self.assertLess(user.index('hashlib.sha256'), user.index('runpy.run_path'))
        self.assertIn('os.geteuid() == 0', user)
        self.assertIn("run_name='gx_smoke_probe_preflight'", user)
        self.assertLess(TEXT.index('$package_manifest'), TEXT.index('runpy.run_path'))

    def test_disposable_root_existing_install_and_fresh_evidence_guards_remain(self):
        for contract in ('--allow-system-install', 'Run as root inside the disposable container',
                         'Refusing to replace an existing gx-shell installation',
                         '[ -e "$evidence" ] || [ -L "$evidence" ]', 'mkdir -- "$evidence"'):
            self.assertIn(contract, TEXT)
        self.assertNotIn('mkdir -p "$evidence"', TEXT)
        self.assertNotIn('safe.directory', TEXT)

    def test_reinstall_repeats_the_shared_runtime_suite_before_remove(self):
        body = re.search(r'^assert_runtime\(\) \{\n.*?^\}', TEXT, re.M | re.S).group(0)
        for contract in ('assert_entry_points', 'run_user gx-zsh', 'run_user herdr --version',
                         'installed herdr hash differs', 'run_user herdr update', '#compdef herdr',
                         'run_user "$GX_SMOKE_PYTHON" -I -B - "$herdr_probe" "$evidence/herdr-probe"',
                         "'--zsh', '/usr/lib/ohmyzsh-gx/libexec/zsh/zsh'",
                         'run_user wezterm-gx --gx-initialize-only', 'run_user wezterm-gx ls-fonts',
                         'PURE_FN_TEST: ALL PASS', 'xvfb-run', 'LIBGL_ALWAYS_SOFTWARE=1',
                         'pgrep -P "$gui"', 'kill -0 "$gui"', 'linux.png'):
            self.assertIn(contract, body)
        calls = re.findall(r'^assert_runtime (.+)$', TEXT, re.M)
        self.assertEqual(calls, ['"$evidence" "$evidence/smoke-provenance.json"',
                                 '"$evidence/reinstall-runtime" "$evidence/smoke-provenance.json"'])
        reinstall = TEXT.index('apt-get install -y --reinstall')
        runtime = TEXT.index('assert_runtime "$evidence/reinstall-runtime"')
        self.assertLess(reinstall, runtime)
        self.assertLess(runtime, TEXT.index('step remove keeps user data'))
        self.assertIn('run_user mkdir -- "$evidence/reinstall-runtime"', TEXT)
        self.assertIn('cmp "$evidence/installed.txt" "$evidence/reinstalled.txt"', TEXT)

    def test_user_data_checks_follow_reinstall_runtime_remove_and_purge(self):
        for stage in ('after-reinstall', 'after-reinstall-runtime', 'after-remove', 'after-purge'):
            self.assertIn('assert_user_data ' + stage + '\n', TEXT)
        for field in ('sha256', 'mode', 'uid', 'gid'):
            self.assertIn(repr(field), block('$test_home'))
        self.assertIn('stat.S_ISREG(details.st_mode)', block('$test_home'))
        self.assertIn('diff -u "$evidence/user-data.before.json"', TEXT)
        self.assertIn('diff -u "$evidence/witness-home.before"', TEXT)
        self.assertIn('The witness and smoke accounts must have different UIDs', TEXT)

    def test_entry_points_retain_package_and_root_ownership_checks(self):
        body = re.search(r'^assert_entry_points\(\) \{\n.*?^\}', TEXT, re.M | re.S).group(0)
        for contract in ('gx-zsh herdr wezterm-gx wezterm-gx-gui', 'dpkg-query -S',
                         'readlink -f', "stat -c '%u:%g'", '= 0:0'):
            self.assertIn(contract, body)

    def test_no_old_release_or_hardware_gpu_success_is_implied(self):
        final = block('$evidence/smoke-provenance.json')
        self.assertIn("'previous_gx_shell': 'NOT_RUN'", final)
        self.assertIn("'hardware_gpu': 'NOT_RUN'", final)
        self.assertIn("'PASS_EXPLICIT_INPUT_ONLY' if sys.argv[2] else 'NOT_RUN'", final)
        self.assertNotRegex(TEXT, r'(?m)^\s*(?:curl|wget|gh release)\s')


class IsolatedPythonHelpers(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='gx-smoke-unit-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_block(self, marker, *args, prefix='', env=None):
        return subprocess.run([sys.executable, '-I', '-B', '-', *map(str, args)],
                              input=prefix + block(marker), cwd=self.root, env=env,
                              capture_output=True, text=True, encoding='utf-8', timeout=30)

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_runtime_preflight_imports_real_coordinator_modules_in_isolation(self):
        poison = self.root / 'poison'
        poison.mkdir()
        (poison / 'gx_shell_sources.py').write_text(
            "raise RuntimeError('PYTHONPATH leaked')\n", encoding='utf-8')
        result = self.run_block('python_runtime=', ROOT, env={**os.environ, 'PYTHONPATH': str(poison)})
        receipt = self.assert_success(result)
        self.assertEqual(receipt['minimum_version'], '3.9')
        self.assertEqual(receipt['imports'], ['gx_shell_package', 'gx_shell_sources'])
        self.assertEqual(Path(receipt['executable']), Path(sys.executable))
        self.assertFalse(list(poison.glob('__pycache__/*')))

    def test_python_38_is_rejected_before_coordinator_import(self):
        prefix = ("import sys\nfrom collections import namedtuple\n"
                  "sys.version_info = namedtuple('VersionInfo', 'major minor micro')(3, 8, 20)\n")
        result = self.run_block('python_runtime=', self.root / 'no-repository', prefix=prefix)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('GX_SMOKE_PYTHON must be Python >= 3.9; got 3.8.20', result.stderr)
        self.assertNotIn('ModuleNotFoundError', result.stderr)

    def make_probe(self):
        probe = self.root / 'gx_probe_herdr.py'
        probe.write_text("from pathlib import Path\n"
                         "Path(__file__).with_suffix('.imported').write_text('checked', encoding='utf-8')\n"
                         "if __name__ == '__main__':\n    raise RuntimeError('must not launch a pane')\n",
                         encoding='utf-8')
        (self.root / 'python-runtime.json').write_text(json.dumps({
            'executable': sys.executable, 'version': sys.version.split()[0]}), encoding='utf-8')
        (self.root / 'smoke-provenance.json').write_text(json.dumps({
            'herdr_probe': {'sha256': hashlib.sha256(probe.read_bytes()).hexdigest()}}), encoding='utf-8')
        return probe

    def test_probe_preflight_imports_verified_fixture_without_main(self):
        probe = self.make_probe()
        result = self.run_block('python-user-runtime.json', probe, self.root,
                                prefix='import os\nos.geteuid = lambda: 1001\n')
        receipt = self.assert_success(result)
        self.assertEqual(receipt['uid'], 1001)
        self.assertEqual(probe.with_suffix('.imported').read_text(encoding='utf-8'), 'checked')
        self.assertFalse((self.root / '__pycache__').exists())

    def test_probe_preflight_refuses_root_and_runtime_mismatch(self):
        probe = self.make_probe()
        result = self.run_block('python-user-runtime.json', probe, self.root,
                                prefix='import os\nos.geteuid = lambda: 0\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('non-root smoke account', result.stderr)
        (self.root / 'python-runtime.json').write_text(json.dumps({
            'executable': sys.executable, 'version': 'different'}), encoding='utf-8')
        result = self.run_block('python-user-runtime.json', probe, self.root,
                                prefix='import os\nos.geteuid = lambda: 1001\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Python runtimes differ', result.stderr)
        self.assertFalse(probe.with_suffix('.imported').exists())

    def test_changed_probe_is_not_imported(self):
        probe = self.make_probe()
        probe.write_text(probe.read_text(encoding='utf-8') + '# changed\n', encoding='utf-8')
        result = self.run_block('python-user-runtime.json', probe, self.root,
                                prefix='import os\nos.geteuid = lambda: 1001\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('herdr probe changed', result.stderr)
        self.assertFalse(probe.with_suffix('.imported').exists())

    def make_data(self):
        for relative in PROTECTED:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'user data\x00\xff\n')

    def test_user_snapshot_detects_same_size_content_change(self):
        self.make_data()
        before = self.assert_success(self.run_block('$test_home', self.root))
        self.assertEqual([record['path'] for record in before], list(PROTECTED))
        self.assertEqual(set(before[0]), {'path', 'sha256', 'mode', 'uid', 'gid'})
        target = self.root / PROTECTED[0]
        target.write_bytes(target.read_bytes().replace(b'user', b'edit'))
        after = self.assert_success(self.run_block('$test_home', self.root))
        self.assertNotEqual(before[0]['sha256'], after[0]['sha256'])
        self.assertEqual(before[1:], after[1:])

    def test_user_snapshot_rejects_missing_or_non_regular_file(self):
        self.make_data()
        target = self.root / PROTECTED[-1]
        target.unlink()
        result = self.run_block('$test_home', self.root)
        self.assertNotEqual(result.returncode, 0)
        target.mkdir()
        result = self.run_block('$test_home', self.root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('not a regular file', result.stderr)

    def test_final_receipt_discloses_upgrade_and_renderer_limits(self):
        self.make_probe()
        user = {'executable': sys.executable, 'version': sys.version.split()[0], 'uid': 1001}
        (self.root / 'python-user-runtime.json').write_text(json.dumps(user), encoding='utf-8')
        receipt_path = self.root / 'smoke-provenance.json'
        result = self.run_block('$evidence/smoke-provenance.json', receipt_path, '')
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        self.assertEqual(receipt['legacy_release_upgrade'], 'NOT_RUN')
        self.assertEqual(receipt['coverage']['previous_gx_shell'], 'NOT_RUN')
        self.assertEqual(receipt['coverage']['hardware_gpu'], 'NOT_RUN')
        self.assertEqual(receipt['coverage']['reinstall_runtime'], 'PASS')
        self.assertEqual(receipt['python_user_runtime'], user)


class ShortProbeRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='gx-short-probe-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = self.root / 'runtime'
        self.archive = self.root / ('evidence-' + 'x' * 80) / 'reinstall-runtime/herdr-probe'
        self.archive.parent.mkdir(parents=True)
        self.probe = self.root / 'locked-probe.py'
        self.namespace = {'__name__': 'gx_smoke_short_probe_test'}
        exec(compile(block('$evidence/herdr-probe'), str(SCRIPT), 'exec'), self.namespace)
        self.budget = self.namespace['probe_socket_budget']
        self.diagnostics = io.StringIO()

    def child(self, argv, *, stdout, stderr):
        self.assertEqual(argv[:4], [sys.executable, '-I', '-B', str(self.probe)])
        self.assertEqual(argv[4:8], ['--herdr', '/usr/lib/ohmyzsh-gx/lib/herdr/herdr',
                                    '--zsh', '/usr/lib/ohmyzsh-gx/libexec/zsh/zsh'])
        self.assertEqual(argv[8], '--output')
        output = Path(argv[9])
        self.assertEqual(output, self.runtime.resolve() / 'p')
        self.assertNotIn('evidence-', str(output))
        output.mkdir()
        (output / 'config').mkdir()
        (output / 'config/probe.toml').write_bytes(b'[terminal]\n')
        (output / 'server.log').write_bytes(b'probe-owned server stopped\n')
        (output / 'commands.json').write_bytes(b'[{"args": ["server", "stop"]}]\n')
        (output / 'pane.txt').write_bytes(b'GX-ZSH-fixture\n')
        result = {'status': 'FAIL' if self.returncode else 'PASS', 'output': str(output),
                  'session': 'gx-probe-' + 'f' * 16}
        payload = (json.dumps(result) + '\n').encode()
        (output / 'result.json').write_bytes(payload)
        stdout.write(payload)
        if self.returncode:
            stderr.write(b'fixture probe failed\n')
        return subprocess.CompletedProcess(argv, self.returncode)

    def invoke(self, returncode=0):
        self.returncode = returncode
        self.runtime.mkdir()
        self.allocate = mock.Mock(return_value=str(self.runtime))
        self.launch = mock.Mock(side_effect=self.child)
        self.budget_check = mock.Mock(return_value=self.budget(PurePosixPath('/tmp/gxh-abcdefgh/p')))
        with (mock.patch.object(tempfile, 'mkdtemp', self.allocate),
              mock.patch.object(subprocess, 'run', self.launch),
              mock.patch.dict(self.namespace, {'probe_socket_budget': self.budget_check}),
              contextlib.redirect_stderr(self.diagnostics)):
            return self.namespace['run_short_probe'](self.probe, self.archive)

    def test_pinned_socket_suffix_and_old_reinstall_failure(self):
        installed = self.budget(PurePosixPath('/evidence/lifecycle/herdr-probe'))
        self.assertEqual([item['bytes_with_nul'] for item in installed], [91, 98])
        with self.assertRaisesRegex(ValueError, 'sun_path capacity'):
            self.budget(PurePosixPath('/evidence/lifecycle/reinstall-runtime/herdr-probe'))
        short = self.budget(PurePosixPath('/tmp/gxh-abcdefgh/p'))
        self.assertEqual([item['bytes_with_nul'] for item in short], [79, 86])
        self.assertTrue(short[-1]['path_template'].endswith(
            '/config/herdr/sessions/gx-probe-ffffffffffffffff/herdr-client.sock'))

    def test_socket_budget_counts_utf8_and_the_nul_terminator(self):
        boundary = self.budget(PurePosixPath('/' + 'x' * 40))
        self.assertEqual(boundary[-1]['bytes_with_nul'], 108)
        with self.assertRaisesRegex(ValueError, 'sun_path capacity'):
            self.budget(PurePosixPath('/' + 'x' * 41))
        with self.assertRaisesRegex(ValueError, 'sun_path capacity'):
            self.budget(PurePosixPath('/' + '\u754c' * 14))

    def test_long_evidence_path_is_not_used_for_probe_execution(self):
        self.assertGreater(len(str(self.archive).encode('utf-8')), 108)
        self.assertEqual(self.invoke(), 0)
        self.allocate.assert_called_once_with(prefix='gxh-', dir='/tmp')
        self.launch.assert_called_once()
        self.budget_check.assert_called_once_with(self.runtime.resolve() / 'p')
        self.assertFalse(self.runtime.exists())
        self.assertEqual((self.archive / 'server.log').read_bytes(), b'probe-owned server stopped\n')
        self.assertTrue((self.archive / 'commands.json').is_file())
        self.assertTrue((self.archive / 'pane.txt').is_file())
        self.assertTrue((self.archive / 'config/probe.toml').is_file())
        raw = self.archive.with_suffix('.json').read_bytes()
        self.assertEqual((self.archive / 'result.json').read_bytes(), raw)
        self.assertEqual(json.loads(raw)['output'], str(self.runtime.resolve() / 'p'))
        receipt = json.loads(self.archive.with_name('herdr-probe.runtime.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['probe_exit_code'], 0)
        self.assertEqual(receipt['evidence_output'], str(self.archive))
        self.assertEqual(receipt['runtime_output'], json.loads(raw)['output'])
        self.assertEqual(receipt['socket_budget'][-1]['bytes_with_nul'], 86)

    def test_failed_probe_keeps_diagnostics_and_its_nonzero_status(self):
        self.assertEqual(self.invoke(returncode=37), 37)
        self.assertFalse(self.runtime.exists())
        self.assertIn('fixture probe failed', self.diagnostics.getvalue())
        self.assertTrue((self.archive / 'server.log').is_file())
        self.assertTrue((self.archive / 'commands.json').is_file())
        self.assertEqual(json.loads((self.archive / 'result.json').read_text(encoding='utf-8'))['status'], 'FAIL')
        receipt = json.loads(self.archive.with_name('herdr-probe.runtime.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['probe_exit_code'], 37)

    def test_copy_failure_retains_private_runtime_and_fails(self):
        with mock.patch.object(shutil, 'copytree', side_effect=OSError('fixture archive failure')):
            with self.assertRaisesRegex(OSError, 'fixture archive failure'):
                self.invoke()
        self.assertTrue((self.runtime / 'p/server.log').is_file())
        self.assertIn('runtime retained at', self.diagnostics.getvalue())
        self.assertTrue(self.archive.with_suffix('.json').is_file())

    def test_launch_error_is_not_swallowed(self):
        with mock.patch.object(self, 'child', side_effect=OSError('fixture launch failure')):
            with self.assertRaisesRegex(OSError, 'fixture launch failure'):
                self.invoke()
        self.assertTrue(self.archive.is_dir())
        self.assertFalse(self.runtime.exists())
        receipt = json.loads(self.archive.with_name('herdr-probe.runtime.json').read_text(encoding='utf-8'))
        self.assertIsNone(receipt['probe_exit_code'])

    def test_existing_evidence_is_never_overwritten(self):
        self.archive.mkdir()
        marker = self.archive / 'keep.txt'
        marker.write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError, 'evidence must be new'):
            self.invoke()
        self.allocate.assert_not_called()
        self.launch.assert_not_called()
        self.assertEqual(marker.read_bytes(), b'keep')

    def test_collector_excludes_links_sockets_and_fifos_without_following_them(self):
        copytree = shutil.copytree

        def collect(source, destination, *, ignore):
            modes = {'link': stat.S_IFLNK, 'socket': stat.S_IFSOCK, 'fifo': stat.S_IFIFO}
            for name in modes:
                (source / name).write_bytes(b'do not follow or archive')
            lstat = Path.lstat

            def fake_lstat(path, *args, **kwargs):
                if path.parent == source and path.name in modes:
                    return mock.Mock(st_mode=modes[path.name])
                return lstat(path, *args, **kwargs)

            with mock.patch.object(Path, 'lstat', fake_lstat):
                excluded = ignore(source, list(modes))
            self.assertEqual(set(excluded), set(modes))
            with mock.patch.object(shutil, 'copytree', copytree):
                return copytree(source, destination, ignore=lambda folder, names: excluded)

        with mock.patch.object(shutil, 'copytree', side_effect=collect):
            self.assertEqual(self.invoke(), 0)
        self.assertTrue((self.archive / 'server.log').is_file())
        receipt = json.loads(self.archive.with_name('herdr-probe.runtime.json').read_text(encoding='utf-8'))
        self.assertEqual(set(receipt['excluded_runtime_entries']), {'link', 'socket', 'fifo'})
        for name in ('link', 'socket', 'fifo'):
            self.assertFalse((self.archive / name).exists())

    def test_excessive_resolved_runtime_budget_prevents_launch(self):
        self.runtime.mkdir()

        def reject_budget(output):
            self.assertEqual(output, self.runtime.resolve() / 'p')
            return self.budget(PurePosixPath('/tmp/' + 'x' * 80 + '/p'))

        with (mock.patch.object(tempfile, 'mkdtemp', return_value=str(self.runtime)),
              mock.patch.object(subprocess, 'run') as launch,
              mock.patch.dict(self.namespace, {'probe_socket_budget': reject_budget})):
            with self.assertRaisesRegex(ValueError, 'sun_path capacity'):
                self.namespace['run_short_probe'](self.probe, self.archive)
        launch.assert_not_called()
        self.assertTrue(self.archive.is_dir())
        self.assertFalse(self.runtime.exists())

    def test_symlink_probe_root_is_not_followed_or_removed(self):
        original = Path.is_symlink
        output = self.runtime.resolve() / 'p'

        def is_symlink(path):
            return path == output or original(path)

        with mock.patch.object(Path, 'is_symlink', is_symlink):
            with self.assertRaisesRegex(OSError, 'must not be a symlink'):
                self.invoke()
        self.assertTrue((output / 'server.log').is_file())
        self.assertFalse(self.archive.exists())

    def test_both_phases_run_in_separate_fresh_private_directories(self):
        for phase in ('install', 'reinstall'):
            with self.subTest(phase=phase):
                self.runtime = self.root / ('runtime-' + phase)
                self.archive = self.archive.parent / ('probe-' + phase)
                self.assertEqual(self.invoke(), 0)
                self.launch.assert_called_once()
                self.assertTrue((self.archive / 'pane.txt').is_file())
                self.assertFalse(self.runtime.exists())


@unittest.skipUnless(BASH, 'requires native bash or Git Bash, never WSL')
class IsolatedShellHelpers(unittest.TestCase):
    def shell(self, body, env=None):
        return subprocess.run([BASH, '--noprofile', '--norc', '-c', body], input='',
                              env={**os.environ, 'BASH_ENV': '/dev/null', 'ENV': '/dev/null', **(env or {})},
                              capture_output=True, text=True, timeout=30)

    def test_whole_script_syntax_without_executing_it(self):
        result = subprocess.run([BASH, '-n'], input=TEXT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_python_selector_refuses_relative_and_missing_interpreters(self):
        start = TEXT.index(': "${GX_SMOKE_PYTHON:')
        guard = TEXT[start:TEXT.index('python_runtime=', start)]
        for value in ('python3', 'python3 -I', '/not-present/gx-python'):
            with self.subTest(value=value):
                result = self.shell('set -euo pipefail\n' + guard, {'GX_SMOKE_PYTHON': value})
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('GX_SMOKE_PYTHON', result.stderr)

    def test_fresh_evidence_creation_and_reuse_refusal(self):
        start = TEXT.index('if [ -e "$evidence" ]')
        end = TEXT.index("printf '%s\\n'", start)
        guard = TEXT[start:end]
        with tempfile.TemporaryDirectory(prefix='gx-smoke-evidence-unit-') as directory:
            output = Path(directory) / 'new evidence'
            result = self.shell('set -euo pipefail\n' + guard, {'evidence': shell_path(output)})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.is_dir())
            marker = output / 'existing.txt'
            marker.write_bytes(b'keep')
            result = self.shell('set -euo pipefail\n' + guard, {'evidence': shell_path(output)})
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn('Evidence output must be new', result.stderr)
            self.assertEqual(marker.read_bytes(), b'keep')


if __name__ == '__main__':
    unittest.main()

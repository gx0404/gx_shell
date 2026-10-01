"""Linux smoke contracts and isolated helpers; never run an installer or lifecycle."""
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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
        self.assertEqual(len(BLOCKS), 6)
        for header, body in BLOCKS:
            with self.subTest(header=header):
                self.assertIn('"$GX_SMOKE_PYTHON" -I -B - ', header)
                ast.parse(body, feature_version=(3, 9))
        self.assertNotRegex(TEXT, r'(?m)^\s*(?:run_user\s+)?python(?:[0-9.]*)\s')
        self.assertIn('run_user "$GX_SMOKE_PYTHON" -I -B "$herdr_probe"', TEXT)
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
                         'run_user "$GX_SMOKE_PYTHON" -I -B "$herdr_probe"',
                         '--zsh /usr/lib/ohmyzsh-gx/libexec/zsh/zsh',
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

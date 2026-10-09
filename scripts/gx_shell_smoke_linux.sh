#!/usr/bin/env bash
# GX Shell deb lifecycle smoke for a disposable Ubuntu 24.04 container (run as root): install, entry
# points, GX Zsh, herdr identity / managed update / completion / real Zsh pane, Ghostty GX identity and
# the bundled fonts, Ghostty GX running GX Zsh under Xvfb with software OpenGL, reinstall, removal and
# purge with user data preserved (the Ghostty GX configuration, the WezTerm configuration an earlier
# GX Shell left behind, the GX Zsh profile) and another account's HOME untouched.
# Required GX_SMOKE_PYTHON: absolute Python >= 3.9 with the standard library used by the
# coordinator package/source modules and the locked herdr probe; no system-python fallback.
# Exit status: 0 when every check passes; 2 when refused (not disposable); 1 on failure.
set -euo pipefail
if [ "${GITHUB_ACTIONS:-}" != true ] && [ "${1:-}" != --allow-system-install ]; then
    echo 'Use a disposable container, or pass --allow-system-install explicitly.' >&2
    exit 2
fi
if [ "$(id -u)" -ne 0 ]; then
    echo 'Run as root inside the disposable container.' >&2
    exit 2
fi
: "${GX_SMOKE_USER:?Set GX_SMOKE_USER to a non-root test account}"
[ "$(id -u "$GX_SMOKE_USER")" -ne 0 ]

repo="$(cd "$(dirname "$0")/.." && pwd)"
dist="${GX_SMOKE_DIST:-$repo/dist}"
packages=("$dist"/gx-shell_*_amd64.deb)
if [ "${#packages[@]}" -ne 1 ] || [ ! -f "${packages[0]}" ]; then
    echo "Expected exactly one gx-shell deb in $dist, found: ${packages[*]}" >&2
    exit 1
fi
package="${packages[0]}"
: "${GX_SMOKE_PYTHON:?Set GX_SMOKE_PYTHON to an absolute Python >= 3.9 executable; no system python3 fallback}"
case "$GX_SMOKE_PYTHON" in
    /*) ;;
    *) echo 'GX_SMOKE_PYTHON must be an absolute interpreter path, not a command with arguments.' >&2; exit 2 ;;
esac
if [ ! -f "$GX_SMOKE_PYTHON" ] || [ ! -x "$GX_SMOKE_PYTHON" ]; then
    echo "GX_SMOKE_PYTHON is not an executable regular file: $GX_SMOKE_PYTHON" >&2
    exit 2
fi
if ! runuser -u "$GX_SMOKE_USER" -- test -r "$GX_SMOKE_PYTHON" -a -x "$GX_SMOKE_PYTHON"; then
    echo "GX_SMOKE_PYTHON is not readable and executable by $GX_SMOKE_USER: $GX_SMOKE_PYTHON" >&2
    exit 2
fi
python_runtime="$("$GX_SMOKE_PYTHON" -I -B - "$repo" <<'PY'
import sys

minimum = (3, 9)
if sys.version_info[:2] < minimum:
    raise SystemExit(
        f"GX_SMOKE_PYTHON must be Python >= {minimum[0]}.{minimum[1]}; "
        f"got {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
import json
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]) / 'scripts'))
import gx_shell_package
import gx_shell_sources

print(json.dumps({'executable': sys.executable, 'version': sys.version.split()[0],
                  'minimum_version': '3.9', 'imports': ['gx_shell_package', 'gx_shell_sources']}))
PY
)"
if dpkg-query -W -f='${db:Status-Status}' gx-shell 2>/dev/null | grep -qx installed; then
    echo 'Refusing to replace an existing gx-shell installation in a lifecycle test.' >&2
    exit 2
fi
: "${GX_SMOKE_HERDR_PROBE:?Set GX_SMOKE_HERDR_PROBE to scripts/gx_probe_herdr.py in the locked external Oh My Zsh checkout}"
: "${GX_SMOKE_COMPONENTS_LOCK:?Set GX_SMOKE_COMPONENTS_LOCK to the lock used to assemble this package}"
herdr_probe="$(realpath -e -- "$GX_SMOKE_HERDR_PROBE")"
components_lock="$(realpath -e -- "$GX_SMOKE_COMPONENTS_LOCK")"
package_manifest="${GX_SMOKE_PACKAGE_MANIFEST:-$package.manifest.json}"
evidence="${GX_SMOKE_EVIDENCE:-$repo/.ui-evidence/gx-shell-linux}"
if [ -e "$evidence" ] || [ -L "$evidence" ]; then
    echo "Evidence output must be new: $evidence" >&2
    exit 1
fi
mkdir -p "$(dirname "$evidence")"
mkdir -- "$evidence"
evidence="$(realpath -e -- "$evidence")"
printf '%s\n' "$python_runtime" > "$evidence/python-runtime.json"
"$GX_SMOKE_PYTHON" -I -B - "$repo" "$package" "$package_manifest" "$components_lock" "$herdr_probe" "$evidence" <<'PY'
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
    package.require(info.get('platform') == 'linux', 'expected a Linux package manifest')
    package.verify_provenance(info, lock, checksum, info.get('source_commit'), allow_dirty=True)
    expected_name, _ = package.artifact_names(info['version'], 'linux', local=not info['publishable'])
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
        'schema': 1, 'platform': 'linux', 'status': 'PREFLIGHT_PASS',
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
PY
test_home="$(mktemp -d)"
chown "$GX_SMOKE_USER" "$test_home" "$evidence"
runuser -u "$GX_SMOKE_USER" -- test -r "$herdr_probe" ||
    { echo "Probe is not readable by $GX_SMOKE_USER: $herdr_probe" >&2; exit 1; }
cat /etc/os-release > "$evidence/os-release"
sha256sum "$package" > "$evidence/package.sha256"
witness_user=gx-smoke-witness

step() { printf '=== %s\n' "$*"; }
fail() {
    echo "$*" >&2
    exit 1
}
run_user() {
    runuser -u "$GX_SMOKE_USER" -- env HOME="$test_home" XDG_CONFIG_HOME="$test_home/.config" \
        XDG_DATA_HOME="$test_home/.local/share" XDG_STATE_HOME="$test_home/.local/state" LANG=C.UTF-8 "$@"
}
assert_entry_points() {
    local name target
    for name in gx-zsh herdr ghostty-gx; do
        [ "$(command -v "$name")" = "/usr/bin/$name" ]
        [ "$(dpkg-query -S "/usr/bin/$name")" = "gx-shell: /usr/bin/$name" ]
        case "$name" in
            gx-zsh|herdr) target="/usr/lib/ohmyzsh-gx/bin/$name" ;;
            *) target=/usr/lib/ghostty-gx/bin/ghostty ;;
        esac
        [ "$(readlink -f "/usr/bin/$name")" = "$target" ]
        [ "$(dpkg-query -S "$target")" = "gx-shell: $target" ]
        [ "$(stat -c '%u:%g' "/usr/bin/$name")" = 0:0 ]
        [ "$(stat -c '%u:%g' "$target")" = 0:0 ]
    done
}
assert_absent() {
    for path in "$@"; do
        if [ -e "$path" ] || [ -L "$path" ]; then
            fail "$path still exists"
        fi
    done
}
home_manifest() {
    getent passwd "$1"
    find "$2" -printf '%y %m %u:%g %s %T@ %p %l\n' | LC_ALL=C sort
    find "$2" -type f -exec sha256sum {} + | LC_ALL=C sort -k2
}
# The Ghostty GX configuration and the WezTerm configuration an earlier GX Shell left behind; GX Shell
# never reads, migrates or removes either.
assert_user_configs() {
    (cd "$test_home" && sha256sum --quiet -c "$evidence_root/user-configs.sha256") ||
        fail "$1 changed the Ghostty GX or WezTerm configuration"
}
readonly evidence_root="$evidence"
expose_evidence() {
    find "$evidence_root" \( -type s -o -type p \) -delete 2>/dev/null || true
    chmod -R a+rX "$evidence_root" 2>/dev/null || true
}
trap expose_evidence EXIT

step selected Python and locked probe work as the non-root account
run_user "$GX_SMOKE_PYTHON" -I -B - "$herdr_probe" "$evidence" <<'PY' > "$evidence/python-user-runtime.json"
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys

probe, evidence = map(Path, sys.argv[1:])
expected = json.loads((evidence / 'python-runtime.json').read_text(encoding='utf-8'))
if os.geteuid() == 0:
    raise SystemExit('probe preflight must run as the non-root smoke account')
if (sys.version.split()[0] != expected['version']
        or Path(sys.executable).resolve() != Path(expected['executable']).resolve()):
    raise SystemExit('root and non-root smoke Python runtimes differ')
receipt = json.loads((evidence / 'smoke-provenance.json').read_text(encoding='utf-8'))
if hashlib.sha256(probe.read_bytes()).hexdigest() != receipt['herdr_probe']['sha256']:
    raise SystemExit('herdr probe changed after provenance preflight')
runpy.run_path(str(probe), run_name='gx_smoke_probe_preflight')
print(json.dumps({'executable': sys.executable, 'version': sys.version.split()[0],
                  'uid': os.geteuid(), 'imports': ['gx_probe_herdr']}))
PY

id -u "$witness_user" > /dev/null 2>&1 || useradd --create-home "$witness_user"
[ "$(id -u "$witness_user")" -ne 0 ]
[ "$(id -u "$witness_user")" -ne "$(id -u "$GX_SMOKE_USER")" ] ||
    fail 'The witness and smoke accounts must have different UIDs'
witness_home="$(getent passwd "$witness_user" | cut -d: -f6)"
home_manifest "$witness_user" "$witness_home" > "$evidence/witness-home.before"

step user configuration of Ghostty GX and of an earlier WezTerm GX exists before the installation
run_user bash -c '
    set -euo pipefail
    mkdir -p "$XDG_CONFIG_HOME/ghostty" "$XDG_CONFIG_HOME/wezterm"
    printf "font-size = 13\n" > "$XDG_CONFIG_HOME/ghostty/config.ghostty"
    printf "%s\n" "-- WezTerm GX configuration left by an earlier GX Shell" > "$XDG_CONFIG_HOME/wezterm/wezterm.lua"
'
(cd "$test_home" && sha256sum .config/ghostty/config.ghostty .config/wezterm/wezterm.lua) > "$evidence/user-configs.sha256"

step install
HOME="$witness_home" apt-get install -y "$package" > "$evidence/install.log" 2>&1 ||
    { cat "$evidence/install.log" >&2; exit 1; }
dpkg-query -W -f='${Package} ${Version}\n' gx-shell | tee "$evidence/installed.txt"
assert_user_configs install

assert_runtime() {
    local evidence="$1" provenance="$2" opengl major minor
    step entry points
    assert_entry_points

    step GX Zsh with Oh My Zsh
    run_user gx-zsh -c 'print -r -- "zsh=$ZSH_VERSION omz=$ZSH"' > "$evidence/gx-zsh.txt" 2>&1
    cat "$evidence/gx-zsh.txt"
    grep -q 'zsh=5\.9\.2 omz=/usr/share/ohmyzsh-gx' "$evidence/gx-zsh.txt"

    step herdr and Ghostty GX package identity, herdr managed update and packaged completion
    run_user herdr --version | tee "$evidence/herdr-version.txt"
    run_user ghostty-gx +version > "$evidence/ghostty-version.txt" 2> "$evidence/ghostty-version.stderr" ||
        { cat "$evidence/ghostty-version.stderr" >&2; fail 'ghostty-gx +version failed'; }
    cat "$evidence/ghostty-version.txt"
    "$GX_SMOKE_PYTHON" -I -B - "$evidence" "$herdr_probe" "$provenance" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

evidence, probe, provenance = map(Path, sys.argv[1:])
receipt = json.loads(provenance.read_text(encoding='utf-8'))
if (evidence / 'herdr-version.txt').read_text(encoding='utf-8').strip() != receipt['expected_herdr_version']:
    raise SystemExit('herdr version differs from the locked herdr revision and package identity')
records = [record for record in receipt['stages']['ohmyzsh']['payload']
           if record['path'] == 'usr/lib/ohmyzsh-gx/lib/herdr/herdr']
if len(records) != 1 or hashlib.sha256(Path('/usr/lib/ohmyzsh-gx/lib/herdr/herdr').read_bytes()).hexdigest() != records[0]['sha256']:
    raise SystemExit('installed herdr hash differs from stage provenance')
ghostty = receipt['stages']['gx_ghostty']
lines = (evidence / 'ghostty-version.txt').read_text(encoding='utf-8').splitlines()
if lines[:1] != ['Ghostty ' + ghostty['product_version']] or '  - version: ' + ghostty['product_version'] not in lines:
    raise SystemExit('Ghostty GX version differs from the locked Ghostty GX stage')
if hashlib.sha256(Path('/usr/lib/ghostty-gx/bin/ghostty').read_bytes()).hexdigest() != ghostty['binaries']['ghostty']:
    raise SystemExit('installed Ghostty GX hash differs from stage provenance')
if hashlib.sha256(probe.read_bytes()).hexdigest() != receipt['herdr_probe']['sha256']:
    raise SystemExit('herdr probe changed after provenance preflight')
PY
    if run_user herdr update > "$evidence/herdr-update.txt" 2>&1; then
        fail 'herdr update was not blocked'
    fi
    grep -q 'managed by Oh My Zsh GX' "$evidence/herdr-update.txt"
    [ "$(head -n 1 /usr/share/ohmyzsh-gx/gx/omz-custom/plugins/herdr/_herdr)" = '#compdef herdr' ] ||
        fail 'the packaged herdr completion is missing'

    step herdr server with a real GX Zsh pane
    run_user "$GX_SMOKE_PYTHON" -I -B - "$herdr_probe" "$evidence/herdr-probe" <<'PY'
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile


def probe_socket_budget(output):
    # Locked probe: output/config, gx-probe- plus 16 hex digits; herdr session sockets.
    session = output / 'config/herdr/sessions' / ('gx-probe-' + 'f' * 16)
    paths = [str(session / name) for name in ('herdr.sock', 'herdr-client.sock')]
    records = [{'path_template': path, 'bytes_with_nul': len(path.encode('utf-8')) + 1}
               for path in paths]
    if any(record['bytes_with_nul'] > 108 for record in records):
        raise ValueError(f'probe socket path exceeds Linux sun_path capacity (108 bytes including NUL): {records}')
    return records


def run_short_probe(probe, archive):
    if archive.exists() or archive.is_symlink():
        raise ValueError(f'probe evidence must be new: {archive}')
    runtime = Path(tempfile.mkdtemp(prefix='gxh-', dir='/tmp')).resolve()
    output = runtime / 'p'
    metadata = {'runtime_output': str(output), 'evidence_output': str(archive),
                'sun_path_capacity_bytes': 108, 'probe_exit_code': None, 'excluded_runtime_entries': []}
    metadata_path = archive.with_name(archive.name + '.runtime.json')
    stderr_path = archive.with_name(archive.name + '.stderr.log')

    def ignore_runtime_entries(directory, names):
        ignored = []
        for name in names:
            path = Path(directory) / name
            mode = path.lstat().st_mode
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                ignored.append(name)
                metadata['excluded_runtime_entries'].append(str(path.relative_to(output)))
        return ignored

    try:
        metadata['socket_budget'] = probe_socket_budget(output)
        metadata_path.write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
        with archive.with_suffix('.json').open('wb') as stdout, stderr_path.open('wb') as stderr:
            result = subprocess.run([sys.executable, '-I', '-B', str(probe),
                                     '--herdr', '/usr/lib/ohmyzsh-gx/lib/herdr/herdr',
                                     '--zsh', '/usr/lib/ohmyzsh-gx/libexec/zsh/zsh',
                                     '--output', str(output)], stdout=stdout, stderr=stderr)
        metadata['probe_exit_code'] = result.returncode
    finally:
        # The probe waits for its own server before returning; archive even a failed probe.
        try:
            if output.is_symlink():
                raise OSError(f'probe output must not be a symlink: {output}')
            if output.exists():
                shutil.copytree(output, archive, ignore=ignore_runtime_entries)
            else:
                archive.mkdir()
            metadata_path.write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
        except Exception:
            print(f'Probe evidence copy failed; runtime retained at {runtime}', file=sys.stderr)
            raise
        shutil.rmtree(runtime)
    if result.returncode:
        print(stderr_path.read_text(encoding='utf-8', errors='replace'), file=sys.stderr, end='')
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(run_short_probe(*map(Path, sys.argv[1:])))
PY
    grep -q '"status": "PASS"' "$evidence/herdr-probe.json"

    step Ghostty GX finds the bundled fonts
    run_user ghostty-gx +list-fonts '--family=JetBrainsMono Nerd Font' > "$evidence/ghostty-fonts.txt" 2> "$evidence/ghostty-fonts.stderr" ||
        { cat "$evidence/ghostty-fonts.stderr" >&2; fail 'ghostty-gx +list-fonts failed'; }
    grep -Fxq 'JetBrainsMono Nerd Font' "$evidence/ghostty-fonts.txt" ||
        fail 'Ghostty GX does not find the bundled JetBrainsMono Nerd Font; see ghostty-fonts.txt'
    fc-list > "$evidence/fc-list.txt"
    grep -q '/usr/share/fonts/truetype/gx-shell/JetBrainsMonoNerdFont-Regular.ttf' "$evidence/fc-list.txt"
    grep -q '/usr/share/fonts/truetype/gx-shell/NotoSansCJK-Regular.ttc' "$evidence/fc-list.txt"

    step Ghostty GX runs GX Zsh under Xvfb with software OpenGL
    # The runner has no GPU: Mesa llvmpipe proves the software rendering path only. -e runs gx-zsh
    # directly, without a shell in between, so its Zsh is a child of the Ghostty GX process.
    run_user env GDK_BACKEND=x11 LIBGL_ALWAYS_SOFTWARE=1 NO_AT_BRIDGE=1 timeout 120 \
        xvfb-run -a --server-args='-screen 0 1280x800x24' bash -c '
        set -euo pipefail
        ghostty-gx -e gx-zsh > "$1/gui.log" 2>&1 &
        gui=$!
        trap "kill $gui 2>/dev/null || true; wait $gui 2>/dev/null || true" EXIT
        for _ in $(seq 1 120); do
            if pgrep -P "$gui" -u "$(id -u)" -f "^/usr/lib/ohmyzsh-gx/libexec/zsh/zsh" > "$1/gui-shell.pid"; then break; fi
            sleep 0.5
        done
        ps -o pid,ppid,args -u "$(id -u)" > "$1/gui-processes.txt"
        test -s "$1/gui-shell.pid"
        test "$(readlink "/proc/$gui/exe")" = /usr/lib/ghostty-gx/bin/ghostty
        sleep 5
        kill -0 "$gui"
        kill -0 "$(head -n 1 "$1/gui-shell.pid")"
        scrot "$1/linux.png"
    ' bash "$evidence"
    test -s "$evidence/linux.png"
    opengl="$(grep -aEo 'loaded OpenGL [0-9]+\.[0-9]+' "$evidence/gui.log" | tail -n 1 || true)"
    [ -n "$opengl" ] || fail 'the Ghostty GX log has no "loaded OpenGL" line; see gui.log'
    opengl="${opengl#loaded OpenGL }"
    major="${opengl%%.*}"
    minor="${opengl#*.}"
    [ "$major" -gt 4 ] || { [ "$major" -eq 4 ] && [ "$minor" -ge 3 ]; } ||
        fail "Ghostty GX loaded OpenGL $opengl; it needs 4.3"
    printf '%s\n' "$opengl" > "$evidence/opengl-version.txt"
    assert_user_configs 'Ghostty GX'
}
assert_runtime "$evidence" "$evidence/smoke-provenance.json"

user_data_manifest() {
    "$GX_SMOKE_PYTHON" -I -B - "$test_home" <<'PY'
import hashlib
import json
from pathlib import Path
import stat
import sys

home = Path(sys.argv[1])
records = []
for relative in ('.config/ghostty/config.ghostty', '.config/wezterm/wezterm.lua',
                 '.config/ohmyzsh-gx/profile/.zshrc', '.local/share/gx-smoke/preserve.txt',
                 '.local/state/gx-smoke/preserve.txt'):
    path = home / relative
    details = path.lstat()
    if not stat.S_ISREG(details.st_mode):
        raise SystemExit(f'protected user data is not a regular file: {relative}')
    records.append({'path': relative, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                    'mode': stat.S_IMODE(details.st_mode), 'uid': details.st_uid, 'gid': details.st_gid})
print(json.dumps(records, sort_keys=True, indent=2))
PY
}
assert_user_data() {
    user_data_manifest > "$evidence/user-data.$1.json"
    diff -u "$evidence/user-data.before.json" "$evidence/user-data.$1.json"
}

step reinstall keeps user data and runtime behavior
run_user bash -c '
    set -euo pipefail
    printf "\n# gx-shell-preserve-marker\n" >> "$XDG_CONFIG_HOME/ghostty/config.ghostty"
    printf "\n-- gx-shell-preserve-marker\n" >> "$XDG_CONFIG_HOME/wezterm/wezterm.lua"
    printf "\n# gx-shell-preserve-marker\n" >> "$XDG_CONFIG_HOME/ohmyzsh-gx/profile/.zshrc"
    mkdir -p "$XDG_DATA_HOME/gx-smoke" "$XDG_STATE_HOME/gx-smoke"
    printf "gx-shell-user-data\n" > "$XDG_DATA_HOME/gx-smoke/preserve.txt"
    printf "gx-shell-user-state\n" > "$XDG_STATE_HOME/gx-smoke/preserve.txt"
'
(cd "$test_home" && sha256sum .config/ghostty/config.ghostty .config/wezterm/wezterm.lua) > "$evidence/user-configs.sha256"
user_data_manifest > "$evidence/user-data.before.json"
HOME="$witness_home" apt-get install -y --reinstall "$package" > "$evidence/reinstall.log" 2>&1 ||
    { cat "$evidence/reinstall.log" >&2; exit 1; }
assert_user_data after-reinstall
dpkg-query -W -f='${Package} ${Version}\n' gx-shell > "$evidence/reinstalled.txt"
cmp "$evidence/installed.txt" "$evidence/reinstalled.txt"
run_user mkdir -- "$evidence/reinstall-runtime"
assert_runtime "$evidence/reinstall-runtime" "$evidence/smoke-provenance.json"
assert_user_data after-reinstall-runtime

step remove keeps user data
HOME="$witness_home" apt-get remove -y gx-shell > "$evidence/remove.log" 2>&1
assert_absent /usr/bin/gx-zsh /usr/bin/herdr /usr/bin/ghostty-gx /usr/lib/ohmyzsh-gx /usr/lib/ghostty-gx
assert_user_data after-remove
test -d "$test_home/.config/ohmyzsh-gx/profile"

step purge removes what the package owned and keeps user data
HOME="$witness_home" dpkg --purge gx-shell > "$evidence/purge.log" 2>&1 || { cat "$evidence/purge.log" >&2; exit 1; }
status="$(dpkg-query -W -f='${db:Status-Status}' gx-shell 2>/dev/null || true)"
[ -z "$status" ] || [ "$status" = not-installed ] || fail "gx-shell is still $status after purge"
assert_absent /usr/bin/gx-zsh /usr/bin/herdr /usr/bin/ghostty-gx \
    /usr/share/ohmyzsh-gx /usr/lib/ohmyzsh-gx /usr/lib/ghostty-gx /usr/share/doc/ghostty-gx \
    /usr/share/fonts/truetype/gx-shell /usr/share/applications/com.gx0404.ghostty-gx.desktop
find /usr/share/icons -name 'com.gx0404.ghostty-gx.*' > "$evidence/icons-purged.txt"
[ ! -s "$evidence/icons-purged.txt" ] || fail "Ghostty GX icons remain: $(cat "$evidence/icons-purged.txt")"
fc-list > "$evidence/fc-list-purged.txt"
if grep -q '/truetype/gx-shell/' "$evidence/fc-list-purged.txt"; then
    fail 'fc-list still lists the GX Shell fonts after purge'
fi
assert_user_data after-purge
test -d "$test_home/.config/ohmyzsh-gx/profile"

step "maintainer scripts left $witness_home untouched"
home_manifest "$witness_user" "$witness_home" > "$evidence/witness-home.after"
diff -u "$evidence/witness-home.before" "$evidence/witness-home.after"
"$GX_SMOKE_PYTHON" -I -B - "$evidence/smoke-provenance.json" <<'PY'
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
receipt = json.loads(path.read_text(encoding='utf-8'))
receipt['status'] = 'PASS'
receipt['python_runtime'] = json.loads((path.parent / 'python-runtime.json').read_text(encoding='utf-8'))
receipt['python_user_runtime'] = json.loads((path.parent / 'python-user-runtime.json').read_text(encoding='utf-8'))
receipt['legacy_release_upgrade'] = 'NOT_RUN'
receipt['coverage'] = {
    'install': 'PASS', 'same_version_reinstall': 'PASS', 'reinstall_runtime': 'PASS',
    'remove': 'PASS', 'purge': 'PASS', 'user_configuration': 'PASS', 'user_data_content_and_ownership': 'PASS',
    'witness_home_unchanged': 'PASS', 'ghostty_gx_runs_gx_zsh': 'PASS',
    'gui_renderer': 'Xvfb/Mesa llvmpipe (software OpenGL)', 'hardware_gpu': 'NOT_RUN',
    'desktop_input_echo_redraw': 'NOT_RUN', 'images_reviewed': False, 'previous_gx_shell': 'NOT_RUN',
}
path.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
print('Legacy release upgrade: ' + receipt['legacy_release_upgrade'])
PY
echo "PASS: gx-shell deb lifecycle on $(. /etc/os-release && echo "$PRETTY_NAME"); see smoke-provenance.json for upgrade coverage" | tee "$evidence/result.txt"

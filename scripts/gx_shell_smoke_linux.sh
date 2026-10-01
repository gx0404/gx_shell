#!/usr/bin/env bash
# GX Shell deb lifecycle smoke for a disposable Ubuntu container (run as root):
# optional legacy-package replacement (0.3.0 configuration migration), install, entry
# points, GX Zsh, herdr identity / managed update / completion / real Zsh pane, WezTerm seeding,
# fonts and configuration cases (tests/pure_fn_test.lua), GUI default shell, reinstall, removal
# and purge with user data preserved and another account's HOME untouched.
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
legacy_launch_sha=3b08d62514968129834d4e13086b31bc09ec30cc9f9c6204f530ab39d24966bd
payload=/usr/share/wezterm-gx/dotfiles/wezterm-config

step() { printf '=== %s\n' "$*"; }
fail() {
    echo "$*" >&2
    exit 1
}
run_user() {
    runuser -u "$GX_SMOKE_USER" -- env HOME="$test_home" XDG_CONFIG_HOME="$test_home/.config" \
        XDG_DATA_HOME="$test_home/.local/share" XDG_STATE_HOME="$test_home/.local/state" LANG=C.UTF-8 "$@"
}
run_legacy_user() {
    runuser -u "$GX_SMOKE_USER" -- env -u XDG_CONFIG_HOME -u XDG_DATA_HOME -u XDG_STATE_HOME \
        HOME="$legacy_home" LANG=C.UTF-8 "$@"
}
assert_config_log() {
    if grep -Eq 'plugin load failed|Error loading configuration|Failed to require' "$1"; then
        cat "$1" >&2
        exit 1
    fi
}
assert_entry_points() {
    local name target
    for name in gx-zsh herdr wezterm-gx wezterm-gx-gui; do
        [ "$(command -v "$name")" = "/usr/bin/$name" ]
        [ "$(dpkg-query -S "/usr/bin/$name")" = "gx-shell: /usr/bin/$name" ]
        case "$name" in
            gx-zsh|herdr) target="/usr/lib/ohmyzsh-gx/bin/$name" ;;
            *) target="/usr/lib/wezterm-gx/$name" ;;
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
config_manifest() {
    (cd "$1" && find . -type f -exec sha256sum {} + | LC_ALL=C sort -k2)
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

if [ -n "${GX_SMOKE_LEGACY_DEB:-}" ]; then
    step "legacy $(dpkg-deb --field "$GX_SMOKE_LEGACY_DEB" Package) is replaced by gx-shell"
    apt-get install -y "$GX_SMOKE_LEGACY_DEB" > "$evidence/legacy-install.log" 2>&1
    legacy="$(dpkg-deb --field "$GX_SMOKE_LEGACY_DEB" Package)"
    legacy_home="$(mktemp -d)"
    legacy_config="$legacy_home/.config/wezterm"
    chown "$GX_SMOKE_USER" "$legacy_home"
    run_legacy_user wezterm-gx --gx-initialize-only
    sha256sum "$legacy_config/config/launch.lua" | tee "$evidence/legacy-launch.sha256"
    [ "$(cut -d' ' -f1 "$evidence/legacy-launch.sha256")" = "$legacy_launch_sha" ] ||
        fail "$legacy did not seed the released 0.3.0 launch.lua"
    [ ! -e "$legacy_config/utils/gx-shell.lua" ] || fail "$legacy already seeded utils/gx-shell.lua"
    printf '{\n  "font_size": 12.0\n}\n' > "$evidence/gui-settings.json"
    install -o "$GX_SMOKE_USER" -m 0644 "$evidence/gui-settings.json" "$legacy_config/gui-settings.json"
    config_manifest "$legacy_config" > "$evidence/legacy-config.before"
fi

step install
HOME="$witness_home" apt-get install -y "$package" > "$evidence/install.log" 2>&1 ||
    { cat "$evidence/install.log" >&2; exit 1; }
dpkg-query -W -f='${Package} ${Version}\n' gx-shell | tee "$evidence/installed.txt"
if [ -n "${legacy:-}" ]; then
    if dpkg-query -W -f='${db:Status-Status}' "$legacy" 2>/dev/null | grep -qx installed; then
        echo "$legacy is still installed next to gx-shell" >&2
        exit 1
    fi
    # fontconfig 2.13 (Ubuntu 20.04) leaves a .uuid behind, so dpkg keeps the emptied directory
    # of the replaced package until it is purged; only its fonts must be gone.
    find /usr/share/fonts/truetype/wezterm-gx -mindepth 1 ! -name .uuid > "$evidence/legacy-fonts-left.txt" 2>/dev/null || true
    [ ! -s "$evidence/legacy-fonts-left.txt" ] || fail "fonts of $legacy remain: $(cat "$evidence/legacy-fonts-left.txt")"
fi

assert_runtime() {
    local evidence="$1" provenance="$2"
    step entry points
    assert_entry_points

    step GX Zsh with Oh My Zsh
    run_user gx-zsh -c 'print -r -- "zsh=$ZSH_VERSION omz=$ZSH"' > "$evidence/gx-zsh.txt" 2>&1
    cat "$evidence/gx-zsh.txt"
    grep -q 'zsh=5\.9\.2 omz=/usr/share/ohmyzsh-gx' "$evidence/gx-zsh.txt"

    step herdr package identity, managed update and packaged completion
    run_user herdr --version | tee "$evidence/herdr-version.txt"
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
    run_user "$GX_SMOKE_PYTHON" -I -B "$herdr_probe" --herdr /usr/lib/ohmyzsh-gx/lib/herdr/herdr \
        --zsh /usr/lib/ohmyzsh-gx/libexec/zsh/zsh --output "$evidence/herdr-probe" > "$evidence/herdr-probe.json"
    grep -q '"status": "PASS"' "$evidence/herdr-probe.json"

    step WezTerm seeds its configuration and finds the bundled fonts
    run_user wezterm-gx --version | tee "$evidence/wezterm-version.txt"
    run_user wezterm-gx --gx-initialize-only > "$evidence/wezterm-init.log" 2>&1
    assert_config_log "$evidence/wezterm-init.log"
    test -f "$test_home/.config/wezterm/wezterm.lua"
    test -f "$test_home/.config/wezterm/utils/gx-shell.lua"
    test "$(find "$test_home/.local/share/wezterm/plugins" -path '*/.git/HEAD' | wc -l)" -eq 4
    run_user wezterm-gx ls-fonts > "$evidence/fonts.log" 2>&1
    assert_config_log "$evidence/fonts.log"
    grep -q '/usr/share/fonts/truetype/gx-shell/JetBrainsMonoNerdFont-Regular.ttf' "$evidence/fonts.log"
    grep -q '/usr/share/fonts/truetype/gx-shell/NotoSansCJK-Regular.ttc' "$evidence/fonts.log"
    fc-list > "$evidence/fc-list.txt"
    grep -q '/truetype/gx-shell/' "$evidence/fc-list.txt"

    step WezTerm configuration cases pass on the packaged binary and configuration
    # A failing require falls back to default configuration; only the final ALL PASS counts.
    run_user timeout 120 wezterm-gx --config-file "$payload/tests/pure_fn_test.lua" show-keys > "$evidence/pure-fn-test.log" 2>&1 ||
        { cat "$evidence/pure-fn-test.log" >&2; fail 'wezterm-gx show-keys failed on tests/pure_fn_test.lua'; }
    grep -a 'PURE_FN_TEST' "$evidence/pure-fn-test.log" || true
    grep -aq 'PURE_FN_TEST: ALL PASS' "$evidence/pure-fn-test.log" ||
        fail 'tests/pure_fn_test.lua did not pass on the packaged WezTerm; see pure-fn-test.log'

    step WezTerm GUI starts GX Zsh by default with software rendering
    run_user timeout 90 xvfb-run -a bash -c '
        set -euo pipefail
        LIBGL_ALWAYS_SOFTWARE=1 wezterm-gx-gui --config front_end=\"OpenGL\" --config enable_wayland=false \
            start --always-new-process --no-auto-connect > "$1/gui.log" 2>&1 &
        gui=$!
        trap "kill $gui 2>/dev/null || true; wait $gui 2>/dev/null || true" EXIT
        for _ in $(seq 1 60); do
            if pgrep -P "$gui" -u "$(id -u)" -f "^/usr/lib/ohmyzsh-gx/libexec/zsh/zsh" > "$1/gui-shell.pid"; then break; fi
            sleep 0.5
        done
        ps -o pid,ppid,args -u "$(id -u)" > "$1/gui-processes.txt"
        test -s "$1/gui-shell.pid"
        test "$(readlink "/proc/$gui/exe")" = /usr/lib/wezterm-gx/wezterm-gui
        sleep 5
        kill -0 "$gui"
        xwd -root -silent > "$1/screen.xwd"
        ffmpeg -hide_banner -loglevel error -y -i "$1/screen.xwd" -frames:v 1 "$1/linux.png"
    ' bash "$evidence"
    assert_config_log "$evidence/gui.log"
}
assert_runtime "$evidence" "$evidence/smoke-provenance.json"

if [ -n "${legacy:-}" ]; then
    step "the untouched 0.3.0 configuration is migrated file by file"
    run_legacy_user wezterm-gx --gx-initialize-only
    managed="$legacy_home/.local/share/wezterm-gx"
    cp "$managed/config-migration.log" "$evidence/legacy-migration.log" 2>/dev/null || true
    # Released copies are replaced and missing files added, so every shipped file matches the payload.
    (cd "$payload" && find . -type f -exec sha256sum {} +) > "$evidence/payload.sha256"
    (cd "$legacy_config" && sha256sum --quiet -c "$evidence/payload.sha256") ||
        fail 'the 0.3.0 configuration was not upgraded to the packaged files; see legacy-migration.log'
    find "$legacy_config" -type l > "$evidence/legacy-links.txt"
    [ ! -s "$evidence/legacy-links.txt" ] || fail 'the migrated configuration contains symlinks'
    backups=("$managed"/backups/*/wezterm-config)
    [ "${#backups[@]}" -eq 1 ] && [ -d "${backups[0]}" ] ||
        fail "expected one configuration backup, found: ${backups[*]}"
    [ ! -e "${backups[0]}/gui-settings.json" ] && cmp -s "$evidence/gui-settings.json" "$legacy_config/gui-settings.json" ||
        fail 'the migration touched gui-settings.json'
    # Each 0.3.0 file is either untouched (files no longer shipped) or backed up before it was replaced.
    while read -r sum rel; do
        rel=${rel#\*}
        [ -f "$legacy_config/$rel" ] || fail "$rel disappeared during the migration"
        [ "$(sha256sum < "$legacy_config/$rel" | cut -d' ' -f1)" = "$sum" ] && continue
        [ "$(sha256sum < "${backups[0]}/$rel" | cut -d' ' -f1)" = "$sum" ] ||
            fail "$rel was replaced without a backup of the 0.3.0 copy"
    done < "$evidence/legacy-config.before"
    [ "$(sha256sum < "${backups[0]}/config/launch.lua" | cut -d' ' -f1)" = "$legacy_launch_sha" ] ||
        fail "${backups[0]}/config/launch.lua is not the 0.3.0 launch.lua"
    run_legacy_user wezterm-gx ls-fonts > "$evidence/legacy-fonts.log" 2>&1
    assert_config_log "$evidence/legacy-fonts.log"
    find "$legacy_config" "${backups[0]}" -type f -exec sha256sum {} + > "$evidence/legacy-data.sha256"
fi

user_data_manifest() {
    "$GX_SMOKE_PYTHON" -I -B - "$test_home" <<'PY'
import hashlib
import json
from pathlib import Path
import stat
import sys

home = Path(sys.argv[1])
records = []
for relative in ('.config/wezterm/wezterm.lua', '.config/wezterm/gui-settings.json',
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
    printf "\n-- gx-shell-preserve-marker\n" >> "$XDG_CONFIG_HOME/wezterm/wezterm.lua"
    printf "\n# gx-shell-preserve-marker\n" >> "$XDG_CONFIG_HOME/ohmyzsh-gx/profile/.zshrc"
    printf "{\"font_size\": 13.0}\n" > "$XDG_CONFIG_HOME/wezterm/gui-settings.json"
    mkdir -p "$XDG_DATA_HOME/gx-smoke" "$XDG_STATE_HOME/gx-smoke"
    printf "gx-shell-user-data\n" > "$XDG_DATA_HOME/gx-smoke/preserve.txt"
    printf "gx-shell-user-state\n" > "$XDG_STATE_HOME/gx-smoke/preserve.txt"
'
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
assert_absent /usr/bin/gx-zsh /usr/bin/herdr /usr/bin/wezterm-gx /usr/bin/wezterm-gx-gui \
    /usr/lib/ohmyzsh-gx /usr/lib/wezterm-gx
assert_user_data after-remove
test -d "$test_home/.config/ohmyzsh-gx/profile"

step purge removes what the package owned and keeps user data
HOME="$witness_home" dpkg --purge gx-shell > "$evidence/purge.log" 2>&1 || { cat "$evidence/purge.log" >&2; exit 1; }
status="$(dpkg-query -W -f='${db:Status-Status}' gx-shell 2>/dev/null || true)"
[ -z "$status" ] || [ "$status" = not-installed ] || fail "gx-shell is still $status after purge"
assert_absent /usr/bin/gx-zsh /usr/bin/herdr /usr/bin/wezterm-gx /usr/bin/wezterm-gx-gui \
    /usr/share/ohmyzsh-gx /usr/share/wezterm-gx /usr/lib/ohmyzsh-gx /usr/lib/wezterm-gx \
    /usr/share/fonts/truetype/gx-shell /usr/share/applications/org.gx0404.wezterm.desktop
fc-list > "$evidence/fc-list-purged.txt"
if grep -q '/truetype/gx-shell/' "$evidence/fc-list-purged.txt"; then
    fail 'fc-list still lists the GX Shell fonts after purge'
fi
assert_user_data after-purge
test -d "$test_home/.config/ohmyzsh-gx/profile"
if [ -n "${legacy:-}" ]; then
    sha256sum -c "$evidence/legacy-data.sha256"
fi

step "maintainer scripts left $witness_home untouched"
home_manifest "$witness_user" "$witness_home" > "$evidence/witness-home.after"
diff -u "$evidence/witness-home.before" "$evidence/witness-home.after"
"$GX_SMOKE_PYTHON" -I -B - "$evidence/smoke-provenance.json" "${GX_SMOKE_LEGACY_DEB:-}" <<'PY'
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
receipt = json.loads(path.read_text(encoding='utf-8'))
receipt['status'] = 'PASS'
receipt['python_runtime'] = json.loads((path.parent / 'python-runtime.json').read_text(encoding='utf-8'))
receipt['python_user_runtime'] = json.loads((path.parent / 'python-user-runtime.json').read_text(encoding='utf-8'))
receipt['legacy_release_upgrade'] = 'PASS_EXPLICIT_INPUT_ONLY' if sys.argv[2] else 'NOT_RUN'
receipt['coverage'] = {
    'install': 'PASS', 'same_version_reinstall': 'PASS', 'reinstall_runtime': 'PASS',
    'remove': 'PASS', 'purge': 'PASS', 'user_configuration': 'PASS', 'user_data_content_and_ownership': 'PASS',
    'witness_home_unchanged': 'PASS', 'gui_renderer': 'Xvfb/software OpenGL', 'hardware_gpu': 'NOT_RUN',
    'legacy_wezterm': receipt['legacy_release_upgrade'], 'previous_gx_shell': 'NOT_RUN',
}
path.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
print('Legacy release upgrade: ' + receipt['legacy_release_upgrade'])
PY
echo "PASS: gx-shell deb lifecycle on $(. /etc/os-release && echo "$PRETTY_NAME"); see smoke-provenance.json for upgrade coverage" | tee "$evidence/result.txt"

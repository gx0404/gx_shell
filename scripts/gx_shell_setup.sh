#!/usr/bin/env bash
# Project-local bootstrap; requires Bash, curl, tar and sha256sum, but no Python.
set -euo pipefail

# Digests from the corresponding GitHub release asset metadata.
PYTHON_VERSION='3.12.12'
PYTHON_BUILD='20251014'
PYTHON_URL='https://github.com/astral-sh/python-build-standalone/releases/download/20251014/cpython-3.12.12%2B20251014-x86_64-unknown-linux-gnu-install_only.tar.gz'
PYTHON_SHA256='1ab2b6594d1c3d76cbebea09d6bc3e6ba68d8eb3b6322080375c4cc3dd188f34'
ACTIONLINT_VERSION='1.7.12'
ACTIONLINT_URL='https://github.com/rhysd/actionlint/releases/download/v1.7.12/actionlint_1.7.12_linux_amd64.tar.gz'
ACTIONLINT_SHA256='8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8'

fail() { printf 'FAIL %s\n' "$*" >&2; exit 1; }
check=false
case "${1:-}" in
    --check|doctor) check=true ;;
    '') ;;
    *) fail 'Usage: bash scripts/gx_shell_setup.sh [--check|doctor]' ;;
esac
(( $# <= 1 )) || fail 'Too many arguments'
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || fail 'Only Linux x86_64 is supported'
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
local_root="$repo_root/.local"
tools_root="$repo_root/.local/tools"
cache_root="$repo_root/.local/cache/setup"
python_key="cpython-$PYTHON_VERSION-linux-x86_64-gnu"
python_dir="$tools_root/python/$python_key"
python_exe="$python_dir/bin/python3.12"
actionlint_dir="$tools_root/actionlint"
actionlint_exe="$actionlint_dir/actionlint"

assert_local() {
    local path=$1 part
    case "$path" in "$local_root"|"$local_root/"*) ;; *) fail "Path escapes .local: $path" ;; esac
    case "$path/" in */../*|*/./*) fail "Non-canonical setup path: $path" ;; esac
    part=$path
    while [[ $part == "$local_root" || $part == "$local_root/"* ]]; do
        [[ ! -L $part ]] || fail "Linked setup path is not allowed: $part"
        part=${part%/*}
    done
}

file_hash() { sha256sum -- "$1" | cut -d ' ' -f 1; }

ready() {
    local exe=$1 version=$2 digest=$3 marker
    marker="$(dirname -- "$exe")/.gx-shell-setup"
    assert_local "$exe"
    assert_local "$marker"
    [[ -f $exe && -f $marker ]] || return 1
    [[ $(cat -- "$marker") == "$version $digest $(file_hash "$exe")" ]]
}

receipt() {
    local exe=$1 version=$2 digest=$3
    assert_local "$exe"
    printf '%s %s %s\n' "$version" "$digest" "$(file_hash "$exe")" > "$(dirname -- "$exe")/.gx-shell-setup"
}

probe() {
    local name=$1 exe=$2 version=$3 digest=$4 output
    shift 4
    if ! ready "$exe" "$version" "$digest"; then printf 'MISSING %s %s\n' "$name" "$exe"; return 1; fi
    if ! output=$("$exe" "$@" 2>&1); then printf 'FAIL %s %s\n' "$name" "$output"; return 1; fi
    if [[ ${output%%$'\n'*} != "$version" ]]; then printf 'FAIL %s unexpected version: %s\n' "$name" "$output"; return 1; fi
    printf 'PASS %s %s %s\n' "$name" "$version" "$exe"
}

doctor() {
    local status=0
    probe python "$python_exe" "$PYTHON_VERSION" "$PYTHON_SHA256" -I -B -c 'import sys; print(sys.version.split()[0])' || status=1
    probe actionlint "$actionlint_exe" "$ACTIONLINT_VERSION" "$ACTIONLINT_SHA256" -version || status=1
    return "$status"
}

# Exit before mkdir, downloads, environment files or any installation.
if $check; then doctor; exit $?; fi
for command in curl tar sha256sum; do command -v "$command" >/dev/null || fail "Missing prerequisite: $command"; done
for path in "$tools_root" "$cache_root" "$repo_root/.local/cache/uv" "$local_root/build" "$tools_root/python" "$tools_root/bin"; do
    assert_local "$path"
    mkdir -p -- "$path"
done
run_root=$(mktemp -d "$local_root/build/sXXXXXXXX")
export TMPDIR="$run_root"
export UV_PYTHON_INSTALL_DIR="$tools_root/python"
export UV_CACHE_DIR="$repo_root/.local/cache/uv"
export UV_PYTHON_BIN_DIR="$tools_root/bin"
export UV_PYTHON_INSTALL_REGISTRY=false UV_PYTHON_DOWNLOADS=manual UV_OFFLINE=true UV_NO_CACHE=false
printf 'Setup evidence: %s\n' "$run_root"

download() {
    local url=$1 digest=$2 name=$3 target partial
    [[ $digest =~ ^[0-9a-f]{64}$ ]] || fail 'Invalid SHA-256 pin'
    target="$cache_root/$name"
    partial="$run_root/$name.partial"
    assert_local "$target"
    if [[ ! -e $target ]]; then
        printf 'Download: %s\n' "$url" >&2
        curl --fail --location --proto '=https' --proto-redir '=https' --retry 3 --output "$partial" "$url"
        [[ $(file_hash "$partial") == "$digest" ]] || fail "SHA-256 mismatch: $partial (retained for diagnosis)"
        mv -- "$partial" "$target"
    fi
    [[ $(file_hash "$target") == "$digest" ]] || fail "SHA-256 mismatch: $target; inspect the cache before retrying"
    printf '%s\n' "$target"
}

new_target() {
    assert_local "$1"
    [[ ! -e $1 ]] || fail "Incomplete or unrecognized installation: $1; inspect it before retrying (no automatic removal)"
}

file_uri() {
    # Escape URI delimiters and JSON-sensitive characters without needing Python.
    local value=$1
    value=${value//%/%25}; value=${value// /%20}; value=${value//#/%23}; value=${value//\?/%3F}
    value=${value//\"/%22}; value=${value//\\/%5C}; value=${value//$'\n'/%0A}; value=${value//$'\r'/%0D}; value=${value//$'\t'/%09}
    printf 'file://%s' "$value"
}

if ! ready "$python_exe" "$PYTHON_VERSION" "$PYTHON_SHA256"; then
    new_target "$python_dir"
    archive=$(download "$PYTHON_URL" "$PYTHON_SHA256" "python-$PYTHON_VERSION-$PYTHON_BUILD-linux.tar.gz")
    if command -v uv >/dev/null; then
        cat > "$run_root/python-downloads.json" <<EOF
{"$python_key":{"name":"cpython","arch":{"family":"x86_64","variant":null},"os":"linux","libc":"gnu","major":3,"minor":12,"patch":12,"prerelease":"","variant":null,"build":"$PYTHON_BUILD","url":"$(file_uri "$archive")","sha256":"$PYTHON_SHA256"}}
EOF
        uv --no-config --offline python install "$python_key" --no-bin --python-downloads-json-url "$(file_uri "$run_root/python-downloads.json")" 2>&1 | tee "$run_root/uv.log"
    else
        mkdir -- "$python_dir"
        tar -xzf "$archive" -C "$python_dir" --strip-components=1 --no-same-owner
    fi
    receipt "$python_exe" "$PYTHON_VERSION" "$PYTHON_SHA256"
fi
if ! ready "$actionlint_exe" "$ACTIONLINT_VERSION" "$ACTIONLINT_SHA256"; then
    new_target "$actionlint_dir"
    archive=$(download "$ACTIONLINT_URL" "$ACTIONLINT_SHA256" "actionlint-$ACTIONLINT_VERSION-linux.tar.gz")
    mkdir -- "$actionlint_dir"
    tar -xzf "$archive" -C "$actionlint_dir" --no-same-owner
    receipt "$actionlint_exe" "$ACTIONLINT_VERSION" "$ACTIONLINT_SHA256"
fi
doctor
assert_local "$tools_root/env.sh"
cat > "$tools_root/env.sh" <<'EOF'
# Source from Bash; changes apply only to the current process.
gx_tools_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
export UV_PYTHON_INSTALL_DIR="$gx_tools_root/python"
export UV_CACHE_DIR="$gx_tools_root/../cache/uv"
export UV_PYTHON_BIN_DIR="$gx_tools_root/bin"
export UV_PYTHON_INSTALL_REGISTRY=false
export GX_SHELL_PYTHON="$gx_tools_root/python/cpython-3.12.12-linux-x86_64-gnu/bin/python3.12"
export PATH="$(dirname -- "$GX_SHELL_PYTHON"):$gx_tools_root/actionlint:$PATH"
unset gx_tools_root
EOF
printf 'Ready. Source from Bash: %q\n' "$tools_root/env.sh"

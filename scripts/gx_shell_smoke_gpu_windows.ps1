# Non-installing Windows GPU gate. VerifyInputs never executes payload binaries.
# Run is deliberately blocked until the locked product has audited native path isolation.
# CheckEvidence validates captured material, not desktop interaction or visual acceptance.
param(
    [ValidateSet('VerifyInputs', 'Run', 'CheckEvidence')][string]$Action = 'VerifyInputs',
    [Parameter(Mandatory = $true)][string]$Installer,
    [Parameter(Mandatory = $true)][string]$PackageManifest,
    [Parameter(Mandatory = $true)][string]$ComponentsLock,
    [Parameter(Mandatory = $true)][string]$Assembly,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-fA-F]{40}$')][string]$ExpectedCoordinator,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$ExpectedLockDigest,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$ExpectedManifestSha256,
    [Parameter(Mandatory = $true)][string]$Evidence,
    [ValidateSet('OpenGL', 'WebGpu')][string]$Renderer = 'OpenGL',
    [string]$ObservationDirectory = '',
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$gpuHelper = @'
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import zlib

ISOLATION_BLOCKER = (
    'BLOCKED_UNSAFE_KNOWNFOLDERS: audited WezTerm config::HOME_DIR, DATA_DIR and CACHE_DIR '
    'use dirs-next Windows KnownFolders (Profile, RoamingAppData, LocalAppData); RUNTIME_DIR/logs '
    'fall back to that native HOME. Launcher USERPROFILE/APPDATA/XDG overrides do not redirect '
    'these native paths. No payload executable, GUI, installer or uninstaller may run here. '
    'A new locked revision requires a fresh source audit and an isolated native path probe; '
    'environment variables alone, --skip-config and --config-file are not an isolation boundary.'
)

def regular(package, path):
    package.safe_directory(path.absolute().parent)
    package.require(path.is_file() and not package.is_link(path), f'not a regular input: {path}')

def verify_inputs(package, installer, metadata, lock_path, assembly, coordinator, lock_digest, manifest_hash):
    for path in (installer, metadata, lock_path):
        regular(package, path)
    package.require(package.digest(metadata) == manifest_hash.lower(), 'trusted package manifest SHA-256 mismatch')
    lock, checksum, raw_lock = package.read_components_lock(lock_path)
    package.require(checksum == lock_digest.lower(), 'trusted components lock digest mismatch')
    manifest = package.read_json(metadata)
    package.require(manifest.get('platform') == 'windows', 'expected Windows package')
    package.verify_provenance(manifest, lock, checksum, coordinator, allow_dirty=False)
    info = package.check_assembly(assembly)
    package.require(info.get('platform') == 'windows', 'expected Windows assembly')
    package.verify_provenance(info, lock, checksum, coordinator, allow_dirty=False)
    package.require((assembly / 'components.lock.json').read_bytes() == raw_lock, 'assembly lock bytes differ')
    expected = {key: value for key, value in info.items() if key != 'payload'}
    expected.update(payload_files=len(info['payload']), artifacts=manifest.get('artifacts'))
    package.require(manifest == expected, 'package and complete assembly identity differ')
    name, source_name = package.artifact_names(info['version'], 'windows')
    package.require(installer.name == name and metadata.name == name + '.manifest.json', 'unexpected package filenames')
    artifacts = manifest.get('artifacts')
    package.require(isinstance(artifacts, dict) and set(artifacts) == {name, source_name}, 'incomplete artifact receipt')
    for filename, record in artifacts.items():
        path = installer if filename == name else installer.parent / filename
        regular(package, path)
        package.require(isinstance(record, dict) and set(record) == {'sha256', 'size'}, 'invalid artifact receipt')
        package.require(type(record['size']) is int and record['size'] > 0 and
                        record['size'] == path.stat().st_size and record['sha256'] == package.digest(path),
                        f'artifact hash or size mismatch: {filename}')
    sidecar = installer.parent / (name + '.sha256')
    regular(package, sidecar)
    sums = [f"{record['sha256']}  {filename}" for filename, record in artifacts.items()]
    sums.append(f'{package.digest(metadata)}  {metadata.name}')
    package.require(sorted(sidecar.read_text(encoding='ascii').splitlines()) == sorted(sums), 'stale package sidecar')
    return {
        'schema': 1, 'status': 'INPUTS_VERIFIED', 'runtime_status': 'BLOCKED_UNSAFE_KNOWNFOLDERS',
        'package_sha256': package.digest(installer), 'package_manifest_sha256': package.digest(metadata),
        'assembly_manifest_sha256': package.digest(assembly / 'assembly-manifest.json'),
        'coordinator': info['coordinator'], 'components_lock_digest': checksum, 'components': info['components'],
        'payload_files': len(info['payload']), 'assembly_files': len(info['inventory']),
        'gpu_acceptance': 'NOT_RUN', 'images_reviewed': False,
        'ci_identity': 'caller-supplied trusted manifest digest; no CI identity inferred from local environment',
    }

def renderer_evidence(text, renderer):
    banned = r'(?i)\b(cpu|warp|llvmpipe|softpipe|swiftshader|software|fallback)\b|basic render|gdi generic|microsoft remote'
    if renderer == 'OpenGL':
        lines = [line for line in text.splitlines() if 'OpenGL initialized! OpenGL:' in line]
        if not lines or any(re.search(banned, line) for line in lines):
            raise ValueError('missing or software OpenGL renderer evidence')
        if any(not re.search(r'(?i)intel|nvidia|amd|radeon|geforce|iris', line) for line in lines):
            raise ValueError('unrecognized hardware OpenGL renderer; review the adapter explicitly')
        if 'OpenGL initialized! WebGPU:' in text:
            raise ValueError('mixed renderer cases in OpenGL evidence')
    else:
        lines = [line for line in text.splitlines() if 'Using adapter: AdapterInfo {' in line]
        if not lines or any(re.search(banned, line) for line in lines):
            raise ValueError('missing or software WebGPU selected-adapter evidence')
        if any(not re.search(r'device_type: (IntegratedGpu|DiscreteGpu)\b', line) or
               not re.search(r'backend: (Dx12|Vulkan|Gl)\b', line) for line in lines):
            raise ValueError('selected WebGPU adapter is not a hardware device')
        initialized = [line for line in text.splitlines() if 'OpenGL initialized! WebGPU:' in line]
        if not initialized:
            raise ValueError('selected adapter alone does not prove initialized WebGPU rendering')
        if any(re.search(banned, line) for line in initialized):
            raise ValueError('software WebGPU initialized renderer')
        if any('OpenGL initialized! OpenGL:' in line for line in text.splitlines()):
            raise ValueError('mixed renderer cases in WebGPU evidence')
        lines += initialized
    if re.search(r'(?i)failed to create RenderState|panicked at|Error loading configuration|plugin load failed', text):
        raise ValueError('renderer/configuration failure in runtime log')
    return lines

def png_dimensions(path):
    data = path.read_bytes()
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('screenshot is not PNG')
    offset, dimensions, pixels, ended = 8, None, bytearray(), False
    while offset + 12 <= len(data):
        size = struct.unpack('>I', data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        body = data[offset + 8:offset + 8 + size]
        end = offset + 12 + size
        if end > len(data) or zlib.crc32(kind + body) != struct.unpack('>I', data[end - 4:end])[0]:
            raise ValueError('truncated or corrupt PNG screenshot')
        if dimensions is None:
            if kind != b'IHDR' or size != 13:
                raise ValueError('invalid PNG header')
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', body)
            if not (320 <= width <= 16384 and 200 <= height <= 16384 and depth == 8 and color in (2, 6)
                    and compression == filtering == interlace == 0):
                raise ValueError('expected non-interlaced RGB/RGBA desktop PNG')
            dimensions = (width, height)
        elif kind == b'IDAT':
            pixels.extend(body)
        elif kind == b'IEND':
            ended = size == 0 and end == len(data)
            break
        offset = end
    if dimensions is None or not ended or not pixels:
        raise ValueError('incomplete PNG screenshot')
    expected = (width * (3 if color == 2 else 4) + 1) * height
    decoder = zlib.decompressobj()
    raw = decoder.decompress(bytes(pixels), expected + 1)
    if len(raw) != expected or not decoder.eof or decoder.unused_data:
        raise ValueError('invalid PNG pixel data')
    return list(dimensions)

def check_evidence(package, folder, receipt, renderer):
    package.safe_directory(folder)
    observation = package.read_json(folder / 'observation.json')
    for key in ('package_sha256', 'package_manifest_sha256', 'assembly_manifest_sha256', 'components_lock_digest'):
        package.require(observation.get(key) == receipt[key], f'evidence package identity mismatch: {key}')
    package.require(observation.get('renderer') == renderer, 'renderer case mismatch')
    if renderer == 'OpenGL':
        package.require(observation.get('default_front_end') is True, 'OpenGL must exercise the packaged default')
    else:
        package.require(observation.get('webgpu_force_fallback_adapter') is False, 'WebGPU must explicitly disable fallback')
    token = observation.get('token')
    package.require(isinstance(token, str) and re.fullmatch('[0-9a-f]{32}', token), 'missing unique input token')
    files = observation.get('files')
    package.require(isinstance(files, dict) and set(files) ==
                    {'renderer.log', 'input.txt', 'echo.txt', 'before.png', 'after.png'}, 'incomplete evidence file set')
    for name, checksum in files.items():
        path = folder / name
        regular(package, path)
        package.require(package.digest(path) == checksum, f'evidence file hash mismatch: {name}')
    selected = renderer_evidence((folder / 'renderer.log').read_text(encoding='utf-8-sig'), renderer)
    package.require((folder / 'input.txt').read_text(encoding='utf-8-sig').strip() == 'GX_GPU_INPUT_' + token,
                    'missing desktop input marker')
    output = (folder / 'echo.txt').read_text(encoding='utf-8-sig').splitlines()
    package.require('GX_GPU_ECHO_' + token in output and 'GX_GPU_REDRAW_' + token in output,
                    'missing exact echo/redraw output markers')
    dimensions = {name: png_dimensions(folder / name) for name in ('before.png', 'after.png')}
    package.require(files['before.png'] != files['after.png'], 'identical before/after screenshots')
    return {'status': 'EVIDENCE_READY', 'renderer': renderer, 'renderer_lines': selected, 'screenshots': dimensions,
            'images_reviewed': False, 'desktop_interaction_verified': False, 'gpu_acceptance': 'PENDING',
            'warning': 'Hashes and markers only. Desktop input, visible echo, repaint and isolation require independent review.'}

def main(argv):
    (repo, action, installer, metadata, lock_path, assembly, coordinator, lock_digest, manifest_hash,
     evidence, renderer, observation) = argv
    sys.path.insert(0, str(Path(repo) / 'scripts'))
    import gx_shell_package as package
    package.require(action in ('VerifyInputs', 'Run', 'CheckEvidence'), 'invalid action')
    package.require(renderer in ('OpenGL', 'WebGpu'), 'invalid renderer')
    installer, metadata, lock_path, assembly, evidence = map(Path, (installer, metadata, lock_path, assembly, evidence))
    package.require(evidence.is_absolute() and not evidence.exists() and not evidence.is_symlink(),
                    'evidence must be a new absolute directory')
    package.safe_directory(evidence.parent)
    evidence = evidence.resolve()
    for source in (assembly, installer.parent, metadata.parent, lock_path.parent):
        package.require(not evidence.is_relative_to(source.resolve()), 'evidence must be outside the input trees')
    receipt = verify_inputs(package, installer, metadata, lock_path, assembly, coordinator, lock_digest, manifest_hash)
    receipt.update(requested_renderer=renderer, isolation_blocker=ISOLATION_BLOCKER, isolation_audit={
        'audited_wezterm_revision': '4b219eea6a46eab9de03444612b90766d1d0d806',
        'native_paths': 'config/src/lib.rs HOME_DIR; config/src/config.rs compute_data_dir/compute_cache_dir/compute_runtime_dir',
        'plugins': 'lua-api-crates/plugin/src/lib.rs RepoSpec::plugins_dir uses config::DATA_DIR',
        'logs': 'env-bootstrap/src/ringlog.rs uses config::RUNTIME_DIR',
        'library': 'dirs-next 2.0.0 src/win.rs -> dirs-sys-next 0.1.2 SHGetKnownFolderPath',
        'launcher_only': 'scripts/gx-launcher/os/windows.rs uses USERPROFILE/APPDATA/XDG_CONFIG_HOME',
        'other_revisions': 'UNREVIEWED: this gate stays closed until a new native isolation contract is audited',
    })
    if action == 'CheckEvidence':
        package.require(bool(observation), 'CheckEvidence requires -ObservationDirectory')
        receipt['evidence_check'] = check_evidence(package, Path(observation), receipt, renderer)
        receipt['status'] = 'EVIDENCE_READY'
    elif action == 'Run':
        receipt['status'] = 'BLOCKED_UNSAFE_KNOWNFOLDERS'
    evidence.mkdir()
    package.write_json(evidence / 'gpu-smoke.json', receipt)
    package.write_json(evidence / 'evidence-contract.json', {
        'schema': 1, 'required_cases': ['OpenGL packaged default', 'WebGpu hardware separate case'],
        'isolation_required': ['HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'KnownFolders Profile/Roaming/Local',
                               'GX Zsh profile', 'herdr configuration', 'XDG config/cache/data/state/runtime',
                               'TEMP/TMP/TMPDIR', 'WezTerm logs/pki/socket/cache/config/plugins/backups'],
        'forbidden': ['installer execution', 'registry or PATH writes', 'font registration', 'killing existing processes',
                      'environment-only isolation claims', 'CPU/WARP/llvmpipe/fallback renderer', 'handle-only PASS'],
        'observation_json': {**{key: receipt[key] for key in ('package_sha256', 'package_manifest_sha256',
                             'assembly_manifest_sha256', 'components_lock_digest')},
                             'renderer': renderer, 'token': '<32 lowercase hex generated per run>',
                             'default_front_end': renderer == 'OpenGL', 'webgpu_force_fallback_adapter': False,
                             'files': {name: '<sha256>' for name in
                                       ('renderer.log', 'input.txt', 'echo.txt', 'before.png', 'after.png')}},
        'log_filter': 'WEZTERM_LOG=info,wezterm_gui::termwindow=trace',
        'review_required': 'Use approved desktop tooling to type the unique marker, observe echo, resize/repaint and read both PNGs. '
                           'Keep action receipts, process identity, native path probes and before/after host baselines. '
                           'Screenshot failure fails the case. EVIDENCE_READY is never GPU acceptance.',
    })
    print(receipt['status'] + ': ' + ISOLATION_BLOCKER)
    return 3 if action == 'Run' else 0

if __name__ == '__main__':
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (OSError, ValueError, KeyError, TypeError, zlib.error) as error:
        print(f'gpu-smoke rejected: {error}', file=sys.stderr)
        raise SystemExit(1)
'@
& $Python -I -B -c $gpuHelper $repo $Action $Installer $PackageManifest $ComponentsLock $Assembly `
    $ExpectedCoordinator $ExpectedLockDigest $ExpectedManifestSha256 $Evidence $Renderer $ObservationDirectory
if ($LASTEXITCODE -ne 0) { throw "GPU smoke refused or failed (exit $LASTEXITCODE); no runtime acceptance is claimed." }

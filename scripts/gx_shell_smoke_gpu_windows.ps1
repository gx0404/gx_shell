# Non-installing Windows GPU gate for Ghostty GX. VerifyInputs never executes payload binaries.
# Run is deliberately blocked until the locked Ghostty GX revision has an audited native path isolation
# contract. CheckEvidence validates captured material, not desktop interaction or visual acceptance.
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
    [ValidateSet('OpenGL')][string]$Renderer = 'OpenGL',
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

AUDITED_GHOSTTY_REVISION = 'f9e67e5f18f1ab7506f50e216f09d423c94be4b3'
ISOLATION_BLOCKER = (
    'BLOCKED_PENDING_ISOLATION_AUDIT: at the audited revision Ghostty GX resolves its configuration, cache '
    'and state from XDG_CONFIG_HOME/XDG_CACHE_HOME/XDG_STATE_HOME or LOCALAPPDATA, writes its log to '
    'LOCALAPPDATA\\ghostty\\logs and takes its home from HOMEDRIVE/HOMEPATH; GX Zsh and herdr keep their '
    'profile under LOCALAPPDATA. No KnownFolders lookup was found there, but environment variables are not '
    'an isolation boundary until the locked revision is audited again and an isolated native path probe '
    'passes. No payload executable, GUI, installer or uninstaller may run here.'
)
# Ghostty GX logs the implementation behind its WGL context once the render thread starts.
OPENGL_LINE = re.compile(r'loaded OpenGL ([0-9]+)\.([0-9]+) vendor=(.*?) renderer=(.*?) software=(true|false)\s*$')

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
        'schema': 1, 'status': 'INPUTS_VERIFIED', 'runtime_status': 'BLOCKED_PENDING_ISOLATION_AUDIT',
        'package_sha256': package.digest(installer), 'package_manifest_sha256': package.digest(metadata),
        'assembly_manifest_sha256': package.digest(assembly / 'assembly-manifest.json'),
        'coordinator': info['coordinator'], 'components_lock_digest': checksum, 'components': info['components'],
        'payload_files': len(info['payload']), 'assembly_files': len(info['inventory']),
        'gpu_acceptance': 'NOT_RUN', 'images_reviewed': False,
        'ci_identity': 'caller-supplied trusted manifest digest; no CI identity inferred from local environment',
    }

def renderer_evidence(text, renderer):
    if renderer != 'OpenGL':
        raise ValueError('Ghostty GX renders with OpenGL only')
    banned = r'(?i)\b(cpu|warp|llvmpipe|softpipe|swiftshader|software|fallback)\b|basic render|gdi generic|microsoft remote'
    lines = [line for line in text.splitlines() if OPENGL_LINE.search(line)]
    if not lines:
        raise ValueError('missing Ghostty GX OpenGL implementation evidence')
    for line in lines:
        major, minor, vendor, name, software = OPENGL_LINE.search(line).groups()
        if software != 'false' or re.search(banned, vendor + ' ' + name):
            raise ValueError('software OpenGL renderer evidence (bundled Mesa or a software driver)')
        if (int(major), int(minor)) < (4, 3):
            raise ValueError('the system OpenGL driver is below 4.3')
        if not re.search(r'(?i)intel|nvidia|amd|radeon|geforce|iris|ati technologies', vendor + ' ' + name):
            raise ValueError('unrecognized hardware OpenGL renderer; review the adapter explicitly')
    if re.search(r'(?i)OpenGL version is too old|OpenGLOutdated|software OpenGL \(.*\) is unavailable|panic', text):
        raise ValueError('renderer failure in runtime log')
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
    package.require(observation.get('ghostty_gx_opengl_override') is False,
                    'Ghostty GX must run its packaged default: GHOSTTY_GX_OPENGL unset, system OpenGL driver first')
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
    package.require(renderer == 'OpenGL', 'invalid renderer')
    installer, metadata, lock_path, assembly, evidence = map(Path, (installer, metadata, lock_path, assembly, evidence))
    package.require(evidence.is_absolute() and not evidence.exists() and not evidence.is_symlink(),
                    'evidence must be a new absolute directory')
    package.safe_directory(evidence.parent)
    evidence = evidence.resolve()
    for source in (assembly, installer.parent, metadata.parent, lock_path.parent):
        package.require(not evidence.is_relative_to(source.resolve()), 'evidence must be outside the input trees')
    receipt = verify_inputs(package, installer, metadata, lock_path, assembly, coordinator, lock_digest, manifest_hash)
    receipt.update(requested_renderer=renderer, isolation_blocker=ISOLATION_BLOCKER, isolation_audit={
        'audited_ghostty_revision': AUDITED_GHOSTTY_REVISION,
        'locked_ghostty_revision': receipt['components'][package.GHOSTTY]['revision'],
        'config_cache_state': 'src/os/xdg.zig: XDG_CONFIG_HOME, XDG_CACHE_HOME, XDG_STATE_HOME, else LOCALAPPDATA',
        'logs': 'src/apprt/win32/file_log.zig: LOCALAPPDATA\\ghostty\\logs\\ghostty.log',
        'home': 'src/os/homedir.zig: HOMEDRIVE + HOMEPATH',
        'fonts': 'src/font/discovery.zig: SystemRoot\\Fonts and LOCALAPPDATA\\Microsoft\\Windows\\Fonts',
        'profiles': 'src/gx/profiles.zig: GX Zsh from LOCALAPPDATA\\Programs\\GXShell\\bin, the executable directory or PATH',
        'known_folders': 'none in src at the audited revision',
        'other_revisions': 'UNREVIEWED: this gate stays closed until the locked revision is audited and an isolated native path probe passes',
    })
    if action == 'CheckEvidence':
        package.require(bool(observation), 'CheckEvidence requires -ObservationDirectory')
        receipt['evidence_check'] = check_evidence(package, Path(observation), receipt, renderer)
        receipt['status'] = 'EVIDENCE_READY'
    elif action == 'Run':
        receipt['status'] = 'BLOCKED_PENDING_ISOLATION_AUDIT'
    evidence.mkdir()
    package.write_json(evidence / 'gpu-smoke.json', receipt)
    package.write_json(evidence / 'evidence-contract.json', {
        'schema': 1, 'required_cases': ['OpenGL on the system driver: the packaged default, software=false'],
        'isolation_required': ['HOME', 'HOMEDRIVE/HOMEPATH', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA',
                               'XDG_CONFIG_HOME/XDG_CACHE_HOME/XDG_STATE_HOME', 'TEMP/TMP/TMPDIR',
                               'Ghostty GX configuration, cache, state and logs', 'GX Zsh profile',
                               'herdr configuration', 'user font registrations'],
        'forbidden': ['installer execution', 'registry or PATH writes', 'font registration', 'killing existing processes',
                      'environment-only isolation claims', 'GHOSTTY_GX_OPENGL=software',
                      'bundled Mesa/llvmpipe/WARP/GDI Generic renderer', 'handle-only PASS'],
        'observation_json': {**{key: receipt[key] for key in ('package_sha256', 'package_manifest_sha256',
                             'assembly_manifest_sha256', 'components_lock_digest')},
                             'renderer': renderer, 'token': '<32 lowercase hex generated per run>',
                             'ghostty_gx_opengl_override': False,
                             'files': {name: '<sha256>' for name in
                                       ('renderer.log', 'input.txt', 'echo.txt', 'before.png', 'after.png')}},
        'renderer_log': 'the isolated LOCALAPPDATA\\ghostty\\logs\\ghostty.log of the run, with the line '
                        '"loaded OpenGL X.Y vendor=... renderer=... software=false"',
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

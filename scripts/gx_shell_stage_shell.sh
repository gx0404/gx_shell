#!/usr/bin/env bash
set -euo pipefail
coordinator="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
if command -v python >/dev/null 2>&1; then
    python=python
elif command -v python3 >/dev/null 2>&1; then
    python=python3
else
    printf '%s\n' 'gx-shell-stage: Python 3.10+ is required (run this script with Git Bash on Windows).' >&2
    exit 1
fi
exec "$python" -B - "$coordinator" "$@" <<'PY'
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def write_json(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=True)
        stream.write('\n')


HERDR_REPOSITORY = 'https://github.com/gx0404/herdr'


def require_herdr_source(pinned, revision):
    require(pinned['revision'].lower() == revision.lower(),
            'Oh My Zsh dependency lock herdr revision differs from components lock; update the producer, not the adapter')
    source = pinned['source']
    require(isinstance(source, dict) and source.get('commit') == pinned['revision']
            and ((source.get('git_repository') == HERDR_REPOSITORY and 'url' not in source)
                 or ('git_repository' not in source
                     and source.get('url') == f"{HERDR_REPOSITORY}/archive/{pinned['revision']}.zip")),
            'producer must pin the independent gx0404/herdr archive of the locked commit (Git checkout or commit '
            'archive URL), not a coordinator source subtree, another repository or a floating ref')


def main():
    require(sys.version_info >= (3, 10), 'Python 3.10+ is required')
    coordinator = Path(sys.argv[1])
    parser = argparse.ArgumentParser(
        prog='gx_shell_stage_shell.sh',
        description='Stage pinned Oh My Zsh/herdr checkouts; never infer component paths from the coordinator.',
        epilog='Local: GX_LOCAL_BUILD_ROOT must name the coordinator .local/build/<run> directory, work-root '
               'must be a new child of it, and the Oh My Zsh/herdr roots must live under the coordinator '
               '.local/sources. CI release builds instead use independent checkouts under RUNNER_TEMP; that Git '
               'identity boundary never relaxes the local path rule. '
               'The original platform/work-root positional arguments are retained; all source options are mandatory. '
               'Local stages are never publishable; root assemble must use --allow-dirty.')
    parser.add_argument('platform', choices=('windows-x64', 'ubuntu-amd64'))
    parser.add_argument('work_root', type=Path)
    parser.add_argument('--ohmyzsh-root', required=True, type=Path)
    parser.add_argument('--herdr-root', required=True, type=Path)
    parser.add_argument('--components-lock', required=True, type=Path)
    parser.add_argument('--component-revision', required=True)
    parser.add_argument('--jobs', default=os.environ.get('GX_CPU_JOBS', os.environ.get('GX_ZSH_JOBS', '2')))
    parser.add_argument('--allow-dirty', action='store_true',
                        help='explicitly permit local coordinator/Oh My Zsh edits; herdr must stay clean')
    args = parser.parse_args(sys.argv[2:])
    require(re.fullmatch(r'[1-9][0-9]*', str(args.jobs)) is not None, '--jobs must be a positive integer')
    require(re.fullmatch(r'[0-9a-fA-F]{40}', args.component_revision) is not None,
            '--component-revision must be the full locked Oh My Zsh SHA, not a branch or tag')
    require(not os.environ.get('GH_TOKEN') and not os.environ.get('GITHUB_TOKEN'),
            'remove GH_TOKEN/GITHUB_TOKEN before running dependency builders')
    for key in ('GIT_DIR', 'GIT_COMMON_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_OBJECT_DIRECTORY',
                'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_NAMESPACE', 'GIT_REPLACE_REF_BASE'):
        require(not os.environ.get(key), f'unset {key}; source overrides are not accepted')

    spec = importlib.util.spec_from_file_location('gx_shell_sources', coordinator / 'scripts/gx_shell_sources.py')
    sources = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sources)
    coordinator = sources._safe_path(coordinator)
    omz = sources._safe_path(args.ohmyzsh_root)
    herdr = sources._safe_path(args.herdr_root)
    work = sources._safe_path(args.work_root)
    lock_path = sources._safe_path(args.components_lock)
    local = bool(os.environ.get('GX_LOCAL_BUILD_ROOT'))
    private = coordinator / '.local'

    def nested(inner, outer):
        return inner.is_relative_to(outer) and not (local and outer == coordinator and inner.is_relative_to(private))

    roots = (coordinator, omz, herdr)
    for index, root in enumerate(roots):
        for other in roots[index + 1:]:
            require(not nested(root, other) and not nested(other, root),
                    'coordinator, Oh My Zsh and herdr must be separate, non-nested Git checkouts '
                    '(local runs may nest them only under the coordinator .local)')
        require(not nested(work, root) and not root.is_relative_to(work),
                'work-root must be outside every source checkout and cannot contain one')
    require(not work.exists(), 'work-root already exists; choose a fresh path, never reuse build/cache/stage outputs')
    require(not lock_path.is_relative_to(work), 'components lock must not be inside the new work-root')
    require(lock_path.is_file(), '--components-lock must name an existing complete lock; no production lock is generated')
    lock_raw = lock_path.read_bytes()
    checked = sources.check(lock_path)
    entries = checked['components']
    require(args.component_revision.lower() == entries['ohmyzsh']['revision'].lower(),
            '--component-revision differs from the components lock Oh My Zsh revision')

    if local:
        require(os.environ.get('GITHUB_ACTIONS') != 'true', 'GX_LOCAL_BUILD_ROOT cannot be used on GitHub Actions')
        boundary = sources._safe_path(Path(os.environ['GX_LOCAL_BUILD_ROOT']))
        build_root = sources._safe_path(coordinator / '.local' / 'build')
        sources_root = sources._safe_path(coordinator / '.local' / 'sources')
        require(boundary != build_root and boundary.is_relative_to(build_root),
                'GX_LOCAL_BUILD_ROOT must be the coordinator .local/build/<run> directory')
        require(work.parent == boundary,
                'local work-root must be a new child of GX_LOCAL_BUILD_ROOT (.local/build/<run>)')
        require(all(root != sources_root and root.is_relative_to(sources_root) for root in (omz, herdr)),
                'local Oh My Zsh/herdr checkouts must be independent directories under the coordinator .local/sources')
        for candidate, label in ((boundary, 'GX_LOCAL_BUILD_ROOT'), (work, 'work-root')):
            relative = candidate.relative_to(coordinator)
            require(len(str(relative)) <= 80
                    and all(re.fullmatch(r'[A-Za-z0-9_.-]+', part) for part in relative.parts),
                    f'{label} must stay a short ASCII path below the coordinator (<=80 characters, no spaces)')
        require(len(str(work)) <= 200, 'work-root absolute path is too long; choose a shorter run name')
    else:
        require(os.environ.get('GITHUB_ACTIONS') == 'true'
                and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
                and os.environ.get('GITHUB_REPOSITORY') == 'gx0404/gx_shell',
                'local builds require GX_LOCAL_BUILD_ROOT; release builds require the real GitHub-hosted integration runner')
        require(not args.allow_dirty, '--allow-dirty is only allowed with GX_LOCAL_BUILD_ROOT')
        require(bool(os.environ.get('RUNNER_TEMP')), 'RUNNER_TEMP is required on CI')
        boundary = sources._safe_path(Path(os.environ['RUNNER_TEMP']))
        require(all(root != boundary and root.is_relative_to(boundary) for root in (omz, herdr)),
                'CI component checkouts must be independent directories under RUNNER_TEMP')
        require(work.parent == boundary, 'CI work-root must be a new child of RUNNER_TEMP')
        require(len(str(work)) <= 80 and re.fullmatch(r'[A-Za-z0-9_./:\\-]+', str(work)) is not None,
                'CI work-root must be a short ASCII path (<=80 characters, no spaces or shell metacharacters)')
    require(boundary.is_dir(), 'GX_LOCAL_BUILD_ROOT/RUNNER_TEMP must be an existing directory')
    require((os.name == 'nt') == (args.platform == 'windows-x64'), 'builder OS and target platform differ')
    if args.platform == 'ubuntu-amd64':
        require(Path('/usr/share/keyrings/ubuntu-archive-keyring.gpg').is_file(),
                'Ubuntu archive keyring is required for the pinned Zsh SDK')

    def checkout(name, root, revision=None):
        try:
            sources._repository(root)
            if name != 'coordinator':
                sources._origin(root, entries[name])
            head = sources._git(root, 'rev-parse', 'HEAD', offline=True).stdout.strip()
            sources._require_commit(root, head)
            require(revision is None or head.lower() == revision.lower(), f'{name}: HEAD differs from the locked SHA')
            flags = sources._git(root, 'ls-files', '-v', '-z', offline=True).stdout.split('\0')
            require(not any(item and (item[0].islower() or item[0] == 'S') for item in flags),
                    f'{name}: assume-unchanged/skip-worktree masks are not permitted')
            status = sources._git(root, 'status', '--porcelain=v1', '--untracked-files=all',
                                  '--ignore-submodules=none', offline=True).stdout
            require(not status or (local and args.allow_dirty and name != 'herdr'),
                    f'{name}: dirty checkout; only local coordinator/Oh My Zsh changes may use --allow-dirty')
            return {'path': str(root), 'revision': head, 'dirty': bool(status)}
        except sources.SourceError as error:
            raise ValueError(f'{name}: {error}') from None

    resolved = {'coordinator': checkout('coordinator', coordinator),
                'components': dict(entries), 'lock_digest': checked['lock_digest']}
    for name, root in (('ohmyzsh', omz), ('herdr', herdr)):
        resolved['components'][name] = {**entries[name], **checkout(name, root, entries[name]['revision'])}
    scripts = omz / 'scripts'
    producer_files = ('gx_dependencies.py', 'gx_build_herdr.py', 'gx_release.py', 'gx_build_zsh.py', 'gx_package.py')
    for name in producer_files:
        path = sources._safe_path(scripts / name)
        require(path.is_file(), f'missing pinned producer: {path}')
    sys.path.insert(0, str(scripts))
    import gx_dependencies as deps
    import gx_release as release
    dependency_lock = sources._safe_path(scripts / 'packaging/dependencies.json')
    pinned = release.load_lock(omz)['herdr']
    require_herdr_source(pinned, entries['herdr']['revision'])
    zsh_lock = sources._safe_path(scripts / 'packaging/zsh-runtime-lock.json')
    require(zsh_lock.is_file(), 'missing pinned Zsh runtime lock')
    inputs = {str(path): digest(path) for path in
              [coordinator / 'scripts/gx_shell_stage_shell.sh', coordinator / 'scripts/gx_shell_sources.py',
               dependency_lock, zsh_lock, *(scripts / name for name in producer_files)]}
    resolved.update(schema=1, platform=args.platform, builder='local' if local else 'github-actions',
                    jobs=int(args.jobs), local=local, allow_dirty=args.allow_dirty,
                    components_lock=str(lock_path), input_sha256=inputs,
                    stage=str(work / 'ohmyzsh-stage'), archive=str(work / 'stage.tar'))
    require(lock_path.read_bytes() == lock_raw, 'components lock changed during preflight')
    work.mkdir(parents=True)
    (work / 'components.lock.json').write_bytes(lock_raw)
    write_json(work / 'resolved-sources.json', resolved)
    env = os.environ.copy()
    env.update(CARGO_BUILD_JOBS=str(args.jobs), CMAKE_BUILD_PARALLEL_LEVEL=str(args.jobs),
               GX_CPU_JOBS=str(args.jobs), GX_ZSH_JOBS=str(args.jobs),
               MAKEFLAGS='-j' + str(args.jobs), PYTHONDONTWRITEBYTECODE='1',
               GIT_NO_REPLACE_OBJECTS='1', GIT_OPTIONAL_LOCKS='0')

    def run(name, *arguments):
        print('gx-shell-stage: ' + name + ' ' + ' '.join(map(str, arguments)), flush=True)
        subprocess.run([sys.executable, '-B', str(scripts / name), *map(str, arguments)],
                       cwd=omz, env=env, check=True)

    cache = work / 'gx-cache'
    herdr_build = work / 'gx-herdr'
    zsh_build = work / 'gx-zsh'
    dependencies = work / 'gx-dependencies'
    stage = work / 'ohmyzsh-stage'
    run('gx_dependencies.py', '--lock', dependency_lock, 'audit', '--platform', args.platform)
    # The dependency CLI has no --herdr-source-root; use its verified archive API before fetch.
    deps.fetch_artifact(pinned['source'], cache, repository_root=herdr)
    for action in ('fetch', 'verify'):
        run('gx_dependencies.py', '--lock', dependency_lock, action, '--platform', args.platform, '--cache', cache)
    run('gx_build_herdr.py', '--repo', omz, '--herdr-source-root', herdr, '--platform', args.platform,
        '--work', work / 'gx-herdr-work', '--cache', cache, '--output', herdr_build)
    run('gx_release.py', 'verify-herdr', '--repo', omz, '--platform', args.platform, '--herdr-build', herdr_build)
    run('gx_build_zsh.py', '--lock', zsh_lock, 'fetch', '--platform', args.platform, '--cache', cache)
    run('gx_build_zsh.py', '--lock', zsh_lock, 'build', '--platform', args.platform, '--cache', cache,
        '--work', work / 'gx-zsh-work', '--output', zsh_build, '--jobs', args.jobs)
    run('gx_build_zsh.py', '--lock', zsh_lock, 'verify', '--platform', args.platform, '--build', zsh_build)
    run('gx_dependencies.py', '--lock', dependency_lock, 'assemble', '--platform', args.platform,
        '--cache', cache, '--herdr-build', herdr_build, '--zsh-build', zsh_build, '--output', dependencies)
    run('gx_package.py', 'stage', '--repo', omz, '--ref', resolved['components']['ohmyzsh']['revision'],
        '--platform', args.platform, '--dependencies', dependencies, '--output', stage,
        *(['--allow-dirty'] if local else []))
    run('gx_package.py', 'verify-stage', '--stage', stage)
    manifest_path = stage / 'package-manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    receipt = json.loads((herdr_build / 'herdr-build.json').read_text(encoding='utf-8'))
    require(manifest['platform'] == args.platform
            and manifest['source']['revision'] == resolved['components']['ohmyzsh']['revision']
            and manifest['herdr']['revision'] == resolved['components']['herdr']['revision']
            and manifest['herdr_build'] == receipt, 'stage identity or herdr receipt differs from resolved sources')
    require(receipt['builder'] == resolved['builder'], 'herdr builder identity differs from the selected build mode')
    require(type(manifest['publishable']) is bool and (not local or manifest['publishable'] is False),
            'local stage must be explicitly non-publishable')
    require(lock_path.read_bytes() == lock_raw, 'components lock changed during build')
    require(all(digest(Path(path)) == value for path, value in inputs.items()), 'producer inputs changed during build')
    require(checkout('coordinator', coordinator) == resolved['coordinator'], 'coordinator changed during build')
    for name, root in (('ohmyzsh', omz), ('herdr', herdr)):
        current = checkout(name, root, entries[name]['revision'])
        require(all(current[key] == resolved['components'][name][key] for key in current),
                f'{name}: checkout changed during build')

    archive = work / 'stage.tar'
    with tarfile.open(archive, 'x', format=tarfile.PAX_FORMAT) as stream:
        for path in sorted(stage.iterdir()):
            stream.add(path, arcname=path.name)
    provenance = {**resolved, 'publishable': manifest['publishable'],
                  'assemble_requires_allow_dirty': local, 'artifact_suffix': '-local' if local else '',
                  'package_manifest': {'path': str(manifest_path), 'sha256': digest(manifest_path)},
                  'herdr_build': receipt, 'zsh_build': manifest['zsh_build'],
                  'archive_sha256': digest(archive), 'archive_size': archive.stat().st_size}
    write_json(work / 'stage-provenance.json', provenance)
    print(json.dumps({'stage': str(stage), 'archive': str(archive),
                      'resolved_sources': str(work / 'resolved-sources.json'),
                      'provenance': str(work / 'stage-provenance.json'),
                      'publishable': manifest['publishable']}, sort_keys=True))


try:
    main()
except subprocess.CalledProcessError as error:
    print(f'gx-shell-stage: producer failed (exit {error.returncode}); partial outputs are retained, use a new work-root',
          file=sys.stderr)
    sys.exit(1)
except (ValueError, OSError, KeyError, ImportError) as error:
    print(f'gx-shell-stage: {error}', file=sys.stderr)
    sys.exit(1)
PY

#!/usr/bin/env python3
"""Validate source locks and materialize independent, pinned component repositories.

Commit existence and component-branch ancestry are separate checks: checkout
checks the former without consulting a floating branch; check --require-remote
verifies the latter and the remote default HEAD. Only the explicit update command
resolves new component-branch heads, verifies their default HEADs and changes a lock.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

COMPONENT_BRANCHES = {
    "herdr": "feature/gx_herdr",
    "ohmyzsh": "feature/gx_ohmyzsh",
    "wezterm": "feature/gx_wezterm",
}
COMPONENTS = tuple(COMPONENT_BRANCHES)
REVISION = re.compile(r"[0-9a-fA-F]{40}\Z")


class SourceError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SourceError(message)


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, "lock contains a duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise SourceError("lock contains a non-JSON numeric constant")


def _read_lock(path: Path) -> tuple[bytes, dict]:
    try:
        raw = Path(path).read_bytes()
        lock = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                          parse_constant=_invalid_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SourceError("cannot read a valid UTF-8 JSON lock") from None
    require(isinstance(lock, dict), "lock must be an object")
    require(type(lock.get("schema")) is int and lock["schema"] == 1, "lock schema must be 1")
    entries = lock.get("components")
    require(isinstance(entries, dict) and set(entries) == set(COMPONENTS),
            "lock must contain exactly herdr, ohmyzsh and wezterm")
    for name in COMPONENTS:
        entry = entries[name]
        require(isinstance(entry, dict) and set(entry) == {"repository", "branch", "revision"},
                f"{name}: expected repository, branch and revision fields")
        require(entry["repository"] == f"gx0404/{name}", f"{name}: unexpected repository")
        require(entry["branch"] == COMPONENT_BRANCHES[name],
                f"{name}: branch must be {COMPONENT_BRANCHES[name]}")
        require(isinstance(entry["revision"], str) and REVISION.fullmatch(entry["revision"]) is not None,
                f"{name}: revision must be a full 40-hex commit SHA")
    return raw, lock


def load_lock(path: str | Path) -> dict:
    """Return the validated complete lock, including extra top-level metadata."""
    return _read_lock(Path(path))[1]


def lock_digest(path: str | Path) -> str:
    """Hash the exact file bytes, not normalized JSON or a self-referential field."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        raise SourceError("cannot read lock for SHA-256 digest") from None


def _git(cwd: Path, *args: str, offline: bool = False, codes: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess:
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    for key in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM",
                "GIT_SSH", "GIT_SSH_COMMAND", "GIT_ASKPASS"):
        if key in os.environ:
            env[key] = os.environ[key]
    env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never", GIT_NO_REPLACE_OBJECTS="1",
               GIT_CEILING_DIRECTORIES=str(cwd.absolute()), GIT_OPTIONAL_LOCKS="0")
    if offline:
        env["GIT_ALLOW_PROTOCOL"] = ""
    command = ["git", "--no-pager", "-c", "core.hooksPath=/dev/null",
               "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
               "-c", "protocol.ext.allow=never", "-c", "credential.interactive=false", *args]
    try:
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=600)
    except (OSError, subprocess.TimeoutExpired):
        raise SourceError("Git is unavailable or the source operation timed out") from None
    require(result.returncode in codes, "Git source operation failed; captured transport diagnostics are not echoed")
    return result


def _url(entry: dict) -> str:
    return f"https://github.com/{entry['repository']}.git"


def _link(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0)
                                             & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _safe_path(path: Path, root: Path | None = None) -> Path:
    require(".." not in path.parts, "source paths must not contain parent traversal")
    path = path.absolute()
    if root is not None:
        require(path != root and path.is_relative_to(root), "source path escapes output root")
    for item in (*reversed(path.parents), path):
        require(not _link(item), "source path must not traverse a symlink or junction")
    return path


def _check_metadata(gitdir: Path) -> None:
    require(gitdir.is_dir() and not _link(gitdir), "repository metadata must be a real directory")
    for current, dirs, files in os.walk(gitdir, followlinks=False):
        directory = Path(current)
        for name in dirs + files:
            require(not _link(directory / name), "repository metadata must not contain symlinks or junctions")
        if directory.name == "info":
            require(not any(name in files for name in ("alternates", "http-alternates", "grafts")),
                    "repository must not borrow objects or graft history")
        require("commondir" not in files, "repository must not share external Git metadata")


def _repository(path: Path, *, owner: Path | None = None) -> None:
    marker = path / ".git"
    require(not _link(marker), "repository .git must not be a symlink or junction")
    if owner is None:
        require(marker.is_dir(), "component must have its own .git directory; inherited Git is refused")
        gitdir = marker
    elif marker.is_file():
        try:
            text = marker.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            raise SourceError("invalid submodule Git metadata") from None
        require(text.startswith("gitdir: "), "invalid submodule Git metadata")
        gitdir = (path / text[8:]).absolute()
        gitdir = Path(os.path.normpath(gitdir))
        _safe_path(gitdir, owner / ".git/modules")
    else:
        require(marker.is_dir(), "submodule has no independent Git metadata")
        gitdir = marker
    _check_metadata(gitdir)
    top = _git(path, "rev-parse", "--show-toplevel", offline=True).stdout.strip()
    actual = _git(path, "rev-parse", "--absolute-git-dir", offline=True).stdout.strip()
    common = _git(path, "rev-parse", "--git-common-dir", offline=True).stdout.strip()
    require(Path(top).resolve() == path.resolve() and Path(actual).resolve() == gitdir.resolve()
            and (path / common).resolve() == gitdir.resolve(),
            "checkout uses inherited or external Git metadata")


def _require_commit(path: Path, revision: str) -> None:
    kind = _git(path, "cat-file", "-t", revision, offline=True, codes=(0, 1, 128))
    require(kind.returncode == 0 and kind.stdout.strip() == "commit",
            "locked SHA does not exist as a commit")


def _clean_head(path: Path, revision: str) -> None:
    _require_commit(path, revision)
    head = _git(path, "rev-parse", "HEAD", offline=True).stdout.strip()
    require(head.lower() == revision.lower(), "existing checkout HEAD differs from locked SHA; refusing to reset")
    symbolic = _git(path, "symbolic-ref", "-q", "HEAD", offline=True, codes=(0, 1))
    require(symbolic.returncode == 1, "existing checkout must already have a detached HEAD")
    flags = _git(path, "ls-files", "-v", "-z", offline=True).stdout.split("\0")
    require(not any(item and (item[0].islower() or item[0] == "S") for item in flags),
            "checkout must not mask changes with assume-unchanged or skip-worktree")
    dirty = _git(path, "status", "--porcelain=v1", "--untracked-files=all",
                 "--ignore-submodules=none", offline=True).stdout
    require(not dirty, "existing checkout is dirty; refusing to overwrite user files")


def _origin(path: Path, entry: dict) -> None:
    result = _git(path, "config", "--get-all", "remote.origin.url", offline=True, codes=(0, 1))
    repository = entry["repository"]
    accepted = {f"{prefix}{repository}{suffix}"
                for prefix in ("https://github.com/", "git@github.com:", "ssh://git@github.com/")
                for suffix in ("", ".git")}
    require(len(result.stdout.splitlines()) == 1 and result.stdout.strip() in accepted,
            "existing checkout has a different or credential-bearing origin")


def _gitlinks(path: Path) -> list[tuple[str, str]]:
    entries = _git(path, "ls-files", "--stage", "-z", offline=True).stdout.split("\0")
    result = []
    for entry in entries:
        if not entry:
            continue
        info, filename = entry.split("\t", 1)
        mode, revision, stage = info.split()
        if mode != "160000":
            continue
        relative = PurePosixPath(filename)
        require(stage == "0" and not relative.is_absolute() and bool(relative.parts)
                and ".." not in relative.parts and ".git" not in relative.parts
                and "\\" not in filename and ":" not in filename, "unsafe submodule path")
        _safe_path(path / filename, path)
        result.append((filename, revision))
    if result:
        marker = path / ".gitmodules"
        require(marker.is_file() and not _link(marker), "submodules require a regular .gitmodules file")
    return result


def _checkout_lf(path: Path) -> None:
    _git(path, "config", "--local", "core.autocrlf", "false", offline=True)
    _git(path, "config", "--local", "core.eol", "lf", offline=True)


def _submodules(owner: Path, path: Path, *, offline: bool, materialize: bool) -> None:
    for relative, revision in _gitlinks(path):
        child = path / relative
        _safe_path(child, owner)
        marker = child / ".git"
        missing = not marker.exists() and not _link(marker)
        if missing:
            require(not child.exists() or (child.is_dir() and not any(child.iterdir())),
                    "uninitialized submodule directory is not empty")
            require(not offline, "offline checkout requires all recursive submodules to be present")
            if not materialize:
                continue
            _git(path, "-c", "core.autocrlf=false", "-c", "core.eol=lf",
                 "submodule", "update", "--init", "--checkout", "--", relative)
        _repository(child, owner=owner)
        if missing:
            _checkout_lf(child)
        _clean_head(child, revision)
        _submodules(owner, child, offline=offline, materialize=materialize)


def _existing(path: Path, name: str, entry: dict, *, offline: bool) -> None:
    require(path.is_dir(), "existing component path is not a directory")
    _repository(path)
    _origin(path, entry)
    _clean_head(path, entry["revision"])
    if name == "wezterm":
        _submodules(path, path, offline=offline, materialize=False)


def _init(path: Path, entry: dict) -> None:
    _git(path, "init", "--quiet", "--template=", ".")
    _repository(path)
    _checkout_lf(path)
    _git(path, "remote", "add", "origin", _url(entry))


def _branch_ref(entry: dict) -> str:
    return f"refs/heads/{entry['branch']}"


def _tracking_ref(entry: dict) -> str:
    return f"refs/remotes/origin/{entry['branch']}"


def _remote_head(path: Path, entry: dict) -> str:
    _init(path, entry)
    branch_ref = _branch_ref(entry)
    listing = _git(path, "ls-remote", "--symref", _url(entry), "HEAD", branch_ref).stdout.splitlines()
    default_refs = []
    branch_revisions = []
    for line in listing:
        fields = line.split("\t")
        if len(fields) != 2:
            continue
        value, name = fields
        if name == "HEAD" and value.startswith("ref: "):
            default_refs.append(value[5:])
        elif name == branch_ref:
            branch_revisions.append(value)
    require(default_refs == [branch_ref],
            f"remote default HEAD does not point to {branch_ref}")
    require(len(branch_revisions) == 1 and REVISION.fullmatch(branch_revisions[0]) is not None,
            f"remote {branch_ref} did not resolve to a full commit SHA")
    _git(path, "fetch", "--quiet", "--no-tags", "--no-recurse-submodules", _url(entry),
         f"{branch_ref}:{_tracking_ref(entry)}")
    revision = _git(path, "rev-parse", _tracking_ref(entry), offline=True).stdout.strip()
    require(REVISION.fullmatch(revision) is not None, "remote branch did not resolve to a full commit SHA")
    _require_commit(path, revision)
    return revision


def check(path: str | Path, *, require_remote: bool = False) -> dict:
    raw, lock = _read_lock(Path(path))
    if require_remote:
        for name, entry in lock["components"].items():
            with tempfile.TemporaryDirectory(prefix=f"gx-source-check-{name}-") as directory:
                repo = Path(directory)
                _remote_head(repo, entry)
                exists = _git(repo, "cat-file", "-t", entry["revision"], offline=True, codes=(0, 1, 128))
                if exists.returncode != 0:
                    _git(repo, "fetch", "--quiet", "--no-tags", "--no-recurse-submodules",
                         _url(entry), entry["revision"])
                _require_commit(repo, entry["revision"])
                ancestry = _git(repo, "merge-base", "--is-ancestor", entry["revision"],
                                _tracking_ref(entry), offline=True, codes=(0, 1))
                require(ancestry.returncode == 0,
                        f"{name}: locked commit exists but is not an ancestor of {entry['branch']}")
    return {"lock_digest": hashlib.sha256(raw).hexdigest(), "components": lock["components"]}


def checkout(path: str | Path, output: str | Path, components: list[str] | None = None, *, offline: bool = False) -> dict:
    raw, lock = _read_lock(Path(path))
    names = list(dict.fromkeys(COMPONENTS if components is None else components))
    require(bool(names) and all(name in COMPONENTS for name in names), "select at least one known component")
    root = _safe_path(Path(output))
    require(not root.exists() or root.is_dir(), "output must be a directory")
    for name in names:
        target = _safe_path(root / name, root)
        if target.exists():
            _existing(target, name, lock["components"][name], offline=offline)
        else:
            require(not offline, f"{name}: offline checkout requires an existing pinned clone")
    root.mkdir(parents=True, exist_ok=True)
    result = {}
    for name in names:
        target = _safe_path(root / name, root)
        entry = lock["components"][name]
        if not target.exists():
            with tempfile.TemporaryDirectory(prefix=f".{name}-", dir=root) as directory:
                temporary = Path(directory)
                staging = temporary / "checkout"
                staging.mkdir()
                _init(staging, entry)
                _git(staging, "fetch", "--quiet", "--no-tags", "--no-recurse-submodules",
                     _url(entry), entry["revision"])
                _require_commit(staging, entry["revision"])
                _git(staging, "checkout", "--quiet", "--detach", entry["revision"], "--")
                if name == "wezterm":
                    _submodules(staging, staging, offline=False, materialize=True)
                _existing(staging, name, entry, offline=True)
                _safe_path(target, root)
                require(not target.exists(), "component destination appeared during checkout")
                staging.rename(target)
        elif name == "wezterm" and not offline:
            _submodules(target, target, offline=False, materialize=True)
        _existing(target, name, entry, offline=True)
        result[name] = {**entry, "path": str(target)}
    return {"lock_digest": hashlib.sha256(raw).hexdigest(), "components": result}


def update(path: str | Path) -> dict:
    path = _safe_path(Path(path))
    raw, lock = _read_lock(path)
    require(path.is_file(), "update requires an existing complete lock")
    for name in COMPONENTS:
        with tempfile.TemporaryDirectory(prefix=f"gx-source-update-{name}-") as directory:
            lock["components"][name]["revision"] = _remote_head(Path(directory), lock["components"][name])
    payload = (json.dumps(lock, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{path.name}-", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
        _safe_path(path)
        require(path.read_bytes() == raw, "lock changed during update; refusing to overwrite")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"lock_digest": hashlib.sha256(payload).hexdigest(), "components": lock["components"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validator = commands.add_parser("check", help="validate lock offline; remote checks are opt-in")
    validator.add_argument("--lock", required=True, type=Path)
    validator.add_argument("--require-remote", action="store_true",
                           help="verify commit existence, component-branch ancestry and default HEAD (requires network)")
    materializer = commands.add_parser("checkout", help="checkout locked SHAs without resolving branch heads")
    materializer.add_argument("--lock", required=True, type=Path)
    materializer.add_argument("--output", required=True, type=Path)
    materializer.add_argument("--component", action="append", choices=COMPONENTS)
    materializer.add_argument("--offline", action="store_true", help="reuse complete pinned clones; never fetch")
    updater = commands.add_parser("update", help="verify default HEADs, resolve component-branch heads and atomically replace the lock")
    updater.add_argument("--lock", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            result = check(args.lock, require_remote=args.require_remote)
        elif args.command == "checkout":
            result = checkout(args.lock, args.output, args.component, offline=args.offline)
        else:
            result = update(args.lock)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except SourceError as exc:
        print(f"source error: {exc}", file=sys.stderr)
    except OSError:
        print("source error: filesystem operation failed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

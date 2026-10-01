#!/usr/bin/env python3
"""Assemble and build the GX Shell installers from the component stages.

Inputs are complete stages from independently locked gx0404/wezterm and
gx0404/ohmyzsh revisions, with gx0404/herdr provenance checked separately.
The coordinator commit comes from this repository's HEAD. Assembly, build and
verification are offline: they neither check out components nor resolve component-branch heads.
Outputs are a Windows Setup EXE or Ubuntu DEB, corresponding-source archive,
schema-2 manifest and SHA-256 sidecars.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = "gx-shell"
PLATFORMS = {
    "windows": {"wezterm": "windows", "ohmyzsh": "windows-x64", "herdr": "windows-installer", "arch": "x64"},
    "linux": {"wezterm": "deb", "ohmyzsh": "ubuntu-amd64", "herdr": "deb", "arch": "amd64"},
}
FONT_SUFFIXES = {".ttf", ".ttc"}
LINUX_FONT_DIR = "usr/share/fonts/truetype/gx-shell"
LINUX_COMPONENT_FONT_DIRS = ("usr/share/fonts/truetype/ohmyzsh-gx", "usr/share/fonts/truetype/wezterm-gx")
LINUX_ENTRY_POINTS = {
    "usr/bin/gx-zsh": "../lib/ohmyzsh-gx/bin/gx-zsh",
    "usr/bin/herdr": "../lib/ohmyzsh-gx/bin/herdr",
    "usr/bin/wezterm-gx": "../lib/wezterm-gx/wezterm-gx",
    "usr/bin/wezterm-gx-gui": "../lib/wezterm-gx/wezterm-gx-gui",
}
DOCUMENTS = {
    "windows": {"licenses/NotoSansCJK-OFL-1.1.txt": "packaging/licenses/NotoSansCJK-OFL-1.1.txt"},
    "linux": {"usr/share/doc/gx-shell/copyright": "packaging/debian/copyright",
              "usr/share/doc/gx-shell/NotoSansCJK-OFL-1.1.txt": "packaging/licenses/NotoSansCJK-OFL-1.1.txt"},
}
HERDR_COMPLETION = "ohmyzsh-gx/gx/omz-custom/plugins/herdr/_herdr"
# The only herdr builder whose stages may be released; GX_LOCAL_BUILD_ROOT builds record "local".
RELEASE_BUILDER = "github-actions"
REQUIRED = {
    "windows": (
        "bin/gx-zsh.exe", "bin/herdr.exe", "lib/herdr/herdr.exe", "lib/herdr/conpty/conpty.dll",
        "runtime/msys64/usr/bin/zsh.exe", "share/ohmyzsh-gx/oh-my-zsh.sh", "share/" + HERDR_COMPLETION,
        "wezterm/wezterm.exe", "wezterm/wezterm-gui.exe", "wezterm/wezterm-gx.exe", "wezterm/wezterm-gx-cli.exe",
        "wezterm/resources/resource-version",
    ),
    "linux": (
        "usr/lib/ohmyzsh-gx/bin/gx-zsh", "usr/lib/ohmyzsh-gx/bin/herdr", "usr/lib/ohmyzsh-gx/lib/herdr/herdr",
        "usr/lib/ohmyzsh-gx/libexec/zsh/zsh", "usr/share/ohmyzsh-gx/oh-my-zsh.sh", "usr/share/" + HERDR_COMPLETION,
        "usr/lib/wezterm-gx/wezterm", "usr/lib/wezterm-gx/wezterm-gui", "usr/lib/wezterm-gx/wezterm-gx",
        "usr/lib/wezterm-gx/wezterm-gx-gui", "usr/share/wezterm-gx/resource-version",
        "usr/share/applications/org.gx0404.wezterm.desktop",
    ),
}
MAINTAINER_SCRIPTS = ("preinst", "postinst", "postrm")


class PackageError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PackageError(message)


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def read_json(path: Path) -> dict:
    require(path.is_file(), f"missing manifest: {path}")
    require(not is_link(path), f"manifest must not be a symlink or reparse point: {path}")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate manifest JSON key")
            result[key] = value
        return result

    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                       parse_constant=lambda value: require(False, "non-JSON numeric constant"))
    require(isinstance(value, dict), f"manifest must be a JSON object: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def git(*args: str) -> str:
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_NO_REPLACE_OBJECTS="1", GIT_NO_LAZY_FETCH="1")
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True,
                          text=True, encoding="utf-8", env=env).stdout.strip()


def version_from_changelog(root: Path = ROOT, *, release: bool = False) -> str:
    found = re.findall(r"^## (\d+)\.(\d+)\.(\d+)\((TBD|\d{8}|\d{4}-\d{2}-\d{2})\)\s*$",
                       (root / "CHANGELOG.md").read_text(encoding="utf-8"), re.M)
    require(bool(found), "CHANGELOG.md has no '## X.Y.Z(TBD|date)' version heading")
    highest = max(tuple(map(int, item[:3])) for item in found)
    version = ".".join(map(str, highest))
    require(not release or all(item[3] != "TBD" for item in found if tuple(map(int, item[:3])) == highest),
            f"CHANGELOG.md still dates {version} as (TBD); replace TBD with the release date before publishing")
    return version


def validate_version(version: str | None, root: Path = ROOT) -> str:
    expected = version_from_changelog(root)
    version = (version or "").strip().removeprefix("gx-shell-v")
    require(not version or version == expected,
            f"requested version {version} differs from CHANGELOG.md ({expected}); update CHANGELOG.md first")
    return expected


def source_info() -> tuple[str, bool, int]:
    sha = git("rev-parse", "HEAD")
    dirty = bool(git("status", "--porcelain", "--untracked-files=normal"))
    return sha, dirty, int(git("show", "-s", "--format=%ct", sha))


def read_components_lock(path: Path | None = None) -> tuple[dict, str, bytes]:
    import gx_shell_sources as sources

    path = Path(path) if path is not None else ROOT / "components.lock.json"
    try:
        before = path.read_bytes()
        lock = sources.load_lock(path)
        checksum = sources.lock_digest(path)
        require(before == path.read_bytes() and hashlib.sha256(before).hexdigest() == checksum,
                "components lock changed while being read")
    except (ValueError, OSError) as error:
        raise PackageError(f"invalid components lock: {error}") from None
    return lock, checksum, before


def relative_path(value: object) -> str:
    require(isinstance(value, str) and bool(value), "inventory path must be nonempty text")
    parts = value.split("/")
    require(not any(ord(char) < 32 for char in value) and not any(char in value for char in '\\:*?"<>|')
            and all(part not in ("", ".", "..") and part.rstrip(" .") == part for part in parts)
            and all(re.fullmatch(r"(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part) is None for part in parts),
            "unsafe inventory path")
    return value


def is_link(path: Path) -> bool:
    details = path.lstat()
    return path.is_symlink() or bool(getattr(details, "st_file_attributes", 0) & 0x400)


def safe_directory(path: Path) -> None:
    require(path.is_dir(), f"missing directory: {path}")
    require(all(not is_link(item) for item in (path.absolute(), *path.absolute().parents)),
            f"directory traverses a symlink or reparse point: {path}")


def inventory(root: Path, *, links: dict | None = None, exclude: tuple[str, ...] = (),
              executable: bool = False) -> list[dict]:
    safe_directory(root)
    links = links or {}
    records = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(directory) / name
            relative = relative_path(path.relative_to(root).as_posix())
            if is_link(path):
                require(path.is_symlink() and relative in links and os.readlink(path) == links[relative],
                        f"unexpected payload symlinks: {relative}")
                require(path.resolve().is_relative_to(root.resolve()) and path.is_file(),
                        f"unsafe or dangling payload symlink: {relative}")
                records.append({"path": relative, "symlink": os.readlink(path)})
                if name in dirs:
                    dirs.remove(name)
            elif path.is_file():
                if relative not in exclude:
                    record = {"path": relative, "sha256": digest(path), "size": path.stat().st_size}
                    if executable:
                        record["executable"] = bool(path.stat().st_mode & 0o111)
                    records.append(record)
            else:
                require(path.is_dir(), f"special file forbidden: {relative}")
    return sorted(records, key=lambda item: item["path"])


def verify_inventory(root: Path, records: object, *, links: dict | None = None,
                     exclude: tuple[str, ...] = ()) -> None:
    require(isinstance(records, list) and bool(records), "missing complete inventory")
    expected = {}
    folded = set()
    for record in records:
        require(isinstance(record, dict), "invalid inventory record")
        name = relative_path(record.get("path"))
        require(name not in expected and name.casefold() not in folded, f"duplicate inventory path: {name}")
        require(name not in exclude, f"inventory includes its own manifest: {name}")
        if "symlink" in record:
            require(set(record) == {"path", "symlink"} and (links or {}).get(name) == record["symlink"],
                    f"unexpected payload symlinks: {name}")
        else:
            require({"path", "size", "sha256"} <= set(record) <= {"path", "size", "sha256", "executable"}
                    and type(record["size"]) is int and record["size"] >= 0
                    and isinstance(record["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", record["sha256"]),
                    f"invalid file inventory record: {name}")
            require("executable" not in record or type(record["executable"]) is bool,
                    f"invalid executable bit: {name}")
        expected[name] = record
        folded.add(name.casefold())
    actual = {item["path"]: item for item in inventory(root, links=links, exclude=exclude)}
    for name in actual.keys() & expected.keys():
        if "executable" in expected[name]:
            actual[name]["executable"] = bool((root / name).stat().st_mode & 0o111)
    missing, extra = sorted(expected.keys() - actual.keys()), sorted(actual.keys() - expected.keys())
    changed = sorted(name for name in actual.keys() & expected.keys() if actual[name] != expected[name])
    require(not (missing or extra or changed),
            f"inventory mismatch: missing={missing}, extra={extra}, changed={changed}")


def stage_links(platform: str, component: str, prefix: str = "") -> dict:
    if platform != "linux":
        return {}
    names = ("wezterm-gx", "wezterm-gx-gui") if component == "wezterm" else ("gx-zsh", "herdr")
    return {prefix + name: target for name, target in LINUX_ENTRY_POINTS.items() if PurePosixPath(name).name in names}


def check_wezterm_origin(info: dict, platform: str, sha: str, allow_dirty: bool) -> None:
    require(type(info.get("schema")) is int and info["schema"] == 2
            and info.get("platform") == PLATFORMS[platform]["wezterm"],
            f"WezTerm stage is not a schema 2 {PLATFORMS[platform]['wezterm']} stage")
    require(info.get("source_repository") == "gx0404/wezterm", "WezTerm stage has a different repository")
    require(info.get("source_commit") == sha, "WezTerm stage was built from a different commit")
    require(type(info.get("source_dirty")) is bool, "WezTerm stage lacks source dirty provenance")
    require(allow_dirty or info["source_dirty"] is False, "WezTerm stage was built from a dirty tree")


def check_wezterm_stage(stage: Path, platform: str, sha: str, allow_dirty: bool) -> dict:
    safe_directory(stage)
    require(not is_link(stage / "stage-manifest.json"), "WezTerm manifest must not be a symlink")
    info = read_json(stage / "stage-manifest.json")
    check_wezterm_origin(info, platform, sha, allow_dirty)
    verify_inventory(stage, info.get("files"), links=stage_links(platform, "wezterm", "root/"),
                     exclude=("stage-manifest.json",))
    require(isinstance(info.get("binaries"), dict) and bool(info["binaries"]), "WezTerm stage lacks binary hashes")
    if platform == "linux":
        require(isinstance(info.get("deb_depends"), str) and bool(info["deb_depends"].strip()),
                "WezTerm deb stage lacks its dpkg-shlibdeps dependencies")
        binaries = stage / "root/usr/lib/wezterm-gx"
    else:
        binaries = stage / "app"
    safe_directory(binaries)
    for name, checksum in sorted(info["binaries"].items()):
        relative_path(name)
        require("/" not in name, "unsafe WezTerm binary name")
        path = binaries / name
        require(path.is_file() and not is_link(path), f"WezTerm stage lacks the binary {name}")
        require(digest(path) == checksum, f"WezTerm stage binary {name} differs from its manifest SHA-256")
    inputs = ["gx-config-releases.json"] + (["terminal.ico"] if platform == "windows" else [])
    for name in inputs:
        require((stage / "build-inputs" / name).is_file(), f"WezTerm stage lacks build-inputs/{name}")
    read_json(stage / "build-inputs/gx-config-releases.json")
    return info


def check_ohmyzsh_origin(info: dict, platform: str, sha: str, herdr_sha: str, allow_dirty: bool) -> None:
    require(type(info.get("schema_version")) is int and info["schema_version"] == 1
            and info.get("platform") == PLATFORMS[platform]["ohmyzsh"],
            f"Oh My Zsh stage is not a {PLATFORMS[platform]['ohmyzsh']} stage")
    source, herdr, build = (info.get(key) for key in ("source", "herdr", "herdr_build"))
    require(all(isinstance(item, dict) for item in (source, herdr, build)), "Oh My Zsh stage lacks source provenance")
    require(source.get("repository") == "gx0404/ohmyzsh", "Oh My Zsh stage has a different repository")
    require(source.get("revision") == sha, "Oh My Zsh stage was built from a different commit")
    require(type(source.get("dirty")) is bool and type(info.get("publishable")) is bool,
            "Oh My Zsh stage lacks dirty/publishable provenance")
    require(allow_dirty or build.get("builder") == RELEASE_BUILDER,
            f"herdr was not built on GitHub Actions (builder {build.get('builder')!r}, 'local' for GX_LOCAL_BUILD_ROOT); "
            "such stages need --allow-dirty and are never publishable")
    require(allow_dirty or (info["publishable"] and source["dirty"] is False and not source.get("development", False)),
            "Oh My Zsh stage is a development (dirty) build")
    require(info.get("compliance_complete") is True, "Oh My Zsh stage lacks complete redistribution material")
    require(herdr.get("repository") == build.get("repository") == "gx0404/herdr",
            "herdr has a different repository")
    require(herdr.get("revision") == herdr_sha and build.get("revision") == herdr_sha,
            "herdr was not built from the locked commit")
    require(build.get("package_manager") == PLATFORMS[platform]["herdr"],
            "herdr was not built with the GX package identity")
    require(isinstance(build.get("source_sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", build["source_sha256"]),
            "herdr lacks corresponding-source SHA-256")
    require("source_sha256" not in herdr or herdr["source_sha256"] == build["source_sha256"],
            "herdr source SHA-256 disagrees with its build receipt")


def check_ohmyzsh_stage(stage: Path, platform: str, sha: str, allow_dirty: bool, *, herdr_sha: str) -> dict:
    safe_directory(stage)
    require(not is_link(stage / "package-manifest.json"), "Oh My Zsh manifest must not be a symlink")
    info = read_json(stage / "package-manifest.json")
    check_ohmyzsh_origin(info, platform, sha, herdr_sha, allow_dirty)
    require({path.name for path in stage.iterdir()} == {"package-manifest.json", "payload", "redistribution", "build-inputs"},
            "Oh My Zsh stage has missing or extra top-level inputs")
    for field, directory in (("payload", "payload"), ("redistribution", "redistribution"), ("build_inputs", "build-inputs")):
        verify_inventory(stage / directory, info.get(field),
                         links=stage_links(platform, "ohmyzsh") if field == "payload" else {})
    build = info["herdr_build"]
    materials = {item["path"]: item for item in info["redistribution"]}
    require(any(name.startswith("dependencies/herdr/") and item.get("sha256") == build["source_sha256"]
                and item.get("size", 0) > 0 for name, item in materials.items()),
            "herdr source SHA-256 has no corresponding redistribution file")
    if "source_artifacts" in build:
        require(isinstance(build["source_artifacts"], list) and bool(build["source_artifacts"]),
                "herdr build lacks source artifact receipts")
        for item in build["source_artifacts"]:
            require(isinstance(item, dict), "invalid herdr source artifact receipt")
            name = "dependencies/herdr/" + relative_path(item.get("path"))
            require(name in materials and all(item.get(key) == materials[name].get(key) for key in ("sha256", "size")),
                    "herdr source artifact differs from its build receipt")
    if "files" in build:
        prefix = "lib/herdr" if platform == "windows" else "usr/lib/ohmyzsh-gx/lib/herdr"
        verify_inventory(stage / "payload" / prefix, build["files"])
    return info


def copy_tree(source: Path, destination: Path, skip: tuple[str, ...] = ()) -> None:
    """Copy files and symlinks; refuse to overwrite anything already assembled."""
    for directory, names, files in os.walk(source):
        base = Path(directory)
        relative = base.relative_to(source).as_posix()
        names[:] = [name for name in names
                    if not (base / name).is_symlink() and not skipped(join(relative, name), skip)]
        entries = files + [name for name in os.listdir(base) if (base / name).is_symlink() and name not in files]
        for name in entries:
            rel = join(relative, name)
            if skipped(rel, skip):
                continue
            target = destination / rel
            require(not target.exists() and not target.is_symlink(),
                    f"two components provide the same path: {target.as_posix()}")
            target.parent.mkdir(parents=True, exist_ok=True)
            if (base / name).is_symlink():
                os.symlink(os.readlink(base / name), target)
            else:
                shutil.copy2(base / name, target)


def join(relative: str, name: str) -> str:
    return name if relative == "." else f"{relative}/{name}"


def skipped(relative: str, skip: tuple[str, ...]) -> bool:
    return any(relative == item or relative.startswith(item + "/") for item in skip)


def merge_fonts(sources: list[Path], destination: Path) -> list[dict]:
    fonts: dict[str, dict] = {}
    for folder in sources:
        for path in sorted(folder.iterdir()) if folder.is_dir() else []:
            if path.suffix.lower() not in FONT_SUFFIXES:
                continue
            checksum = digest(path)
            if path.name in fonts:
                require(fonts[path.name]["sha256"] == checksum, f"components ship different fonts named {path.name}")
                continue
            destination.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination / path.name)
            (destination / path.name).chmod(0o644)
            fonts[path.name] = {"name": path.name, "sha256": checksum, "size": path.stat().st_size}
    require(bool(fonts), "no fonts found in the component stages")
    return [fonts[name] for name in sorted(fonts)]


def normalize_modes(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            continue
        if path.is_dir():
            path.chmod(0o755)
        else:
            path.chmod(0o755 if path.stat().st_mode & 0o111 else 0o644)


def payload_inventory(root: Path) -> list[dict]:
    result = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            result.append({"path": name, "symlink": os.readlink(path)})
        elif path.is_file():
            result.append({"path": name, "sha256": digest(path), "size": path.stat().st_size})
    return result


def control_depends(stage: Path) -> str:
    control = (stage / "payload/DEBIAN/control").read_text(encoding="utf-8")
    match = re.search(r"^Depends:\s*(.+)$", control, re.M)
    require(match is not None, "Oh My Zsh deb stage control has no Depends")
    return match.group(1)


def merge_depends(*groups: str) -> str:
    """Union the Depends lists; a package required only as `(>= N.N...)` keeps just its highest minimum."""
    items = {" ".join(item.split()) for group in groups for item in group.split(",")}
    items.discard("")
    minimums: dict[str, dict[str, tuple[int, ...]]] = {}
    mixed = set()
    for item in items:
        match = re.fullmatch(r"([a-z0-9][a-z0-9+.-]*) ?\(>= ?(\d+(?:\.\d+)*)\)", item)
        if match:
            minimums.setdefault(match.group(1), {})[item] = tuple(map(int, match.group(2).split(".")))
        else:
            mixed.update(re.findall(r"(?:^|\|)\s*([a-z0-9][a-z0-9+.-]*)", item))
    for name, versions in minimums.items():
        if name not in mixed:
            items -= versions.keys() - {max(versions, key=lambda item: (versions[item], item))}
    return ", ".join(sorted(items))


def install_documents(payload: Path, platform: str) -> None:
    for name, source in DOCUMENTS[platform].items():
        target = payload / name
        require(not target.exists() and not target.is_symlink(), f"a component stage already provides {name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / source, target)


def component_metadata(lock: dict, wezterm: dict, ohmyzsh: dict) -> dict:
    result = {name: dict(entry) for name, entry in lock["components"].items()}
    result["wezterm"].update({key: wezterm.get(key) for key in
                              ("package_version", "product_version", "resource_version", "binaries")})
    result["ohmyzsh"].update({"version": ohmyzsh.get("version"), "lock_digest": ohmyzsh.get("lock_digest")})
    result["herdr"].update({key: ohmyzsh["herdr_build"].get(key) for key in
                            ("version", "target", "package_manager", "source_sha256", "builder")})
    result["zsh"] = {key: ohmyzsh.get("zsh_build", {}).get(key) for key in ("version", "binary_sha256")}
    return result


def verify_provenance(info: dict, lock: dict, checksum: str, sha: str, *, allow_dirty: bool) -> None:
    require(type(info.get("schema")) is int and info["schema"] == 2, "manifest must use schema 2")
    require(info.get("product") == PRODUCT and info.get("platform") in PLATFORMS, "invalid product/platform")
    require(isinstance(sha, str) and re.fullmatch(r"[0-9a-fA-F]{40}", sha), "invalid coordinator commit")
    require(info.get("source_commit") == sha, "manifest source_commit differs from coordinator HEAD")
    require(type(info.get("source_dirty")) is bool and type(info.get("local_build")) is bool
            and type(info.get("publishable")) is bool, "missing coordinator build provenance")
    require(info.get("coordinator") == {"repository": "gx0404/gx_shell", "revision": sha,
                                        "dirty": info["source_dirty"]}, "coordinator provenance mismatch")
    require(info.get("components_lock") == lock and info.get("components_lock_digest") == checksum,
            "components lock snapshot or digest mismatch")
    require(type(info.get("source_date_epoch")) is int and info["source_date_epoch"] >= 0, "invalid source epoch")
    stages = info.get("stages")
    require(isinstance(stages, dict) and set(stages) == {"wezterm", "ohmyzsh"}
            and all(isinstance(value, dict) for value in stages.values()), "missing component stage provenance")
    platform = info["platform"]
    require(info.get("architecture") == PLATFORMS[platform]["arch"], "manifest architecture mismatch")
    strict = info["publishable"] or not allow_dirty
    check_wezterm_origin(stages["wezterm"], platform, lock["components"]["wezterm"]["revision"], not strict)
    check_ohmyzsh_origin(stages["ohmyzsh"], platform, lock["components"]["ohmyzsh"]["revision"],
                         lock["components"]["herdr"]["revision"], not strict)
    require(info.get("components") == component_metadata(lock, stages["wezterm"], stages["ohmyzsh"]),
            "component provenance differs from locked stage receipts")
    require(not info["publishable"] or not (info["source_dirty"] or info["local_build"]),
            "development build cannot be marked publishable")
    require(allow_dirty or info["publishable"], "development build cannot be released")


def check_assembly(assembly: Path) -> dict:
    safe_directory(assembly)
    require(not is_link(assembly / "assembly-manifest.json"), "assembly manifest must not be a symlink")
    info = read_json(assembly / "assembly-manifest.json")
    platform = info.get("platform")
    require(platform in PLATFORMS, "invalid assembly platform")
    links = {"root/" + name: target for name, target in LINUX_ENTRY_POINTS.items()} if platform == "linux" else {}
    verify_inventory(assembly, info.get("inventory"), links=links, exclude=("assembly-manifest.json",))
    lock, checksum, _ = read_components_lock(assembly / "components.lock.json")
    verify_provenance(info, lock, checksum, info.get("source_commit"), allow_dirty=True)
    payload = assembly / ("payload" if platform == "windows" else "root")
    verify_inventory(payload, info.get("payload"), links=LINUX_ENTRY_POINTS if platform == "linux" else {})
    for name in REQUIRED[platform]:
        require((payload / name).is_file(), f"assembled payload lacks {name}")
    stage_inputs = [dict(record, path=record["path"].removeprefix("build-inputs/"))
                    for record in info["stages"]["wezterm"]["files"] if record["path"].startswith("build-inputs/")]
    stage_inputs += [dict(record, path="ohmyzsh/" + record["path"])
                     for record in info["stages"]["ohmyzsh"]["build_inputs"]]
    verify_inventory(assembly / "build-inputs", stage_inputs)
    verify_inventory(assembly / "redistribution", info["stages"]["ohmyzsh"]["redistribution"])
    return info


def assemble(platform: str, wezterm_stage: Path, ohmyzsh_stage: Path, output: Path, *,
             version: str, sha: str, dirty: bool, epoch: int, allow_dirty: bool = False,
             components_lock: Path | None = None) -> dict:
    require(platform in PLATFORMS, "unsupported platform")
    require(allow_dirty or not dirty, "official packages require a clean coordinator checkout; use --allow-dirty for local builds")
    require(not output.exists() and not output.is_symlink(), f"assembly output already exists: {output}")
    lock, checksum, raw_lock = read_components_lock(components_lock)
    wezterm = check_wezterm_stage(wezterm_stage, platform, lock["components"]["wezterm"]["revision"], allow_dirty)
    ohmyzsh = check_ohmyzsh_stage(ohmyzsh_stage, platform, lock["components"]["ohmyzsh"]["revision"], allow_dirty,
                                 herdr_sha=lock["components"]["herdr"]["revision"])
    output.parent.mkdir(parents=True, exist_ok=True)
    safe_directory(output.parent)
    with tempfile.TemporaryDirectory(prefix=".gx-shell-assembly-", dir=output.parent) as temporary:
        work = Path(temporary) / "assembly"
        work.mkdir()
        if platform == "windows":
            payload = work / "payload"
            copy_tree(ohmyzsh_stage / "payload", payload, skip=("fonts",))
            copy_tree(wezterm_stage / "app", payload / "wezterm")
            fonts = merge_fonts([ohmyzsh_stage / "payload/fonts", wezterm_stage / "fonts"], payload / "fonts")
            install_documents(payload, platform)
            depends = None
        else:
            payload = work / "root"
            copy_tree(ohmyzsh_stage / "payload", payload, skip=("DEBIAN", *LINUX_COMPONENT_FONT_DIRS))
            copy_tree(wezterm_stage / "root", payload, skip=("DEBIAN", *LINUX_COMPONENT_FONT_DIRS))
            fonts = merge_fonts([ohmyzsh_stage / "payload" / LINUX_COMPONENT_FONT_DIRS[0],
                                 wezterm_stage / "root" / LINUX_COMPONENT_FONT_DIRS[1]], payload / LINUX_FONT_DIR)
            install_documents(payload, platform)
            links = {path.relative_to(payload).as_posix(): os.readlink(path)
                     for path in payload.rglob("*") if path.is_symlink()}
            require(links == LINUX_ENTRY_POINTS, f"unexpected payload symlinks: {sorted(links)}")
            normalize_modes(payload)
            depends = merge_depends(wezterm["deb_depends"], control_depends(ohmyzsh_stage))
        copy_tree(ohmyzsh_stage / "redistribution", work / "redistribution")
        copy_tree(wezterm_stage / "build-inputs", work / "build-inputs")
        copy_tree(ohmyzsh_stage / "build-inputs", work / "build-inputs/ohmyzsh")
        (work / "components.lock.json").write_bytes(raw_lock)
        manifest = {
            "schema": 2, "product": PRODUCT, "version": version, "platform": platform,
            "architecture": PLATFORMS[platform]["arch"], "source_commit": sha, "source_dirty": dirty,
            "coordinator": {"repository": "gx0404/gx_shell", "revision": sha, "dirty": dirty},
            "source_date_epoch": epoch, "publishable": not (dirty or allow_dirty), "local_build": bool(allow_dirty),
            "components_lock": lock, "components_lock_digest": checksum,
            "components": component_metadata(lock, wezterm, ohmyzsh),
            "stages": {"wezterm": wezterm, "ohmyzsh": ohmyzsh},
            "fonts": fonts, "payload": inventory(payload, links=LINUX_ENTRY_POINTS if platform == "linux" else {},
                                                   executable=True),
            "inventory": inventory(work, links={"root/" + name: target for name, target in LINUX_ENTRY_POINTS.items()}
                                   if platform == "linux" else {}, executable=True),
        }
        if depends is not None:
            manifest["deb_depends"] = depends
        write_json(work / "assembly-manifest.json", manifest)
        check_assembly(work)
        work.rename(output)
    return manifest


def tool(name: str, explicit: str | None) -> str:
    if explicit:
        require(Path(explicit).is_file(), f"{name} not found: {explicit}")
        return explicit
    if name == "iscc" and os.environ.get("ISCC"):
        return tool(name, os.environ["ISCC"])
    found = shutil.which(name)
    if found:
        return found
    if name == "iscc":
        for env in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
            base = Path(os.environ.get(env, "C:/Program Files (x86)"))
            for candidate in (base / "Inno Setup 7/ISCC.exe", base / "Programs/Inno Setup 7/ISCC.exe"):
                if candidate.is_file():
                    return str(candidate)
    raise PackageError(f"required tool not found: {name}")


def run(argv: list, env: dict | None = None) -> None:
    subprocess.run([str(item) for item in argv], check=True, env=env)


def source_archive(source: Path, destination: Path, epoch: int) -> None:
    with tarfile.open(destination, "w:xz", format=tarfile.PAX_FORMAT) as archive:
        for path in sorted(source.rglob("*"), key=lambda item: item.relative_to(source).as_posix()):
            require(not path.is_symlink(), f"source archive must not contain symlinks: {path}")
            if not path.is_file():
                continue
            info = archive.gettarinfo(str(path), path.relative_to(source).as_posix())
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            info.mtime = epoch
            info.mode = 0o755 if path.stat().st_mode & 0o111 else 0o644
            with path.open("rb") as stream:
                archive.addfile(info, stream)


def artifact_names(version: str, platform: str, *, local: bool = False) -> tuple[str, str]:
    # Development builds carry "-local" in their file names so that they cannot pass for release files.
    tag = f"{version}-local" if local else version
    if platform == "windows":
        return f"GX-Shell-{tag}-Setup-x64.exe", f"{PRODUCT}_{tag}_windows-x64-sources.tar.xz"
    return f"{PRODUCT}_{tag}_amd64.deb", f"{PRODUCT}_{tag}_amd64-sources.tar.xz"


def render_control(version: str, installed_size: int, depends: str) -> str:
    text = (ROOT / "packaging/debian/control.in").read_text(encoding="utf-8")
    for key, value in (("@VERSION@", version), ("@INSTALLED_SIZE@", str(installed_size)), ("@DEPENDS@", depends)):
        text = text.replace(key, value)
    require(re.search(r"@[A-Z_]+@", text) is None, "unrendered placeholder in control.in")
    return text


def build(assembly: Path, output: Path, *, iscc: str | None = None, dpkg_deb: str | None = None) -> dict:
    manifest = check_assembly(assembly)
    platform, version = manifest["platform"], manifest["version"]
    require(isinstance(version, str) and re.fullmatch(r"\d+\.\d+\.\d+", version), "invalid package version")
    name, sources = artifact_names(version, platform, local=manifest["publishable"] is not True)
    require(not output.absolute().is_relative_to(assembly.absolute()), "build output must be outside the assembly")
    output.mkdir(parents=True, exist_ok=True)
    safe_directory(output)
    artifact = output / name
    for item in (name, sources, f"{name}.manifest.json", f"{name}.sha256"):
        require(not (output / item).exists() and not (output / item).is_symlink(), f"artifact already exists: {item}")
    if platform == "windows":
        run([tool("iscc", iscc), "/Qp", f"/DGxVersion={version}", f"/DGxPayload={(assembly / 'payload').resolve()}",
             f"/DGxOutput={output.resolve()}", f"/DGxFilename={artifact.stem}",
             f"/DGxIcon={(assembly / 'build-inputs/terminal.ico').resolve()}", ROOT / "packaging/windows/gx-shell.iss"])
    else:
        root = assembly / "root"
        control = root / "DEBIAN"
        require(not control.exists(), "assembly already contains DEBIAN/")
        size = (sum(p.stat().st_size for p in root.rglob("*") if p.is_file() and not p.is_symlink()) + 1023) // 1024
        control.mkdir(mode=0o755)
        try:
            (control / "control").write_text(render_control(version, size, manifest["deb_depends"]),
                                             encoding="utf-8", newline="\n")
            for script in MAINTAINER_SCRIPTS:
                (control / script).write_bytes((ROOT / "packaging/debian" / script).read_bytes().replace(b"\r\n", b"\n"))
                (control / script).chmod(0o755)
            run([tool("dpkg-deb", dpkg_deb), "--root-owner-group", "-Zxz", "--build", root, artifact],
                env={**os.environ, "SOURCE_DATE_EPOCH": str(manifest["source_date_epoch"])})
        finally:
            shutil.rmtree(control, ignore_errors=True)
        fields = subprocess.run([tool("dpkg-deb", dpkg_deb), "--field", str(artifact), "Package", "Version", "Architecture"],
                                check=True, capture_output=True, text=True).stdout.split("\n")
        require(fields[:3] == [f"Package: {PRODUCT}", f"Version: {version}", "Architecture: amd64"],
                f"unexpected deb fields: {fields[:3]}")
    require(artifact.is_file() and not is_link(artifact) and artifact.stat().st_size > 0,
            f"packager did not produce a regular artifact: {artifact}")
    require(check_assembly(assembly) == manifest, "assembly changed during the build")
    source_archive(assembly / "redistribution", output / sources, manifest["source_date_epoch"])
    return finish_artifacts(output, manifest, name, sources)


def finish_artifacts(output: Path, manifest: dict, name: str, sources: str) -> dict:
    result = {key: value for key, value in manifest.items() if key != "payload"}
    result["payload_files"] = len(manifest["payload"])
    result["artifacts"] = {item: {"sha256": digest(output / item), "size": (output / item).stat().st_size}
                           for item in (name, sources)}
    metadata = output / f"{name}.manifest.json"
    write_json(metadata, result)
    (output / f"{name}.sha256").write_text(
        "".join(f"{digest(output / item)}  {item}\n" for item in (name, sources, metadata.name)), encoding="ascii", newline="\n")
    return result


def verify(folder: Path, version: str, sha: str, *, allow_dirty: bool = False,
           components_lock: Path | None = None) -> list[str]:
    lock, checksum, _ = read_components_lock(components_lock)
    safe_directory(folder)
    require(re.fullmatch(r"\d+\.\d+\.\d+", version) is not None, "invalid package version")
    files = []
    provenance = None
    for platform in PLATFORMS:
        name, sources = artifact_names(version, platform)
        if allow_dirty and not (folder / f"{name}.manifest.json").exists():
            name, sources = artifact_names(version, platform, local=True)
        metadata = folder / f"{name}.manifest.json"
        info = read_json(metadata)
        require(not is_link(metadata), "release metadata must not be a symlink")
        for key, value in (("product", PRODUCT), ("version", version), ("platform", platform), ("source_commit", sha)):
            require(info.get(key) == value, f"{name}: manifest {key} differs from the expected release")
        require(allow_dirty or info.get("publishable") is True, f"{name}: development build cannot be released")
        verify_provenance(info, lock, checksum, sha, allow_dirty=allow_dirty)
        require((name, sources) == artifact_names(version, platform, local=not info["publishable"]),
                "development build requires -local artifact names")
        current = (info["coordinator"], info["components_lock_digest"], info["components_lock"],
                   info["components"]["herdr"]["source_sha256"], info["publishable"], info["local_build"])
        require(provenance is None or provenance == current, "platforms have different four-repository provenance")
        provenance = current
        require(isinstance(info.get("artifacts"), dict) and set(info["artifacts"]) == {name, sources},
                "release manifest has missing or extra artifacts")
        for item in (name, sources):
            path = folder / item
            require(path.is_file() and not is_link(path) and path.stat().st_size > 0, f"missing release file: {item}")
            record = info["artifacts"][item]
            require(isinstance(record, dict) and record.get("sha256") == digest(path),
                    f"{item}: SHA-256 differs from its manifest")
            require(type(record.get("size")) is int and record["size"] == path.stat().st_size,
                    f"{item}: size differs from its manifest")
        expected = {item: digest(folder / item) for item in (name, sources, metadata.name)}
        sidecar = folder / f"{name}.sha256"
        require(sidecar.is_file() and not is_link(sidecar), "missing regular SHA-256 sidecar")
        lines = sidecar.read_text(encoding="ascii").splitlines()
        require(sorted(lines) == sorted(f"{value}  {key}" for key, value in expected.items()), f"{name}.sha256 is stale")
        files += [name, sources, metadata.name]
    sums = folder / "SHA256SUMS"
    require(not sums.is_symlink() and (not sums.exists() or not is_link(sums)), "SHA256SUMS must not be a symlink")
    sums.write_text("".join(f"{digest(folder / item)}  {item}\n" for item in sorted(files)), encoding="ascii", newline="\n")
    return files


def release_notes(version: str, root: Path = ROOT) -> str:
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(rf"^## {re.escape(version)}\((?:TBD|\d{{8}}|\d{{4}}-\d{{2}}-\d{{2}})\)\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    require(match is not None and bool(match.group(1).strip()), f"CHANGELOG.md has no entries for {version}")
    windows, windows_sources = artifact_names(version, "windows")
    deb, deb_sources = artifact_names(version, "linux")
    return (f"{match.group(1).strip()}\n\n"
            "## 安装\n\n"
            f"- Windows 10 1809+ x64：运行 `{windows}`（按用户安装，无需管理员；安装包未签名，"
            "SmartScreen 提示时选择“仍要运行”）。会先卸载单独安装的旧版 WezTerm GX / Oh My Zsh GX / Herdr GX。\n"
            f"- Ubuntu 20.04 / 24.04 amd64：`sudo apt install ./{deb}`（自动替换旧的 wezterm-gx、ohmyzsh-gx、herdr-gx 包）。\n\n"
            f"`SHA256SUMS` 校验全部文件；`{windows_sources}`、`{deb_sources}` 为再分发组件的对应源码。\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    step = commands.add_parser("assemble", help="merge the component stages into one payload")
    step.add_argument("--platform", choices=tuple(PLATFORMS), required=True)
    step.add_argument("--wezterm-stage", type=Path, required=True)
    step.add_argument("--ohmyzsh-stage", type=Path, required=True)
    step.add_argument("--components-lock", type=Path, default=ROOT / "components.lock.json",
                      help="validated local source lock; no checkout or remote branch lookup")
    step.add_argument("--output", type=Path, required=True)
    step.add_argument("--version", help="X.Y.Z or gx-shell-vX.Y.Z; must match CHANGELOG.md")
    step.add_argument("--allow-dirty", action="store_true", help="local development builds only; never publishable")
    step = commands.add_parser("build", help="build the installer, sources archive and sidecars")
    step.add_argument("--assembly", type=Path, required=True)
    step.add_argument("--output", type=Path, required=True)
    step.add_argument("--iscc")
    step.add_argument("--dpkg-deb")
    step = commands.add_parser("verify", help="check both platforms before publishing and write SHA256SUMS")
    step.add_argument("--dir", type=Path, required=True)
    step.add_argument("--components-lock", type=Path, default=ROOT / "components.lock.json",
                      help="same exact source lock used by both builds; checked offline")
    step.add_argument("--version")
    step.add_argument("--sha", help="coordinator commit (defaults to root HEAD, not a component revision)")
    step.add_argument("--allow-dirty", action="store_true")
    step = commands.add_parser("version", help="print the release version from CHANGELOG.md")
    step.add_argument("--release", action="store_true", help="fail while that version is still dated (TBD)")
    step = commands.add_parser("notes", help="print the GitHub Release notes for a version")
    step.add_argument("--version")
    args = parser.parse_args(argv)
    try:
        if args.command == "version":
            print(version_from_changelog(ROOT, release=args.release))
        elif args.command == "notes":
            print(release_notes(validate_version(args.version)), end="")
        elif args.command == "assemble":
            version = validate_version(args.version)
            sha, dirty, epoch = source_info()
            manifest = assemble(args.platform, args.wezterm_stage.absolute(), args.ohmyzsh_stage.absolute(),
                                args.output.absolute(), version=version, sha=sha, dirty=dirty, epoch=epoch,
                                allow_dirty=args.allow_dirty, components_lock=args.components_lock)
            print(f"ASSEMBLED {args.output} ({manifest['platform']}, {len(manifest['payload'])} files, GX Shell {version})")
        elif args.command == "build":
            result = build(args.assembly.absolute(), args.output.absolute(), iscc=args.iscc, dpkg_deb=args.dpkg_deb)
            for name, item in result["artifacts"].items():
                print(f"BUILT {name} {item['sha256']}")
        else:
            version = validate_version(args.version)
            sha = args.sha or git("rev-parse", "HEAD")
            files = verify(args.dir.absolute(), version, sha, allow_dirty=args.allow_dirty,
                           components_lock=args.components_lock)
            print(f"VERIFIED {len(files)} release files for GX Shell {version} ({sha})")
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print(f"gx-shell-package: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""GX Shell assembly contract checks on synthetic component stages; no compiler or installer needed."""
import contextlib
import io
import json
import os
import re
import shutil
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import gx_shell_package as package
import gx_shell_sources as sources

SHA = "a" * 40
HERDR_SHA, OMZ_SHA, GHOSTTY_SHA = "b" * 40, "c" * 40, "d" * 40
GHOSTTY_DEPENDS = "libc6 (>= 2.39), libgtk-4-1 (>= 4.14.0), libadwaita-1-0 (>= 1.5~beta)"
SYMLINKS = os.name != "nt"
REPOSITORY_ROOT = package.ROOT


def write(path: Path, data: bytes = b"fixture", executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if executable:
        path.chmod(0o755)


def cleanup_temp(directory: tempfile.TemporaryDirectory) -> None:
    for attempt in range(30):
        try:
            directory.cleanup()
            return
        except OSError as error:
            if os.name != "nt" or getattr(error, "winerror", None) not in (32, 145) or attempt == 29:
                raise
            time.sleep(0.1)


def write_lock(root: Path) -> Path:
    lock = {"schema": 1, "components": {
        name: {"repository": f"gx0404/{name}", "branch": sources.COMPONENT_BRANCHES[name], "revision": revision}
        for name, revision in (("herdr", HERDR_SHA), ("ohmyzsh", OMZ_SHA), ("gx_ghostty", GHOSTTY_SHA))},
        "toolchains": {"fixture": "independent-repositories"}}
    path = root / "components.lock.json"
    write(path, json.dumps(lock, indent=4).encode() + b"\n")
    return path


def fixture_inventory(root: Path, exclude: str = "", executable: bool = False) -> list[dict]:
    records = []
    for path in sorted(root.rglob("*")):
        name = path.relative_to(root).as_posix()
        if name == exclude or path.is_dir():
            continue
        if path.is_symlink():
            records.append({"path": name, "symlink": os.readlink(path)})
        else:
            item = {"path": name, "sha256": package.digest(path), "size": path.stat().st_size}
            if executable:
                item["executable"] = bool(path.stat().st_mode & 0o111)
            records.append(item)
    return records


def refresh_stage(stage: Path, component: str) -> None:
    name = "stage-manifest.json" if component == package.GHOSTTY else "package-manifest.json"
    info = package.read_json(stage / name)
    if component == package.GHOSTTY:
        info["files"] = fixture_inventory(stage, name)
    else:
        for field, directory in (("payload", "payload"), ("redistribution", "redistribution"), ("build_inputs", "build-inputs")):
            info[field] = fixture_inventory(stage / directory, executable=field == "payload")
    package.write_json(stage / name, info)


def ghostty_stage(root: Path, target: str, **overrides) -> Path:
    """A schema 3 stage laid out like gx0404/gx_ghostty scripts/gx_package.py writes it."""
    stage = root / f"ghostty-{target}"
    info = {"schema": 3, "platform": package.PLATFORMS[target][package.GHOSTTY], "architecture": "amd64",
            "source_repository": "gx0404/gx_ghostty", "source_commit": GHOSTTY_SHA, "source_dirty": False,
            "package_version": "0.1.0", "product_version": "1.3.2-gx.0.1.0", "zig_version": "0.16.0"}
    if target == "windows":
        binary = stage / "app/ghostty.exe"
        write(binary, b"MZ ghostty")
        for name in ("conpty.dll", "OpenConsole.exe", "mesa/opengl32.dll", "mesa/libgallium_wgl.dll", "mesa/dxil.dll"):
            write(stage / "app" / name, b"MZ " + name.encode())
        write(stage / "app/share/terminfo/ghostty.terminfo", b"xterm-ghostty|ghostty,\n")
        write(stage / "app/share/ghostty/themes/Builtin Dark", b"background = #000000\n")
        write(stage / "app/licenses/Ghostty-MIT.txt", b"MIT License\n")
        write(stage / "app/README.txt", b"Ghostty GX\r\n")
        write(stage / "build-inputs/ghostty.ico", b"fixture-stage-icon")
        info["binaries"] = {"ghostty.exe": package.digest(binary)}
    else:
        binary = stage / "root/usr/lib/ghostty-gx/bin/ghostty"
        write(binary, b"\x7fELF ghostty", executable=True)
        write(stage / "root/usr/lib/ghostty-gx/share/terminfo/g/ghostty", b"compiled terminfo")
        write(stage / "root/usr/lib/ghostty-gx/share/ghostty/themes/Builtin Dark", b"background = #000000\n")
        write(stage / "root/usr/share/applications/com.gx0404.ghostty-gx.desktop", b"[Desktop Entry]\n")
        write(stage / "root/usr/share/icons/hicolor/16x16/apps/com.gx0404.ghostty-gx.png", b"png")
        write(stage / "root/usr/share/doc/ghostty-gx/copyright", b"MIT License\n")
        (stage / "root/usr/bin").mkdir(parents=True)
        os.symlink("../lib/ghostty-gx/bin/ghostty", stage / "root/usr/bin/ghostty-gx")
        info["binaries"] = {"ghostty": package.digest(binary)}
        info["deb_depends"] = GHOSTTY_DEPENDS
    write(stage / "fonts/JetBrainsMono.ttf", b"shared font")
    write(stage / "fonts/NotoSansCJK.ttc", b"cjk font")
    info["files"] = fixture_inventory(stage)
    info.update(overrides)
    package.write_json(stage / "stage-manifest.json", info)
    return stage


def ohmyzsh_stage(root: Path, platform: str, font: bytes = b"shared font", **overrides) -> Path:
    stage = root / f"ohmyzsh-{platform}"
    identity = package.PLATFORMS[platform]["herdr"]
    info = {"schema_version": 1, "platform": package.PLATFORMS[platform]["ohmyzsh"], "version": "0.2.0",
            "source": {"repository": "gx0404/ohmyzsh", "revision": OMZ_SHA, "dirty": False}, "publishable": True,
            "compliance_complete": True, "lock_digest": "d" * 64,
            "herdr": {"repository": "https://github.com/gx0404/herdr", "revision": HERDR_SHA, "version": "0.9.1"},
            "herdr_build": {"repository": "https://github.com/gx0404/herdr", "revision": HERDR_SHA, "version": "0.9.1",
                            "package_manager": identity, "target": "fixture", "source_sha256": "e" * 64,
                            "builder": "github-actions"},
            "zsh_build": {"version": "5.9.2+gx-metafied-paths"}}
    payload = stage / "payload"
    if platform == "windows":
        for name in ("bin/gx-zsh.exe", "bin/herdr.exe", "lib/herdr/herdr.exe", "lib/herdr/conpty/conpty.dll",
                     "runtime/msys64/usr/bin/zsh.exe", "share/ohmyzsh-gx/oh-my-zsh.sh", "share/" + package.HERDR_COMPLETION):
            write(payload / name)
        write(payload / "licenses/ohmyzsh-LICENSE.txt", b"MIT License\n")
        write(payload / "fonts/JetBrainsMono.ttf", font)
    else:
        for name in ("usr/lib/ohmyzsh-gx/bin/gx-zsh", "usr/lib/ohmyzsh-gx/bin/herdr",
                     "usr/lib/ohmyzsh-gx/lib/herdr/herdr", "usr/lib/ohmyzsh-gx/libexec/zsh/zsh"):
            write(payload / name, b"\x7fELF", executable=True)
        write(payload / "usr/lib/ohmyzsh-gx/share/licenses/zsh/LICENCE", b"Zsh licence\n")
        write(payload / "usr/share/doc/ohmyzsh-gx/licenses/ohmyzsh-LICENSE.txt", b"MIT License\n")
        write(payload / "usr/share/ohmyzsh-gx/oh-my-zsh.sh")
        write(payload / "usr/share" / package.HERDR_COMPLETION, b"#compdef herdr\n")
        write(payload / "usr/share/fonts/truetype/ohmyzsh-gx/JetBrainsMono.ttf", font)
        write(payload / "DEBIAN/control", b"Package: ohmyzsh-gx\nDepends: libc6 (>= 2.29), git, fontconfig\n")
        (payload / "usr/bin").mkdir(parents=True)
        for name in ("gx-zsh", "herdr"):
            os.symlink(f"../lib/ohmyzsh-gx/bin/{name}", payload / "usr/bin" / name)
    write(stage / "redistribution/dependencies/zsh/SOURCE.txt", b"corresponding source")
    source = stage / "redistribution/dependencies/herdr/redistribution/herdr-source.zip"
    write(source, b"fixture herdr corresponding source")
    info["herdr_build"]["source_sha256"] = package.digest(source)
    info["herdr_build"]["source_artifacts"] = [{"path": "redistribution/herdr-source.zip",
                                                 "sha256": package.digest(source), "size": source.stat().st_size}]
    prefix = "lib/herdr" if platform == "windows" else "usr/lib/ohmyzsh-gx/lib/herdr"
    info["herdr_build"]["files"] = fixture_inventory(payload / prefix)
    write(stage / "redistribution/ohmyzsh-gx/CHANGELOG.md", b"## 0.2.0(TBD)\n")
    write(stage / "build-inputs/windows.iss", b"; fixture component installer input\n")
    for field, directory in (("payload", "payload"), ("redistribution", "redistribution"), ("build_inputs", "build-inputs")):
        info[field] = fixture_inventory(stage / directory, executable=field == "payload")
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(info.get(key), dict):
            info[key].update(value)
        else:
            info[key] = value
    package.write_json(stage / "package-manifest.json", info)
    return stage


class CleanupTempTests(unittest.TestCase):
    def test_success_does_not_retry_or_sleep(self):
        for os_name in ("nt", "posix"):
            with self.subTest(os_name=os_name):
                directory = mock.Mock(spec=tempfile.TemporaryDirectory)
                with mock.patch.object(os, "name", os_name), mock.patch.object(time, "sleep") as sleep:
                    self.assertIsNone(cleanup_temp(directory))
                directory.cleanup.assert_called_once_with()
                sleep.assert_not_called()

    def test_transient_windows_errors_are_retried(self):
        for winerror in (32, 145):
            with self.subTest(winerror=winerror):
                error = OSError("temporary cleanup failure")
                error.winerror = winerror
                directory = mock.Mock(spec=tempfile.TemporaryDirectory)
                directory.cleanup.side_effect = [error, error, None]
                with mock.patch.object(os, "name", "nt"), mock.patch.object(time, "sleep") as sleep:
                    self.assertIsNone(cleanup_temp(directory))
                self.assertEqual(directory.cleanup.call_args_list, [mock.call()] * 3)
                self.assertEqual(sleep.call_args_list, [mock.call(0.1)] * 2)

    def test_persistent_windows_errors_raise_after_the_retry_limit(self):
        for winerror in (32, 145):
            with self.subTest(winerror=winerror):
                error = OSError("persistent cleanup failure")
                error.winerror = winerror
                directory = mock.Mock(spec=tempfile.TemporaryDirectory)
                directory.cleanup.side_effect = error
                with mock.patch.object(os, "name", "nt"), mock.patch.object(time, "sleep") as sleep:
                    with self.assertRaises(OSError) as raised:
                        cleanup_temp(directory)
                self.assertIs(raised.exception, error)
                self.assertEqual(directory.cleanup.call_args_list, [mock.call()] * 30)
                self.assertEqual(sleep.call_args_list, [mock.call(0.1)] * 29)

    def test_non_windows_errors_are_not_retried(self):
        for winerror in (32, 145):
            with self.subTest(winerror=winerror):
                error = OSError("cleanup failure outside Windows")
                error.winerror = winerror
                directory = mock.Mock(spec=tempfile.TemporaryDirectory)
                directory.cleanup.side_effect = error
                with mock.patch.object(os, "name", "posix"), mock.patch.object(time, "sleep") as sleep:
                    with self.assertRaises(OSError) as raised:
                        cleanup_temp(directory)
                self.assertIs(raised.exception, error)
                directory.cleanup.assert_called_once_with()
                sleep.assert_not_called()

    def test_other_errors_are_not_retried(self):
        denied = PermissionError("access denied")
        denied.winerror = 5
        for os_name in ("nt", "posix"):
            for error in (denied, OSError("no winerror"), RuntimeError("unexpected failure")):
                with self.subTest(os_name=os_name, error=error):
                    directory = mock.Mock(spec=tempfile.TemporaryDirectory)
                    directory.cleanup.side_effect = error
                    with mock.patch.object(os, "name", os_name), mock.patch.object(time, "sleep") as sleep:
                        with self.assertRaises(type(error)) as raised:
                            cleanup_temp(directory)
                    self.assertIs(raised.exception, error)
                    directory.cleanup.assert_called_once_with()
                    sleep.assert_not_called()

    def test_other_error_after_a_transient_failure_stops_retrying(self):
        for winerror in (32, 145):
            with self.subTest(winerror=winerror):
                transient = OSError("temporary cleanup failure")
                transient.winerror = winerror
                error = OSError("nonretryable cleanup failure")
                directory = mock.Mock(spec=tempfile.TemporaryDirectory)
                directory.cleanup.side_effect = [transient, error, None]
                with mock.patch.object(os, "name", "nt"), mock.patch.object(time, "sleep") as sleep:
                    with self.assertRaises(OSError) as raised:
                        cleanup_temp(directory)
                self.assertIs(raised.exception, error)
                self.assertEqual(directory.cleanup.call_args_list, [mock.call()] * 2)
                sleep.assert_called_once_with(0.1)


class AssemblyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gx-shell-unit-")
        self.addCleanup(cleanup_temp, self.temp)
        self.root = Path(self.temp.name)
        self.coordinator = self.root / "coordinator"
        self.lock = write_lock(self.coordinator)
        shutil.copytree(REPOSITORY_ROOT / "packaging", self.coordinator / "packaging")
        patcher = mock.patch.object(package, "ROOT", self.coordinator)
        patcher.start()
        self.addCleanup(patcher.stop)

    def assemble(self, platform, ghostty, ohmyzsh, **kwargs):
        options = {"version": "0.1.0", "sha": SHA, "dirty": False, "epoch": 1700000000,
                   "components_lock": self.lock}
        options.update(kwargs)
        return package.assemble(platform, ghostty, ohmyzsh, self.root / "out", **options)

    def test_version_is_the_numeric_maximum_and_accepts_the_release_tag(self):
        (self.root / "CHANGELOG.md").write_text("## 0.9.0(2026-01-01)\n## 0.10.0(TBD)\n", encoding="utf-8")
        self.assertEqual(package.validate_version(None, self.root), "0.10.0")
        self.assertEqual(package.validate_version("gx-shell-v0.10.0", self.root), "0.10.0")
        with self.assertRaisesRegex(package.PackageError, "CHANGELOG"):
            package.validate_version("0.9.0", self.root)

    def test_release_version_requires_the_highest_heading_to_be_dated(self):
        changelog = self.root / "CHANGELOG.md"
        changelog.write_text("## 0.9.0(2026-01-01)\n## 0.10.0(TBD)\n", encoding="utf-8")
        self.assertEqual(package.version_from_changelog(self.root), "0.10.0")
        with self.assertRaisesRegex(package.PackageError, r"0\.10\.0 as \(TBD\)"):
            package.version_from_changelog(self.root, release=True)
        for date in ("2026-09-29", "20260929"):
            with self.subTest(date=date):
                changelog.write_text(f"## 0.9.0(TBD)\n## 0.10.0({date})\n", encoding="utf-8")
                self.assertEqual(package.version_from_changelog(self.root, release=True), "0.10.0")

    def test_version_cli_release_flag_prints_the_version_or_fails_on_tbd(self):
        changelog = self.root / "CHANGELOG.md"
        changelog.write_text("## 0.1.0(TBD)\n", encoding="utf-8")
        stdout, stderr = io.StringIO(), io.StringIO()
        with (mock.patch.object(package, "ROOT", self.root), contextlib.redirect_stdout(stdout),
              contextlib.redirect_stderr(stderr)):
            self.assertEqual(package.main(["version"]), 0)
            self.assertEqual(package.main(["version", "--release"]), 1)
            changelog.write_text("## 0.1.0(2026-09-29)\n", encoding="utf-8")
            self.assertEqual(package.main(["version", "--release"]), 0)
        self.assertEqual(stdout.getvalue(), "0.1.0\n0.1.0\n")
        self.assertIn("0.1.0 as (TBD)", stderr.getvalue())

    def test_windows_layout_merges_components_and_deduplicates_fonts(self):
        manifest = self.assemble("windows", ghostty_stage(self.root, "windows"), ohmyzsh_stage(self.root, "windows"))
        payload = self.root / "out/payload"
        for name in package.REQUIRED["windows"]:
            self.assertTrue((payload / name).is_file(), name)
        self.assertEqual(sorted(p.name for p in (payload / "fonts").iterdir()), ["JetBrainsMono.ttf", "NotoSansCJK.ttc"])
        self.assertFalse((payload / "ghostty/fonts").exists())
        self.assertEqual((payload / "ghostty/share/ghostty/themes/Builtin Dark").read_bytes(), b"background = #000000\n")
        self.assertTrue((self.root / "out/redistribution/dependencies/zsh/SOURCE.txt").is_file())
        self.assertTrue(manifest["publishable"])
        self.assertEqual(manifest["components"]["herdr"]["package_manager"], "windows-installer")
        self.assertEqual(package.read_json(self.root / "out/assembly-manifest.json")["source_commit"], SHA)
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith(".gx-shell-assembly-")], [])

    def test_same_font_name_with_different_content_is_rejected(self):
        with self.assertRaisesRegex(package.PackageError, "different fonts"):
            self.assemble("windows", ghostty_stage(self.root, "windows"),
                          ohmyzsh_stage(self.root, "windows", font=b"another build"))
        self.assertFalse((self.root / "out").exists())

    def test_stages_match_independent_locked_commits_and_herdr_identity(self):
        cases = (
            ({"source_commit": SHA}, {}, "different commit"),
            ({"source_repository": "gx0404/gx_shell"}, {}, "different repository"),
            ({"source_dirty": True}, {}, "dirty"),
            ({"schema": 2}, {}, "schema 3"),
            ({"schema": True}, {}, "schema 3"),
            ({"platform": "deb"}, {}, "schema 3 windows"),
            ({"architecture": "arm64"}, {}, "amd64 stage"),
            ({"package_version": "0.1"}, {}, "package or Zig version"),
            ({"zig_version": "0.16"}, {}, "package or Zig version"),
            ({"product_version": "1.3.2-gx.9.9.9"}, {}, "product version"),
            ({"product_version": "1.3.2"}, {}, "product version"),
            ({}, {"source": {"revision": SHA}}, "different commit"),
            ({}, {"source": {"repository": "gx0404/gx_shell"}}, "different repository"),
            ({}, {"publishable": False}, "development"),
            ({}, {"herdr_build": {"package_manager": None}}, "package identity"),
            ({}, {"herdr": {"revision": OMZ_SHA}}, "locked commit"),
            ({}, {"herdr_build": {"revision": OMZ_SHA}}, "locked commit"),
            ({}, {"herdr_build": {"repository": "gx0404/ohmyzsh"}}, "different repository"),
            ({}, {"herdr": {"repository": "gx0404/herdr"}}, "different repository"),
            ({}, {"herdr_build": {"repository": "gx0404/herdr"}}, "different repository"),
            ({}, {"herdr": {"repository": "gx0404/herdr"},
                  "herdr_build": {"repository": "gx0404/herdr"}}, "different repository"),
            ({}, {"herdr": {"repository": "https://github.com/other/herdr"},
                  "herdr_build": {"repository": "https://github.com/other/herdr"}}, "different repository"),
            ({}, {"herdr_build": {"source_sha256": None}}, "source SHA-256"),
            ({}, {"herdr_build": {"builder": "local"}}, "not built on GitHub Actions"),
            ({}, {"herdr_build": {"builder": None}}, "not built on GitHub Actions"),
            ({}, {"herdr_build": {"builder": "self-hosted"}}, "not built on GitHub Actions"),
        )
        for index, (ghostty_change, ohmyzsh_change, message) in enumerate(cases):
            with self.subTest(message=message):
                root = self.root / str(index)
                root.mkdir()
                ghostty = ghostty_stage(root, "windows", **ghostty_change)
                ohmyzsh = ohmyzsh_stage(root, "windows", **ohmyzsh_change)
                with self.assertRaisesRegex(package.PackageError, message):
                    package.assemble("windows", ghostty, ohmyzsh, root / "out", version="0.1.0", sha=SHA,
                                     dirty=False, epoch=0)

    def test_dirty_checkout_requires_explicit_development_mode(self):
        ghostty, ohmyzsh = ghostty_stage(self.root, "windows"), ohmyzsh_stage(self.root, "windows")
        with self.assertRaisesRegex(package.PackageError, "clean coordinator"):
            self.assemble("windows", ghostty, ohmyzsh, dirty=True)
        manifest = self.assemble("windows", ghostty, ohmyzsh, dirty=True, allow_dirty=True)
        self.assertFalse(manifest["publishable"])

    def test_locally_built_herdr_needs_allow_dirty_and_is_never_publishable(self):
        build = {"builder": "local"}
        ghostty = ghostty_stage(self.root, "windows")
        ohmyzsh = ohmyzsh_stage(self.root, "windows", publishable=False, herdr_build=build)
        with self.assertRaisesRegex(package.PackageError, "not built on GitHub Actions .*--allow-dirty"):
            self.assemble("windows", ghostty, ohmyzsh)
        manifest = self.assemble("windows", ghostty, ohmyzsh, allow_dirty=True)
        self.assertFalse(manifest["publishable"])
        self.assertEqual(manifest["components"]["herdr"]["builder"], "local")

    def test_development_builds_get_local_artifact_names(self):
        calls = []

        def iscc(argv, env=None):
            calls.append(argv)
            options = dict(str(item)[2:].split("=", 1) for item in argv if str(item).startswith("/DGx"))
            write(Path(options["GxOutput"]) / f"{options['GxFilename']}.exe", b"MZ fixture installer")

        ghostty, ohmyzsh = ghostty_stage(self.root, "windows"), ohmyzsh_stage(self.root, "windows")
        for label, options, names in (
                ("release", {}, ["GX-Shell-0.1.0-Setup-x64.exe", "gx-shell_0.1.0_windows-x64-sources.tar.xz"]),
                ("local", {"dirty": True, "allow_dirty": True},
                 ["GX-Shell-0.1.0-local-Setup-x64.exe", "gx-shell_0.1.0-local_windows-x64-sources.tar.xz"])):
            with self.subTest(label):
                assembly = self.root / f"assembly-{label}"
                package.assemble("windows", ghostty, ohmyzsh, assembly, version="0.1.0", sha=SHA, epoch=1700000000,
                                 **{"dirty": False, **options})
                with mock.patch.object(package, "run", side_effect=iscc), mock.patch.object(package, "tool", return_value="ISCC.exe"):
                    result = package.build(assembly, self.root / f"dist-{label}")
                self.assertEqual(sorted(result["artifacts"]), names)
                self.assertEqual(calls[-1][-1], package.ROOT / "packaging/windows/gx-shell.iss")
                self.assertEqual((self.root / f"dist-{label}" / f"{names[0]}.sha256").read_text(encoding="ascii").count("\n"), 3)
        self.assertEqual(package.artifact_names("0.1.0", "linux", local=True),
                         ("gx-shell_0.1.0-local_amd64.deb", "gx-shell_0.1.0-local_amd64-sources.tar.xz"))

    def test_two_components_cannot_provide_the_same_path(self):
        ohmyzsh = ohmyzsh_stage(self.root, "windows")
        write(ohmyzsh / "payload/ghostty/ghostty.exe", b"foreign")
        refresh_stage(ohmyzsh, "ohmyzsh")
        with self.assertRaisesRegex(package.PackageError, "same path: .*/payload/ghostty/ghostty.exe"):
            self.assemble("windows", ghostty_stage(self.root, "windows"), ohmyzsh)

    def test_windows_layout_adds_the_noto_license_without_overwriting_component_files(self):
        self.assemble("windows", ghostty_stage(self.root, "windows"), ohmyzsh_stage(self.root, "windows"))
        licenses = self.root / "out/payload/licenses"
        self.assertEqual(sorted(p.name for p in licenses.iterdir()), ["NotoSansCJK-OFL-1.1.txt", "ohmyzsh-LICENSE.txt"])
        text = (licenses / "NotoSansCJK-OFL-1.1.txt").read_bytes()
        self.assertEqual(text, (package.ROOT / "packaging/licenses/NotoSansCJK-OFL-1.1.txt").read_bytes())
        self.assertIn(b"SIL OPEN FONT LICENSE Version 1.1", text)
        root = self.root / "collision"
        ohmyzsh = ohmyzsh_stage(root, "windows")
        write(ohmyzsh / "payload/licenses/NotoSansCJK-OFL-1.1.txt", b"foreign")
        refresh_stage(ohmyzsh, "ohmyzsh")
        with self.assertRaisesRegex(package.PackageError, "already provides licenses/NotoSansCJK-OFL-1.1.txt"):
            package.assemble("windows", ghostty_stage(root, "windows"), ohmyzsh, root / "out", version="0.1.0",
                             sha=SHA, dirty=False, epoch=0)

    def test_ghostty_stage_binary_must_match_its_manifest_hash(self):
        for platform in ("windows", "linux") if SYMLINKS else ("windows",):
            with self.subTest(platform=platform):
                stage = ghostty_stage(self.root / platform, platform)
                binary = stage / ("app/ghostty.exe" if platform == "windows" else "root/usr/lib/ghostty-gx/bin/ghostty")
                info = package.check_ghostty_stage(stage, platform, GHOSTTY_SHA, False)
                self.assertEqual(info["binaries"][binary.name], package.digest(binary))
                binary.write_bytes(b"tampered")
                with self.assertRaisesRegex(package.PackageError, "inventory mismatch"):
                    package.check_ghostty_stage(stage, platform, GHOSTTY_SHA, False)
                refresh_stage(stage, package.GHOSTTY)
                with self.assertRaisesRegex(package.PackageError, "differs from its manifest"):
                    package.check_ghostty_stage(stage, platform, GHOSTTY_SHA, False)
                binary.unlink()
                # On Linux the missing binary also leaves usr/bin/ghostty-gx dangling, which is checked first.
                with self.assertRaisesRegex(package.PackageError, "inventory mismatch|dangling payload symlink"):
                    package.check_ghostty_stage(stage, platform, GHOSTTY_SHA, False)
                write(binary, b"restored")
                info["binaries"] = {"../escape": package.digest(binary)}
                package.write_json(stage / "stage-manifest.json", info)
                refresh_stage(stage, package.GHOSTTY)
                with self.assertRaisesRegex(package.PackageError, "exactly the ghostty"):
                    package.check_ghostty_stage(stage, platform, GHOSTTY_SHA, False)

    def test_ghostty_stage_manifest_fields_and_top_level_follow_the_schema_3_contract(self):
        cases = (
            ("extra field", lambda stage, info: info.update(resource_version="b" * 64), "missing or extra fields"),
            ("missing field", lambda stage, info: info.pop("zig_version"), "missing or extra fields"),
            ("windows deb_depends", lambda stage, info: info.update(deb_depends="libc6"), "missing or extra fields"),
            ("extra top level", lambda stage, info: write(stage / "notes/readme.txt"), "top-level"),
            ("missing build input", lambda stage, info: (stage / "build-inputs/ghostty.ico").unlink(), "lacks build-inputs"),
            ("missing mesa", lambda stage, info: (stage / "app/mesa/opengl32.dll").unlink(), "lacks app/mesa/opengl32.dll"),
            ("non-font file", lambda stage, info: write(stage / "fonts/readme.txt"), "only font files"),
        )
        for index, (label, change, message) in enumerate(cases):
            with self.subTest(case=label):
                stage = ghostty_stage(self.root / str(index), "windows")
                info = package.read_json(stage / "stage-manifest.json")
                change(stage, info)
                package.write_json(stage / "stage-manifest.json", info)
                refresh_stage(stage, package.GHOSTTY)
                with self.assertRaisesRegex(package.PackageError, message):
                    package.check_ghostty_stage(stage, "windows", GHOSTTY_SHA, False)

    @unittest.skipUnless(SYMLINKS, "deb stage fixtures need POSIX symlinks")
    def test_ghostty_deb_stage_needs_its_entry_point_and_dependencies(self):
        cases = (
            ("missing entry point", lambda stage, info: (stage / "root/usr/bin/ghostty-gx").unlink(), "entry point"),
            ("multiline depends", lambda stage, info: info.update(deb_depends="libc6\nlibgtk-4-1"), "dpkg-shlibdeps"),
            ("empty depends", lambda stage, info: info.update(deb_depends=" "), "dpkg-shlibdeps"),
            ("missing depends", lambda stage, info: info.pop("deb_depends"), "missing or extra fields"),
            ("missing desktop file", lambda stage, info: (stage / "root/usr/share/applications/com.gx0404.ghostty-gx.desktop").unlink(),
             "lacks root/usr/share/applications"),
        )
        for index, (label, change, message) in enumerate(cases):
            with self.subTest(case=label):
                stage = ghostty_stage(self.root / str(index), "linux")
                info = package.read_json(stage / "stage-manifest.json")
                change(stage, info)
                package.write_json(stage / "stage-manifest.json", info)
                refresh_stage(stage, package.GHOSTTY)
                with self.assertRaisesRegex(package.PackageError, message):
                    package.check_ghostty_stage(stage, "linux", GHOSTTY_SHA, False)

    @unittest.skipUnless(SYMLINKS, "deb payload fixtures need POSIX symlinks")
    def test_linux_layout_merges_depends_fonts_and_entry_points(self):
        manifest = self.assemble("linux", ghostty_stage(self.root, "linux"), ohmyzsh_stage(self.root, "linux"))
        root = self.root / "out/root"
        self.assertEqual(manifest["deb_depends"],
                         "fontconfig, git, libadwaita-1-0 (>= 1.5~beta), libc6 (>= 2.39), libgtk-4-1 (>= 4.14.0)")
        fonts = root / package.LINUX_FONT_DIR
        self.assertEqual(sorted(p.name for p in fonts.iterdir()), ["JetBrainsMono.ttf", "NotoSansCJK.ttc"])
        for directory in package.LINUX_COMPONENT_FONT_DIRS:
            self.assertFalse((root / directory).exists(), directory)
        self.assertFalse((root / "DEBIAN").exists())
        for link, target in package.LINUX_ENTRY_POINTS.items():
            self.assertEqual(os.readlink(root / link), target)
        self.assertEqual((root / "usr/lib/ghostty-gx/bin/ghostty").stat().st_mode & 0o777, 0o755)
        self.assertTrue((root / "usr/share/applications/com.gx0404.ghostty-gx.desktop").is_file())
        self.assertEqual((root / "usr/share/ohmyzsh-gx/oh-my-zsh.sh").stat().st_mode & 0o777, 0o644)
        self.assertTrue((root / "usr/share/doc/gx-shell/copyright").is_file())

    @unittest.skipUnless(SYMLINKS, "deb payload fixtures need POSIX symlinks")
    def test_linux_copyright_cites_only_installed_paths_including_the_noto_license(self):
        self.assemble("linux", ghostty_stage(self.root, "linux"), ohmyzsh_stage(self.root, "linux"))
        root = self.root / "out/root"
        noto = root / "usr/share/doc/gx-shell/NotoSansCJK-OFL-1.1.txt"
        self.assertEqual(noto.read_bytes(), (package.ROOT / "packaging/licenses/NotoSansCJK-OFL-1.1.txt").read_bytes())
        self.assertEqual(noto.stat().st_mode & 0o777, 0o644)
        cited = re.findall(r"(?<!\S)/\S+", (root / "usr/share/doc/gx-shell/copyright").read_text(encoding="utf-8"))
        self.assertIn("/usr/share/doc/gx-shell/NotoSansCJK-OFL-1.1.txt", cited)
        for path in cited:
            with self.subTest(path=path):
                target = root / path.lstrip("/")
                self.assertTrue(target.is_dir() if path.endswith("/") else target.is_file())

    @unittest.skipUnless(SYMLINKS, "deb payload fixtures need POSIX symlinks")
    def test_linux_payload_rejects_unexpected_symlinks(self):
        ghostty = ghostty_stage(self.root, "linux")
        os.symlink("/etc/passwd", ghostty / "root/usr/lib/ghostty-gx/share/escape")
        with self.assertRaisesRegex(package.PackageError, "unexpected payload symlinks"):
            self.assemble("linux", ghostty, ohmyzsh_stage(self.root, "linux"))

    @unittest.skipUnless(SYMLINKS and shutil.which("dpkg-deb"), "needs dpkg-deb and POSIX symlinks")
    def test_real_deb_build_carries_control_and_maintainer_scripts(self):
        self.assemble("linux", ghostty_stage(self.root, "linux"), ohmyzsh_stage(self.root, "linux"))
        result = package.build(self.root / "out", self.root / "dist")
        deb = self.root / "dist/gx-shell_0.1.0_amd64.deb"
        self.assertIn(deb.name, result["artifacts"])
        info = package.subprocess.run(["dpkg-deb", "--info", str(deb)], check=True, capture_output=True, text=True).stdout
        for text in ("Package: gx-shell", "Replaces: herdr-gx, ohmyzsh-gx\n", " preinst", " postinst", " postrm",
                     "Depends: fontconfig, git, libadwaita-1-0 (>= 1.5~beta), libc6 (>= 2.39), libgtk-4-1 (>= 4.14.0)\n",
                     "Recommends: librsvg2-common\n"):
            self.assertIn(text, info)
        self.assertNotIn("wezterm", info)
        self.assertFalse((self.root / "out/root/DEBIAN").exists())
        contents = package.subprocess.run(["dpkg-deb", "--contents", str(deb)], check=True, capture_output=True, text=True).stdout
        self.assertIn("./usr/bin/gx-zsh -> ../lib/ohmyzsh-gx/bin/gx-zsh", contents)
        self.assertIn("./usr/bin/ghostty-gx -> ../lib/ghostty-gx/bin/ghostty", contents)
        self.assertIn("root/root", contents)

    @unittest.skipUnless(SYMLINKS and shutil.which("dpkg-deb"), "needs dpkg-deb and POSIX symlinks")
    def test_real_deb_build_is_reproducible_from_the_manifest_epoch(self):
        self.assemble("linux", ghostty_stage(self.root, "linux"), ohmyzsh_stage(self.root, "linux"))
        package.build(self.root / "out", self.root / "one")
        for path in (self.root / "out/root").rglob("*"):
            os.utime(path, (1750000000, 1750000000), follow_symlinks=False)
        package.build(self.root / "out", self.root / "two")
        first, second = self.root / "one/gx-shell_0.1.0_amd64.deb", self.root / "two/gx-shell_0.1.0_amd64.deb"
        self.assertEqual(first.read_bytes(), second.read_bytes())
        data = package.subprocess.run(["dpkg-deb", "--fsys-tarfile", str(first)], check=True, capture_output=True).stdout
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            self.assertEqual({member.mtime for member in archive.getmembers()}, {1700000000})

    def test_control_template_renders_every_placeholder(self):
        text = package.render_control("1.2.3", 42, "libc6 (>= 2.29), zsh")
        self.assertIn("Version: 1.2.3\n", text)
        self.assertIn("Installed-Size: 42\n", text)
        self.assertIn("Depends: libc6 (>= 2.29), zsh\n", text)
        self.assertIn("Recommends: librsvg2-common\n", text)
        self.assertIn("Conflicts: herdr, herdr-gx, ohmyzsh-gx\n", text)
        self.assertIn("Replaces: herdr-gx, ohmyzsh-gx\n", text)
        self.assertNotIn("wezterm", text.lower())
        self.assertIn("Ghostty GX", text)

    def test_release_notes_use_the_changelog_section_and_list_the_assets(self):
        (self.root / "CHANGELOG.md").write_text("# log\n\n## 0.2.0(TBD)\n\n- newer\n\n## 0.1.0(2026-09-28)\n\n- first\n",
                                                encoding="utf-8")
        notes = package.release_notes("0.1.0", self.root)
        self.assertTrue(notes.startswith("- first\n"))
        self.assertNotIn("newer", notes)
        for name in ("GX-Shell-0.1.0-Setup-x64.exe", "gx-shell_0.1.0_amd64.deb", "SHA256SUMS",
                     "Ubuntu 24.04", "WezTerm GX 不受影响", "Oh My Zsh GX、Herdr GX 与 Ghostty GX",
                     "为所有用户安装的 Ghostty GX"):
            self.assertIn(name, notes)
        for stale in ("20.04", "wezterm-gx"):
            self.assertNotIn(stale, notes)
        with self.assertRaisesRegex(package.PackageError, "no entries for 0.3.0"):
            package.release_notes("0.3.0", self.root)

    def test_merge_depends_deduplicates_and_keeps_alternatives(self):
        self.assertEqual(package.merge_depends("b, a (>= 1)", " a (>= 1),  c | d ,"), "a (>= 1), b, c | d")

    def test_merge_depends_keeps_only_the_highest_plain_minimum_version(self):
        self.assertEqual(package.merge_depends("libc6 (>= 2.29), zsh", "libc6 (>= 2.30), libc6 (>= 2.4)"),
                         "libc6 (>= 2.30), zsh")
        self.assertEqual(package.merge_depends("a (>= 1.9)", "a (>=1.10)"), "a (>=1.10)")
        for depends in ("b (<< 2.0), b (>= 1.0), b (>= 1.5)", "c (>= 1:1.2), c (>= 1:1.3)", "d, d (>= 1.0), d (>= 2.0)",
                        "e (>= 1.0) | f, e (>= 1.1), e (>= 1.2)", "g (>= 1.2-3), g (>= 1.2-4)",
                        "h (>= 1.0), h (>= 1.1), h (>= 1:0.5)"):
            with self.subTest(depends=depends):
                self.assertEqual(package.merge_depends(depends), ", ".join(sorted(depends.split(", "))))

    def test_source_archive_is_reproducible(self):
        write(self.root / "src/b.txt", b"b")
        write(self.root / "src/a/c.sh", b"c", executable=True)
        first, second = self.root / "one.tar.xz", self.root / "two.tar.xz"
        package.source_archive(self.root / "src", first, 1700000000)
        package.source_archive(self.root / "src", second, 1700000000)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        with tarfile.open(first) as archive:
            members = archive.getmembers()
        self.assertEqual([m.name for m in members], ["a/c.sh", "b.txt"])
        self.assertEqual({m.mtime for m in members}, {1700000000})
        self.assertEqual({(m.uid, m.gid) for m in members}, {(0, 0)})

    def test_assembly_preserves_four_sources_raw_lock_and_stage_build_inputs_offline(self):
        ghostty, ohmyzsh = ghostty_stage(self.root, "windows"), ohmyzsh_stage(self.root, "windows")
        with mock.patch.object(package, "git", side_effect=AssertionError("offline assembly must not inspect Git")):
            manifest = self.assemble("windows", ghostty, ohmyzsh)
        self.assertEqual(manifest["schema"], 3)
        self.assertEqual(manifest["coordinator"]["revision"], SHA)
        self.assertEqual(manifest["components_lock"], package.read_json(self.lock))
        self.assertEqual(manifest["components_lock_digest"], package.digest(self.lock))
        self.assertEqual((self.root / "out/components.lock.json").read_bytes(), self.lock.read_bytes())
        for name, revision in (("herdr", HERDR_SHA), ("ohmyzsh", OMZ_SHA), ("gx_ghostty", GHOSTTY_SHA)):
            self.assertEqual(manifest["components"][name]["revision"], revision)
            self.assertEqual(manifest["components"][name]["repository"], f"gx0404/{name}")
            self.assertFalse((self.coordinator / name).exists())
        paths = {item["path"] for item in manifest["inventory"]}
        self.assertTrue({"components.lock.json", "build-inputs/ghostty.ico", "build-inputs/ohmyzsh/windows.iss"} <= paths)
        self.assertEqual((self.root / "out/build-inputs/ghostty.ico").read_bytes(), b"fixture-stage-icon")
        self.assertEqual(manifest["components"]["gx_ghostty"]["product_version"], "1.3.2-gx.0.1.0")
        self.assertEqual(manifest["components"]["gx_ghostty"]["zig_version"], "0.16.0")

    def test_full_stage_inventories_reject_missing_extra_and_changed_nonbinary_files(self):
        targets = (
            ("gx_ghostty", "app/share/terminfo/ghostty.terminfo"), ("gx_ghostty", "app/conpty.dll"),
            ("gx_ghostty", "app/share/ghostty/themes/Builtin Dark"),
            ("gx_ghostty", "fonts/JetBrainsMono.ttf"), ("gx_ghostty", "build-inputs/ghostty.ico"),
            ("ohmyzsh", "payload/share/ohmyzsh-gx/oh-my-zsh.sh"),
            ("ohmyzsh", "redistribution/dependencies/zsh/SOURCE.txt"),
            ("ohmyzsh", "build-inputs/windows.iss"))
        for index, (component, relative) in enumerate(targets):
            for change in ("missing", "extra", "changed"):
                with self.subTest(component=component, relative=relative, change=change):
                    root = self.root / f"{index}-{change}"
                    ghostty, ohmyzsh = ghostty_stage(root, "windows"), ohmyzsh_stage(root, "windows")
                    target = (ghostty if component == "gx_ghostty" else ohmyzsh) / relative
                    if change == "missing":
                        target.unlink()
                    elif change == "extra":
                        write(target.with_name("unlisted-file"))
                    else:
                        target.write_bytes(b"tampered")
                    with self.assertRaisesRegex(package.PackageError, "inventory mismatch"):
                        self.assemble("windows", ghostty, ohmyzsh)
                    self.assertFalse((self.root / "out").exists())

    def test_inventory_paths_duplicates_sizes_and_hashes_are_strict(self):
        invalid = ("../escape", "/absolute", "C:/escape", "app/../escape", "app//escape",
                   "app/./escape", "app\\escape", "app/escape.", "app/NUL", "")
        for component in ("gx_ghostty", "ohmyzsh"):
            for index, name in enumerate(invalid):
                with self.subTest(component=component, name=name):
                    root = self.root / f"{component}-{index}"
                    ghostty, ohmyzsh = ghostty_stage(root, "windows"), ohmyzsh_stage(root, "windows")
                    path = ghostty / "stage-manifest.json" if component == "gx_ghostty" else ohmyzsh / "package-manifest.json"
                    info = package.read_json(path)
                    field = "files" if component == "gx_ghostty" else "payload"
                    info[field][0]["path"] = name
                    package.write_json(path, info)
                    with self.assertRaises(package.PackageError):
                        self.assemble("windows", ghostty, ohmyzsh)
        for index, change in enumerate(("duplicate", "size", "sha256", "self", "empty")):
            root = self.root / f"record-{index}"
            ghostty, ohmyzsh = ghostty_stage(root, "windows"), ohmyzsh_stage(root, "windows")
            info = package.read_json(ghostty / "stage-manifest.json")
            if change == "duplicate":
                info["files"].append(dict(info["files"][0]))
            elif change == "self":
                info["files"][0]["path"] = "stage-manifest.json"
            elif change == "empty":
                info["files"] = []
            else:
                info["files"][0][change] = True
            package.write_json(ghostty / "stage-manifest.json", info)
            with self.subTest(change=change), self.assertRaises(package.PackageError):
                self.assemble("windows", ghostty, ohmyzsh)

    def test_required_build_inputs_and_herdr_source_cannot_be_removed_with_inventory(self):
        for index, relative in enumerate(("build-inputs/ghostty.ico",)):
            root = self.root / str(index)
            ghostty, ohmyzsh = ghostty_stage(root, "windows"), ohmyzsh_stage(root, "windows")
            (ghostty / relative).unlink()
            refresh_stage(ghostty, package.GHOSTTY)
            with self.assertRaisesRegex(package.PackageError, "lacks build-inputs"):
                self.assemble("windows", ghostty, ohmyzsh)
        root = self.root / "source"
        ghostty, ohmyzsh = ghostty_stage(root, "windows"), ohmyzsh_stage(root, "windows")
        (ohmyzsh / "redistribution/dependencies/herdr/redistribution/herdr-source.zip").unlink()
        refresh_stage(ohmyzsh, "ohmyzsh")
        with self.assertRaisesRegex(package.PackageError, "no corresponding redistribution file"):
            self.assemble("windows", ghostty, ohmyzsh)

    def test_build_rechecks_every_assembly_input_before_invoking_a_packager(self):
        self.assemble("windows", ghostty_stage(self.root, "windows"), ohmyzsh_stage(self.root, "windows"))
        assembly = self.root / "out"
        for name in ("payload/bin/gx-zsh.exe", "payload/ghostty/ghostty.exe", "payload/fonts/JetBrainsMono.ttf",
                     "build-inputs/ghostty.ico", "build-inputs/ohmyzsh/windows.iss",
                     "redistribution/dependencies/zsh/SOURCE.txt", "components.lock.json"):
            path = assembly / name
            before = path.read_bytes()
            path.write_bytes(before + b"tampered")
            with self.subTest(name=name), mock.patch.object(package, "run") as run:
                with self.assertRaisesRegex(package.PackageError, "inventory mismatch"):
                    package.build(assembly, self.root / "dist")
                run.assert_not_called()
            path.write_bytes(before)
        write(assembly / "payload/unlisted")
        with self.assertRaisesRegex(package.PackageError, "inventory mismatch"):
            package.build(assembly, self.root / "dist")
        self.assertFalse((self.root / "dist").exists())

    def test_stage_input_receipts_prevent_rehashing_tampered_assembly_icon(self):
        self.assemble("windows", ghostty_stage(self.root, "windows"), ohmyzsh_stage(self.root, "windows"))
        assembly = self.root / "out"
        write(assembly / "build-inputs/ghostty.ico", b"different icon")
        manifest = package.read_json(assembly / "assembly-manifest.json")
        manifest["inventory"] = fixture_inventory(assembly, "assembly-manifest.json", executable=True)
        package.write_json(assembly / "assembly-manifest.json", manifest)
        with self.assertRaisesRegex(package.PackageError, "inventory mismatch"):
            package.build(assembly, self.root / "dist")

    def test_build_uses_staged_icon_with_no_component_checkout(self):
        self.assemble("windows", ghostty_stage(self.root, "windows"), ohmyzsh_stage(self.root, "windows"))
        assembly = self.root / "out"
        shutil.rmtree(self.root / "ghostty-windows")
        shutil.rmtree(self.root / "ohmyzsh-windows")
        self.lock.unlink()

        def iscc(argv, env=None):
            options = dict(str(item)[2:].split("=", 1) for item in argv if str(item).startswith("/DGx"))
            self.assertTrue(os.path.samefile(Path(options["GxIcon"]), assembly / "build-inputs/ghostty.ico"))
            self.assertEqual(Path(options["GxIcon"]).read_bytes(), b"fixture-stage-icon")
            self.assertEqual(options["GxFontNames"], "JetBrainsMono.ttf|NotoSansCJK.ttc")
            write(Path(options["GxOutput"]) / f"{options['GxFilename']}.exe", b"fixture installer")

        with (mock.patch.object(package, "run", side_effect=iscc),
              mock.patch.object(package, "tool", return_value="ISCC.exe"),
              mock.patch.object(package, "git", side_effect=AssertionError("build must be offline"))):
            result = package.build(assembly, self.root / "dist")
        self.assertEqual(result["components"]["herdr"]["revision"], HERDR_SHA)

    def test_cli_assemble_accepts_explicit_lock_and_root_head_only(self):
        ghostty, ohmyzsh = ghostty_stage(self.root, "windows"), ohmyzsh_stage(self.root, "windows")
        output = io.StringIO()
        with (mock.patch.object(package, "source_info", return_value=(SHA, False, 1700000000)),
              mock.patch.object(package, "validate_version", return_value="0.1.0"), contextlib.redirect_stdout(output)):
            result = package.main(["assemble", "--platform", "windows", "--ghostty-stage", str(ghostty),
                                   "--ohmyzsh-stage", str(ohmyzsh), "--output", str(self.root / "out"),
                                   "--components-lock", str(self.lock)])
        self.assertEqual(result, 0)
        self.assertIn("ASSEMBLED", output.getvalue())
        self.assertEqual(package.read_json(self.root / "out/assembly-manifest.json")["source_commit"], SHA)

    def test_local_assembly_cannot_be_promoted_by_changing_only_manifest_flags(self):
        ghostty = ghostty_stage(self.root, "windows")
        ohmyzsh = ohmyzsh_stage(self.root, "windows", publishable=False, herdr_build={"builder": "local"})
        self.assemble("windows", ghostty, ohmyzsh, allow_dirty=True)
        assembly = self.root / "out"
        info = package.read_json(assembly / "assembly-manifest.json")
        info.update(publishable=True, local_build=False)
        info["stages"]["ohmyzsh"]["publishable"] = True
        package.write_json(assembly / "assembly-manifest.json", info)
        with self.assertRaisesRegex(package.PackageError, "not built on GitHub Actions"):
            package.build(assembly, self.root / "dist")

    @unittest.skipUnless(SYMLINKS, "requires POSIX executable modes")
    def test_stage_and_assembly_executable_modes_are_reverified(self):
        ghostty, ohmyzsh = ghostty_stage(self.root, "linux"), ohmyzsh_stage(self.root, "linux")
        binary = ohmyzsh / "payload/usr/lib/ohmyzsh-gx/bin/gx-zsh"
        binary.chmod(0o644)
        with self.assertRaisesRegex(package.PackageError, "inventory mismatch"):
            self.assemble("linux", ghostty, ohmyzsh)
        binary.chmod(0o755)
        self.assemble("linux", ghostty, ohmyzsh)
        (self.root / "out/root/usr/lib/ghostty-gx/bin/ghostty").chmod(0o644)
        with self.assertRaisesRegex(package.PackageError, "inventory mismatch"):
            package.build(self.root / "out", self.root / "dist")

    def test_standalone_cli_assembles_and_builds_with_native_packager(self):
        import struct
        import sys
        import gx_shell_sources as sources

        platform = "windows" if os.name == "nt" else "linux"
        try:
            compiler = package.tool("iscc" if platform == "windows" else "dpkg-deb", None)
        except package.PackageError as error:
            self.skipTest(str(error))
        script = self.coordinator / "scripts/gx_shell_package.py"
        script.parent.mkdir()
        shutil.copyfile(package.__file__, script)
        shutil.copyfile(sources.__file__, script.parent / "gx_shell_sources.py")
        write(self.coordinator / "CHANGELOG.md", b"## 0.1.0(2026-09-29)\n\n- Fixture\n")
        env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
        env.update(PYTHONDONTWRITEBYTECODE="1", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_TERMINAL_PROMPT="0")

        def command(argv):
            result = package.subprocess.run([str(item) for item in argv], cwd=self.coordinator, env=env,
                                            capture_output=True, text=True, errors="replace", timeout=180)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout.strip()

        command(["git", "init", "-b", "main"])
        command(["git", "add", "CHANGELOG.md", "components.lock.json", "scripts", "packaging"])
        command(["git", "-c", "core.hooksPath=/dev/null", "-c", "user.name=Fixture",
                 "-c", "user.email=fixture@example.invalid", "commit", "-m", "fixture coordinator"])
        coordinator_sha = command(["git", "rev-parse", "HEAD"])
        self.assertNotIn(coordinator_sha, (HERDR_SHA, OMZ_SHA, GHOSTTY_SHA))
        ghostty, ohmyzsh = ghostty_stage(self.root, platform), ohmyzsh_stage(self.root, platform)
        if platform == "windows":
            dib = struct.pack("<IIIHHIIIIII", 40, 16, 32, 1, 32, 0, 1024, 0, 0, 0, 0)
            image = dib + bytes((32, 80, 128, 255)) * 256 + bytes(64)
            icon = struct.pack("<HHHBBBBHHII", 0, 1, 1, 16, 16, 0, 0, 1, 32, len(image), 22) + image
            write(ghostty / "build-inputs/ghostty.ico", icon)
            refresh_stage(ghostty, package.GHOSTTY)
        assembly, dist = self.root / "standalone-assembly", self.root / "standalone-dist"
        output = command([sys.executable, script, "assemble", "--platform", platform,
                          "--ghostty-stage", ghostty, "--ohmyzsh-stage", ohmyzsh, "--output", assembly,
                          "--components-lock", self.lock, "--allow-dirty"])
        self.assertIn("ASSEMBLED", output)
        manifest = package.read_json(assembly / "assembly-manifest.json")
        self.assertEqual(manifest["source_commit"], coordinator_sha)
        self.assertFalse(manifest["source_dirty"])
        self.assertFalse(manifest["publishable"])
        shutil.rmtree(ghostty)
        shutil.rmtree(ohmyzsh)
        self.lock.unlink()
        for name in ("herdr", "ohmyzsh", "gx_ghostty"):
            self.assertFalse((self.coordinator / name).exists())
        output = command([sys.executable, script, "build", "--assembly", assembly, "--output", dist,
                          "--iscc" if platform == "windows" else "--dpkg-deb", compiler])
        self.assertIn("BUILT", output)
        name, source_name = package.artifact_names("0.1.0", platform, local=True)
        self.assertGreater((dist / name).stat().st_size, 1000)
        result = package.read_json(dist / f"{name}.manifest.json")
        self.assertEqual(result["components_lock_digest"], manifest["components_lock_digest"])
        self.assertEqual(result["artifacts"][name]["sha256"], package.digest(dist / name))
        with tarfile.open(dist / source_name) as archive:
            self.assertIn("dependencies/herdr/redistribution/herdr-source.zip", archive.getnames())

    @unittest.skipUnless(SYMLINKS, "requires POSIX symlinks")
    def test_windows_stage_and_redistribution_refuse_symlinks(self):
        for index, relative in enumerate(("app/ghostty.exe", "build-inputs/ghostty.ico", "fonts/JetBrainsMono.ttf")):
            root = self.root / str(index)
            ghostty, ohmyzsh = ghostty_stage(root, "windows"), ohmyzsh_stage(root, "windows")
            path = ghostty / relative
            path.unlink()
            outside = root / "outside"
            write(outside)
            os.symlink(outside, path)
            with self.assertRaisesRegex(package.PackageError, "symlinks"):
                self.assemble("windows", ghostty, ohmyzsh)

    @unittest.skipUnless(os.name == "nt", "Windows junction protection")
    def test_windows_stage_refuses_directory_junctions(self):
        ghostty, ohmyzsh = ghostty_stage(self.root, "windows"), ohmyzsh_stage(self.root, "windows")
        destination = self.root / "external-inputs"
        (ghostty / "build-inputs").rename(destination)
        link = ghostty / "build-inputs"
        result = package.subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(destination)], capture_output=True)
        if result.returncode:
            self.skipTest("junction creation unavailable")
        try:
            with self.assertRaisesRegex(package.PackageError, "symlinks"):
                self.assemble("windows", ghostty, ohmyzsh)
        finally:
            link.rmdir()


class ReleaseVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gx-shell-release-")
        self.addCleanup(cleanup_temp, self.temp)
        self.dir = Path(self.temp.name)
        self.lock = write_lock(self.dir / "coordinator")
        patcher = mock.patch.object(package, "ROOT", self.lock.parent)
        patcher.start()
        self.addCleanup(patcher.stop)
        for platform in package.PLATFORMS:
            name, sources = package.artifact_names("0.1.0", platform)
            write(self.dir / name, f"{platform} installer".encode())
            write(self.dir / sources, f"{platform} sources".encode())
            package.finish_artifacts(self.dir, self.manifest(platform), name, sources)

    def manifest(self, platform, local=False):
        ghostty = {"schema": 3, "platform": package.PLATFORMS[platform][package.GHOSTTY], "architecture": "amd64",
                   "source_repository": "gx0404/gx_ghostty", "source_commit": GHOSTTY_SHA, "source_dirty": False,
                   "package_version": "0.1.0", "product_version": "1.3.2-gx.0.1.0", "zig_version": "0.16.0",
                   "binaries": {"ghostty.exe" if platform == "windows" else "ghostty": "f" * 64}}
        ohmyzsh = {"schema_version": 1, "platform": package.PLATFORMS[platform]["ohmyzsh"],
                   "source": {"repository": "gx0404/ohmyzsh", "revision": OMZ_SHA, "dirty": False},
                   "herdr": {"repository": "https://github.com/gx0404/herdr", "revision": HERDR_SHA},
                   "herdr_build": {"repository": "https://github.com/gx0404/herdr", "revision": HERDR_SHA,
                                   "source_sha256": "e" * 64, "builder": "local" if local else "github-actions",
                                   "package_manager": package.PLATFORMS[platform]["herdr"]},
                   "publishable": not local, "compliance_complete": True}
        lock = package.read_json(self.lock)
        return {"schema": 3, "product": package.PRODUCT, "version": "0.1.0", "platform": platform,
                "architecture": package.PLATFORMS[platform]["arch"], "source_date_epoch": 1700000000,
                "source_commit": SHA, "source_dirty": False, "local_build": local, "publishable": not local,
                "coordinator": {"repository": "gx0404/gx_shell", "revision": SHA, "dirty": False},
                "components_lock": lock, "components_lock_digest": package.digest(self.lock),
                "components": package.component_metadata(lock, ghostty, ohmyzsh),
                "stages": {package.GHOSTTY: ghostty, "ohmyzsh": ohmyzsh}, "payload": [{"path": "fixture"}]}

    def replace_manifest(self, change, platform="linux"):
        name, sources = package.artifact_names("0.1.0", platform)
        info = package.read_json(self.dir / f"{name}.manifest.json")
        change(info)
        info["payload"] = [{"path": "fixture"}]
        package.finish_artifacts(self.dir, info, name, sources)

    def test_complete_release_writes_sha256sums(self):
        files = package.verify(self.dir, "0.1.0", SHA, components_lock=self.lock)
        self.assertEqual(len(files), 6)
        sums = (self.dir / "SHA256SUMS").read_text(encoding="ascii").splitlines()
        self.assertEqual(len(sums), 6)
        self.assertIn(f"{package.digest(self.dir / 'gx-shell_0.1.0_amd64.deb')}  gx-shell_0.1.0_amd64.deb", sums)

    def test_tampered_missing_or_foreign_artifacts_are_rejected(self):
        write(self.dir / "gx-shell_0.1.0_amd64.deb", b"tampered")
        with self.assertRaisesRegex(package.PackageError, "SHA-256 differs"):
            package.verify(self.dir, "0.1.0", SHA)
        with self.assertRaisesRegex(package.PackageError, "source_commit"):
            package.verify(self.dir, "0.1.0", HERDR_SHA)
        (self.dir / "GX-Shell-0.1.0-Setup-x64.exe").unlink()
        with self.assertRaisesRegex(package.PackageError, "missing release file"):
            package.verify(self.dir, "0.1.0", SHA)

    def test_development_builds_cannot_be_released(self):
        self.replace_manifest(lambda info: info.update(publishable=False))
        with self.assertRaisesRegex(package.PackageError, "development build"):
            package.verify(self.dir, "0.1.0", SHA)

    def test_local_artifact_names_are_verified_only_in_development_mode(self):
        local = self.dir / "local"
        for platform in package.PLATFORMS:
            name, sources = package.artifact_names("0.1.0", platform, local=True)
            write(local / name, f"{platform} local installer".encode())
            write(local / sources, f"{platform} local sources".encode())
            package.finish_artifacts(local, self.manifest(platform, local=True), name, sources)
        with self.assertRaisesRegex(package.PackageError, "missing manifest"):
            package.verify(local, "0.1.0", SHA)
        files = package.verify(local, "0.1.0", SHA, allow_dirty=True)
        self.assertIn("GX-Shell-0.1.0-local-Setup-x64.exe", files)
        self.assertIn("gx-shell_0.1.0-local_amd64.deb", files)
        self.assertEqual(package.verify(self.dir, "0.1.0", SHA, allow_dirty=True), package.verify(self.dir, "0.1.0", SHA))

    def test_changed_lock_bytes_are_rejected_even_when_semantically_identical(self):
        self.lock.write_bytes(self.lock.read_bytes() + b"\n")
        with self.assertRaisesRegex(package.PackageError, "lock snapshot or digest"):
            package.verify(self.dir, "0.1.0", SHA)

    def test_platform_component_revision_and_snapshot_must_match_the_lock(self):
        for field in ("components", "components_lock"):
            with self.subTest(field=field):
                name, sources = package.artifact_names("0.1.0", "linux")
                info = self.manifest("linux")
                components = info[field] if field == "components" else info[field]["components"]
                components["herdr"]["revision"] = OMZ_SHA
                package.finish_artifacts(self.dir, info, name, sources)
                with self.assertRaises(package.PackageError):
                    package.verify(self.dir, "0.1.0", SHA)

    def test_local_receipt_cannot_be_laundered_by_publishable_flags(self):
        self.replace_manifest(lambda info: info["stages"]["ohmyzsh"]["herdr_build"].update(builder="local"))
        with self.assertRaisesRegex(package.PackageError, "not built on GitHub Actions"):
            package.verify(self.dir, "0.1.0", SHA, allow_dirty=True)

    def test_coordinator_and_herdr_source_provenance_must_match_across_platforms(self):
        self.replace_manifest(lambda info: info["coordinator"].update(revision=HERDR_SHA))
        with self.assertRaisesRegex(package.PackageError, "coordinator provenance"):
            package.verify(self.dir, "0.1.0", SHA)
        name, sources = package.artifact_names("0.1.0", "linux")
        info = self.manifest("linux")
        info["stages"]["ohmyzsh"]["herdr_build"]["source_sha256"] = "f" * 64
        info["components"]["herdr"]["source_sha256"] = "f" * 64
        package.finish_artifacts(self.dir, info, name, sources)
        with self.assertRaisesRegex(package.PackageError, "four-repository provenance"):
            package.verify(self.dir, "0.1.0", SHA)

    def test_standalone_cli_verifies_both_platform_release_fixtures_without_sources(self):
        import sys
        import gx_shell_sources as sources

        script = self.lock.parent / "scripts/gx_shell_package.py"
        script.parent.mkdir()
        shutil.copyfile(package.__file__, script)
        shutil.copyfile(sources.__file__, script.parent / "gx_shell_sources.py")
        write(self.lock.parent / "CHANGELOG.md", b"## 0.1.0(2026-09-29)\n\n- Fixture\n")
        for name in ("herdr", "ohmyzsh", "gx_ghostty"):
            self.assertFalse((self.lock.parent / name).exists())
        argv = [sys.executable, str(script), "verify", "--dir", str(self.dir), "--version", "0.1.0",
                "--sha", SHA, "--components-lock", str(self.lock)]
        result = package.subprocess.run(argv, cwd=self.lock.parent, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("VERIFIED 6 release files", result.stdout)
        self.assertEqual(len((self.dir / "SHA256SUMS").read_text(encoding="ascii").splitlines()), 6)
        self.replace_manifest(lambda info: info["stages"]["ohmyzsh"]["herdr_build"].update(repository="gx0404/ohmyzsh"))
        result = package.subprocess.run(argv, cwd=self.lock.parent, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 1)
        self.assertIn("different repository", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_cli_reports_errors_without_traceback(self):
        with mock.patch("sys.stderr") as stderr:
            self.assertEqual(package.main(["verify", "--dir", str(self.dir / "missing"), "--version", "0.1.0",
                                           "--sha", SHA, "--components-lock", str(self.lock)]), 1)
        self.assertTrue(stderr.write.called)


def windows_arguments(command_line: str) -> list[str]:
    """argv as Windows (and the Zig runtime Ghostty GX uses) splits a command line."""
    import ctypes
    from ctypes import wintypes

    split = ctypes.windll.shell32.CommandLineToArgvW
    split.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int))
    split.restype = ctypes.POINTER(wintypes.LPWSTR)
    count = ctypes.c_int()
    argv = split("ghostty.exe " + command_line, ctypes.byref(count))
    try:
        return [argv[index] for index in range(1, count.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(argv)


class RepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.iss = (REPOSITORY_ROOT / "packaging/windows/gx-shell.iss").read_text(encoding="utf-8-sig")
        cls.code = cls.iss.split("\n[Code]\n", 1)[1]

    def icon(self, name):
        entry = re.search(r'^Name: "' + re.escape(name) + r'";.*$', self.iss, re.M)
        self.assertIsNotNone(entry, name)
        return entry.group(0)

    def between(self, start, end):
        return self.code[self.code.index(start):self.code.index(end)]

    def test_shortcuts_and_launch_use_the_installed_ghostty_gx(self):
        ghostty = self.icon(r"{autoprograms}\Ghostty GX")
        self.assertIn(r'Filename: "{app}\ghostty\ghostty.exe"', ghostty)
        self.assertNotIn("Parameters:", ghostty)
        zsh = self.icon(r"{autoprograms}\GX Zsh")
        self.assertIn(r'Filename: "{app}\ghostty\ghostty.exe"', zsh)
        self.assertIn(r'Parameters: "-e ""{app}\bin\gx-zsh.exe"""', zsh)
        self.assertIn(r'IconFilename: "{app}\bin\gx-zsh.exe"', zsh)
        for entry in (ghostty, zsh, self.icon(r"{autodesktop}\Ghostty GX")):
            self.assertIn(r'WorkingDir: "{%USERPROFILE}"', entry)
        self.assertTrue(self.icon(r"{autodesktop}\Ghostty GX").endswith("Tasks: desktopicon"))
        self.assertIn(r"UninstallDisplayIcon={app}\ghostty\ghostty.exe", self.iss)
        self.assertIn(r'Filename: "{app}\ghostty\ghostty.exe"; Description: "{cm:LaunchProgram,Ghostty GX}"', self.iss)
        self.assertNotIn("[Registry]", self.iss)
        self.assertNotIn("wezterm-gx.exe\"", self.iss)

    @unittest.skipUnless(os.name == "nt", "Windows command-line parser")
    def test_gx_zsh_shortcut_passes_the_path_as_one_argument(self):
        quoted = re.search(r'Parameters: "((?:[^"]|"")*)"', self.icon(r"{autoprograms}\GX Zsh")).group(1)
        for app in (r"C:\Users\gx\AppData\Local\Programs\GXShell",
                    r"C:\Users\John Doe\AppData\Local\Programs\GXShell"):
            with self.subTest(app=app):
                line = quoted.replace('""', '"').replace("{app}", app)
                self.assertEqual(windows_arguments(line), ["-e", app + r"\bin\gx-zsh.exe"])

    def test_install_delete_removes_only_the_old_wezterm_program_and_stale_pacman_records(self):
        section = re.search(r"^\[InstallDelete\]\n(.*?)(?=^\[)", self.iss, re.M | re.S)
        self.assertIsNotNone(section)
        entries = re.findall(r'^Type: filesandordirs; Name: "([^"]+)"$', section.group(1), re.M)
        self.assertEqual(len(entries), len(re.findall(r"^Type:", section.group(1), re.M)))
        prefix = "{app}\\runtime\\msys64\\var\\lib\\pacman\\local\\"
        deleted = [entry[len(prefix):] for entry in entries if entry.startswith(prefix)]
        self.assertEqual(sorted(set(entries) - {prefix + name for name in deleted}), ["{app}\\wezterm"])
        lock = package.read_json(Path(__file__).parent / "fixtures/gx-shell/msys2-upgrades.json")
        replaced = {f"{item['name']}-{item['upgrades_base']}" for item in lock["packages"]}
        self.assertIn("msys2-runtime-3.6.10-5", deleted)
        self.assertLessEqual(replaced, set(deleted))

    def test_standalone_wezterm_gx_is_no_longer_uninstalled_or_removed(self):
        self.assertNotIn("{734DC47D-4799-46A6-A286-4A64B802370A}", self.iss)
        for app_id in ("{DBB81CDE-31BB-487C-9D03-36C19031CC5D}", "{532CEFC3-E286-41A4-B097-631BD705DB76}"):
            self.assertIn(app_id, self.code)
        removal = self.between("procedure RemoveOldWezTerm;", "procedure KeepForeignWezTerm;")
        self.assertIn("InOldWezTerm(LinkTarget(Path))", removal)
        self.assertIn("InOldWezTerm(Current)", removal)
        self.assertNotIn("DelTree", self.code)
        for text in (r"{autoprograms}\WezTerm GX.lnk", r"{autodesktop}\WezTerm GX.lnk", r"{userprograms}\WezTerm (gx).lnk"):
            self.assertIn(text, self.code)
        uninstall = self.code[self.code.index("procedure CurUninstallStepChanged"):]
        self.assertLess(uninstall.index("KeepForeignWezTerm"), uninstall.index("usPostUninstall"))
        self.assertLess(uninstall.index("usPostUninstall"), uninstall.index("RestoreForeignWezTerm"))

    def test_standalone_ghostty_gx_is_uninstalled_like_oh_my_zsh_gx_and_herdr_gx(self):
        self.assertIn("LegacyCount = 4;", self.code)
        names = self.between("function LegacyName(", "function LegacyRoot(")
        for name in ("0: Result := 'Oh My Zsh GX';", "1: Result := 'Herdr GX';", "2: Result := 'Ghostty GX';",
                     "else Result := FmtMessage(CustomMessage('LegacyAllUsers'), ['Ghostty GX']);"):
            self.assertIn(name, names)
        self.assertIn("if Index = 3 then Result := HKLM else Result := HKCU;",
                      self.between("function LegacyRoot(", "function LegacyKey("))
        keys = self.between("function LegacyKey(", "function UninstallLegacy(")
        self.assertIn("else Result := UninstallRoot + '{49341A18-5070-425E-83B9-79E184242ACF}_is1';", keys)
        legacy = self.between("function UninstallLegacy(", "function PrepareToInstall(")
        self.assertNotIn("HKCU", legacy)
        self.assertIn("Exec(Command, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, Code)",
                      legacy)
        remove = self.between("function RemoveLegacyInstallations:", "function PrepareToInstall(")
        steps = ("(LegacyRoot(I) = HKLM) and not IsAdmin", "CustomMessage('LegacyNeedsAdmin')",
                 "'InstallLocation', Directory", "BusyFile(Directory)", "CustomMessage('BusyFiles')",
                 "if not WizardSilent and", "CustomMessage('LegacyPrompt')", "not UninstallLegacy(I)",
                 "CustomMessage('LegacyFailed')")
        positions = [remove.index(step) for step in steps]
        self.assertEqual(positions, sorted(positions))
        self.assertLess(self.code.index("function BusyFile("), self.code.index("function RemoveLegacyInstallations:"))
        prepare = self.between("function PrepareToInstall(", "procedure AddOwnedPath;")
        self.assertLess(prepare.index("BusyFile(ExpandConstant('{app}'))"), prepare.index("RemoveLegacyInstallations"))
        self.assertLess(prepare.index("RemoveLegacyInstallations"), prepare.index("ResolvedHerdr"))
        for forbidden in ("TerminateProcess", "taskkill", "ShellExec("):
            self.assertNotIn(forbidden, self.code)

    def test_custom_messages_exist_in_both_languages(self):
        section = re.search(r"^\[CustomMessages\]\n(.*?)(?=^\[)", self.iss, re.M | re.S)
        self.assertIsNotNone(section)
        entries = re.findall(r"^(english|chinesesimplified)\.(\w+)=", section.group(1), re.M)
        english = {name for language, name in entries if language == "english"}
        self.assertEqual(english, {name for language, name in entries if language == "chinesesimplified"})
        self.assertEqual(len(entries), 2 * len(english))
        self.assertLessEqual(set(re.findall(r"CustomMessage\('(\w+)'\)", self.code)), english)
        self.assertLessEqual({"LegacyAllUsers", "LegacyNeedsAdmin"}, english)

    def test_fonts_no_longer_shipped_are_unregistered_before_their_files_go(self):
        self.assertIn("#ifndef GxFontNames", self.iss)
        self.assertIn("ShippedFonts = '|{#GxFontNames}|';", self.code)
        fonts = self.between("procedure RemoveUnshippedFonts;", "function GhosttyPath")
        self.assertLess(fonts.index("RemoveFontResourceExW(Path, 0, 0)"), fonts.index("DeleteFile(Path)"))
        self.assertLess(fonts.index("RegDeleteValue(HKCU, FontKey, Key)"), fonts.index("DeleteFile(Path)"))
        self.assertIn("SendBroadcastNotifyMessage(WM_FONTCHANGE, 0, 0)", fonts)
        self.assertIn("NormalizeEntry(ExpandConstant('{app}\\fonts\\') + Name)", fonts)
        steps = self.code[self.code.index("procedure CurStepChanged"):]
        self.assertLess(steps.index("ssInstall then"), steps.index("RemoveUnshippedFonts"))
        self.assertLess(steps.index("RemoveUnshippedFonts"), steps.index("ssPostInstall"))
        self.assertIn("if ShipsFont(Item.Name) and not RegQueryStringValue(HKCU, FontKey, Key, Existing)",
                      self.between("procedure FontsMatching", "procedure Fonts("))

    def test_app_paths_is_written_and_removed_only_while_it_is_ours(self):
        register = self.between("procedure RegisterAppPath;", "procedure UnregisterAppPath;")
        self.assertIn("belongs to another installation", register)
        self.assertIn("AppPathsKey + 'ghostty.exe'", register)
        unregister = self.between("procedure UnregisterAppPath;", "procedure RollbackRegistration;")
        self.assertIn("NormalizeEntry(Current) = NormalizeEntry(GhosttyPath)", unregister)
        rollback = self.between("procedure RollbackRegistration;", "function WezTermLink")
        self.assertIn("if AppPathWritten then UnregisterAppPath;", rollback)
        post = self.code[self.code.index("procedure CurStepChanged"):self.code.index("function InitializeUninstall")]
        self.assertLess(post.index("RegisterAppPath;"), post.index("except"))

    def test_coordinator_uses_exact_independent_component_lock_not_gitlinks(self):
        import gx_shell_sources as sources

        with tempfile.TemporaryDirectory(prefix="gx-shell-lock-contract-") as directory:
            path = write_lock(Path(directory))
            with (mock.patch.object(sources, "load_lock", wraps=sources.load_lock) as load,
                  mock.patch.object(sources, "lock_digest", wraps=sources.lock_digest) as checksum,
                  mock.patch.object(package, "git", side_effect=AssertionError("must not inspect component Git"))):
                lock, hashed, raw = package.read_components_lock(path)
            load.assert_called_once_with(path)
            checksum.assert_called_once_with(path)
            self.assertEqual(raw, path.read_bytes())
            self.assertEqual(hashed, package.digest(path))
            self.assertEqual(set(lock["components"]), {"herdr", "ohmyzsh", "gx_ghostty"})
            self.assertEqual(len({SHA, *(item["revision"] for item in lock["components"].values())}), 4)
            for name, entry in lock["components"].items():
                self.assertEqual(entry["repository"], f"gx0404/{name}")
                self.assertEqual(entry["branch"], sources.COMPONENT_BRANCHES[name])
            for invalid in ("gx", "HEAD", "abc1234"):
                lock["components"]["herdr"]["revision"] = invalid
                package.write_json(path, lock)
                with self.assertRaises(package.PackageError):
                    package.read_components_lock(path)


if __name__ == "__main__":
    unittest.main()

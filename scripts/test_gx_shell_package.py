"""GX Shell assembly contract checks on synthetic component stages; no compiler or installer needed."""
import contextlib
import io
import json
import os
import re
import shutil
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import gx_shell_package as package
import gx_shell_sources as sources

SHA = "a" * 40
HERDR_SHA, OMZ_SHA, WEZTERM_SHA = "b" * 40, "c" * 40, "d" * 40
SYMLINKS = os.name != "nt"
REPOSITORY_ROOT = package.ROOT


def write(path: Path, data: bytes = b"fixture", executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if executable:
        path.chmod(0o755)


def write_lock(root: Path) -> Path:
    lock = {"schema": 1, "components": {
        name: {"repository": f"gx0404/{name}", "branch": sources.COMPONENT_BRANCHES[name], "revision": revision}
        for name, revision in (("herdr", HERDR_SHA), ("ohmyzsh", OMZ_SHA), ("wezterm", WEZTERM_SHA))},
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
    name = "stage-manifest.json" if component == "wezterm" else "package-manifest.json"
    info = package.read_json(stage / name)
    if component == "wezterm":
        info["files"] = fixture_inventory(stage, name)
    else:
        for field, directory in (("payload", "payload"), ("redistribution", "redistribution"), ("build_inputs", "build-inputs")):
            info[field] = fixture_inventory(stage / directory, executable=field == "payload")
    package.write_json(stage / name, info)


def wezterm_stage(root: Path, platform: str, **overrides) -> Path:
    stage = root / f"wezterm-{platform}"
    info = {"schema": 2, "platform": package.PLATFORMS[platform]["wezterm"], "source_commit": WEZTERM_SHA,
            "source_repository": "gx0404/wezterm", "source_dirty": False, "package_version": "0.4.0",
            "product_version": "20260928-000000-dddddddd", "resource_version": "b" * 64}
    if platform == "windows":
        lib, suffix = stage / "app", ".exe"
        for name in ("wezterm.exe", "wezterm-gui.exe", "wezterm-gx.exe", "wezterm-gx-cli.exe"):
            write(lib / name, b"MZ" + name.encode())
        write(stage / "app/resources/resource-version", b"b" * 64)
        write(stage / "fonts/JetBrainsMono.ttf", b"shared font")
        write(stage / "fonts/NotoSansCJK.ttc", b"cjk font")
        write(stage / "build-inputs/terminal.ico", b"fixture-stage-icon")
    else:
        info["deb_depends"] = "libc6 (>= 2.30), zsh, fontconfig"
        lib, suffix = stage / "root/usr/lib/wezterm-gx", ""
        for name in ("wezterm", "wezterm-gui", "wezterm-gx", "wezterm-gx-gui"):
            write(lib / name, b"\x7fELF" + name.encode(), executable=True)
        write(stage / "root/usr/share/wezterm-gx/resource-version", b"b" * 64)
        write(stage / "root/usr/share/wezterm-gx/dotfiles/wezterm-config/LICENSE", b"MIT License\n")
        write(stage / "root/usr/share/doc/wezterm-gx/copyright", b"MIT License\n")
        write(stage / "root/usr/share/applications/org.gx0404.wezterm.desktop", b"[Desktop Entry]\n")
        write(stage / "root/usr/share/fonts/truetype/wezterm-gx/JetBrainsMono.ttf", b"shared font")
        write(stage / "root/usr/share/fonts/truetype/wezterm-gx/NotoSansCJK.ttc", b"cjk font")
        (stage / "root/usr/bin").mkdir(parents=True)
        for name in ("wezterm-gx", "wezterm-gx-gui"):
            os.symlink(f"../lib/wezterm-gx/{name}", stage / "root/usr/bin" / name)
    write(stage / "build-inputs/gx-config-releases.json", b'{"schema": 1, "releases": {}}\n')
    info["binaries"] = {name + suffix: package.digest(lib / (name + suffix)) for name in ("wezterm", "wezterm-gui")}
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
            "herdr": {"repository": "gx0404/herdr", "revision": HERDR_SHA, "version": "0.9.1"},
            "herdr_build": {"repository": "gx0404/herdr", "revision": HERDR_SHA, "version": "0.9.1",
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


class AssemblyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gx-shell-unit-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.coordinator = self.root / "coordinator"
        self.lock = write_lock(self.coordinator)
        shutil.copytree(REPOSITORY_ROOT / "packaging", self.coordinator / "packaging")
        patcher = mock.patch.object(package, "ROOT", self.coordinator)
        patcher.start()
        self.addCleanup(patcher.stop)

    def assemble(self, platform, wezterm, ohmyzsh, **kwargs):
        options = {"version": "0.1.0", "sha": SHA, "dirty": False, "epoch": 1700000000,
                   "components_lock": self.lock}
        options.update(kwargs)
        return package.assemble(platform, wezterm, ohmyzsh, self.root / "out", **options)

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
        manifest = self.assemble("windows", wezterm_stage(self.root, "windows"), ohmyzsh_stage(self.root, "windows"))
        payload = self.root / "out/payload"
        for name in package.REQUIRED["windows"]:
            self.assertTrue((payload / name).is_file(), name)
        self.assertEqual(sorted(p.name for p in (payload / "fonts").iterdir()), ["JetBrainsMono.ttf", "NotoSansCJK.ttc"])
        self.assertFalse((payload / "wezterm/fonts").exists())
        self.assertTrue((self.root / "out/redistribution/dependencies/zsh/SOURCE.txt").is_file())
        self.assertTrue(manifest["publishable"])
        self.assertEqual(manifest["components"]["herdr"]["package_manager"], "windows-installer")
        self.assertEqual(package.read_json(self.root / "out/assembly-manifest.json")["source_commit"], SHA)
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith(".gx-shell-assembly-")], [])

    def test_same_font_name_with_different_content_is_rejected(self):
        with self.assertRaisesRegex(package.PackageError, "different fonts"):
            self.assemble("windows", wezterm_stage(self.root, "windows"),
                          ohmyzsh_stage(self.root, "windows", font=b"another build"))
        self.assertFalse((self.root / "out").exists())

    def test_stages_match_independent_locked_commits_and_herdr_identity(self):
        cases = (
            ({"source_commit": SHA}, {}, "different commit"),
            ({"source_repository": "gx0404/gx_shell"}, {}, "different repository"),
            ({"source_dirty": True}, {}, "dirty"),
            ({"schema": 1}, {}, "schema 2"),
            ({}, {"source": {"revision": SHA}}, "different commit"),
            ({}, {"source": {"repository": "gx0404/gx_shell"}}, "different repository"),
            ({}, {"publishable": False}, "development"),
            ({}, {"herdr_build": {"package_manager": None}}, "package identity"),
            ({}, {"herdr": {"revision": OMZ_SHA}}, "locked commit"),
            ({}, {"herdr_build": {"revision": OMZ_SHA}}, "locked commit"),
            ({}, {"herdr_build": {"repository": "gx0404/ohmyzsh"}}, "different repository"),
            ({}, {"herdr_build": {"source_sha256": None}}, "source SHA-256"),
            ({}, {"herdr_build": {"builder": "local"}}, "not built on GitHub Actions"),
            ({}, {"herdr_build": {"builder": None}}, "not built on GitHub Actions"),
            ({}, {"herdr_build": {"builder": "self-hosted"}}, "not built on GitHub Actions"),
        )
        for index, (wezterm_change, ohmyzsh_change, message) in enumerate(cases):
            with self.subTest(message=message):
                root = self.root / str(index)
                root.mkdir()
                wezterm = wezterm_stage(root, "windows", **wezterm_change)
                ohmyzsh = ohmyzsh_stage(root, "windows", **ohmyzsh_change)
                with self.assertRaisesRegex(package.PackageError, message):
                    package.assemble("windows", wezterm, ohmyzsh, root / "out", version="0.1.0", sha=SHA,
                                     dirty=False, epoch=0)

    def test_dirty_checkout_requires_explicit_development_mode(self):
        wezterm, ohmyzsh = wezterm_stage(self.root, "windows"), ohmyzsh_stage(self.root, "windows")
        with self.assertRaisesRegex(package.PackageError, "clean coordinator"):
            self.assemble("windows", wezterm, ohmyzsh, dirty=True)
        manifest = self.assemble("windows", wezterm, ohmyzsh, dirty=True, allow_dirty=True)
        self.assertFalse(manifest["publishable"])

    def test_locally_built_herdr_needs_allow_dirty_and_is_never_publishable(self):
        build = {"builder": "local"}
        wezterm = wezterm_stage(self.root, "windows")
        ohmyzsh = ohmyzsh_stage(self.root, "windows", publishable=False, herdr_build=build)
        with self.assertRaisesRegex(package.PackageError, "not built on GitHub Actions .*--allow-dirty"):
            self.assemble("windows", wezterm, ohmyzsh)
        manifest = self.assemble("windows", wezterm, ohmyzsh, allow_dirty=True)
        self.assertFalse(manifest["publishable"])
        self.assertEqual(manifest["components"]["herdr"]["builder"], "local")

    def test_development_builds_get_local_artifact_names(self):
        calls = []

        def iscc(argv, env=None):
            calls.append(argv)
            options = dict(str(item)[2:].split("=", 1) for item in argv if str(item).startswith("/DGx"))
            write(Path(options["GxOutput"]) / f"{options['GxFilename']}.exe", b"MZ fixture installer")

        wezterm, ohmyzsh = wezterm_stage(self.root, "windows"), ohmyzsh_stage(self.root, "windows")
        for label, options, names in (
                ("release", {}, ["GX-Shell-0.1.0-Setup-x64.exe", "gx-shell_0.1.0_windows-x64-sources.tar.xz"]),
                ("local", {"dirty": True, "allow_dirty": True},
                 ["GX-Shell-0.1.0-local-Setup-x64.exe", "gx-shell_0.1.0-local_windows-x64-sources.tar.xz"])):
            with self.subTest(label):
                assembly = self.root / f"assembly-{label}"
                package.assemble("windows", wezterm, ohmyzsh, assembly, version="0.1.0", sha=SHA, epoch=1700000000,
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
        write(ohmyzsh / "payload/wezterm/wezterm-gx.exe", b"foreign")
        refresh_stage(ohmyzsh, "ohmyzsh")
        with self.assertRaisesRegex(package.PackageError, "same path: .*/payload/wezterm/wezterm-gx.exe"):
            self.assemble("windows", wezterm_stage(self.root, "windows"), ohmyzsh)

    def test_windows_layout_adds_the_noto_license_without_overwriting_component_files(self):
        self.assemble("windows", wezterm_stage(self.root, "windows"), ohmyzsh_stage(self.root, "windows"))
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
            package.assemble("windows", wezterm_stage(root, "windows"), ohmyzsh, root / "out", version="0.1.0",
                             sha=SHA, dirty=False, epoch=0)

    def test_wezterm_stage_binaries_must_match_their_manifest_hashes(self):
        for platform in ("windows", "linux") if SYMLINKS else ("windows",):
            with self.subTest(platform=platform):
                stage = wezterm_stage(self.root / platform, platform)
                binary = stage / ("app/wezterm-gui.exe" if platform == "windows" else "root/usr/lib/wezterm-gx/wezterm-gui")
                info = package.check_wezterm_stage(stage, platform, WEZTERM_SHA, False)
                self.assertEqual(info["binaries"][binary.name], package.digest(binary))
                binary.write_bytes(b"tampered")
                with self.assertRaisesRegex(package.PackageError, "inventory mismatch"):
                    package.check_wezterm_stage(stage, platform, WEZTERM_SHA, False)
                refresh_stage(stage, "wezterm")
                with self.assertRaisesRegex(package.PackageError, "differs from its manifest"):
                    package.check_wezterm_stage(stage, platform, WEZTERM_SHA, False)
                binary.unlink()
                with self.assertRaisesRegex(package.PackageError, "inventory mismatch"):
                    package.check_wezterm_stage(stage, platform, WEZTERM_SHA, False)
                escape = binary.parent.parent / "escape"
                write(escape, b"outside the payload")
                info["binaries"] = {"../escape": package.digest(escape)}
                package.write_json(stage / "stage-manifest.json", info)
                refresh_stage(stage, "wezterm")
                with self.assertRaisesRegex(package.PackageError, "unsafe inventory path"):
                    package.check_wezterm_stage(stage, platform, WEZTERM_SHA, False)

    @unittest.skipUnless(SYMLINKS, "deb payload fixtures need POSIX symlinks")
    def test_linux_layout_merges_depends_fonts_and_entry_points(self):
        manifest = self.assemble("linux", wezterm_stage(self.root, "linux"), ohmyzsh_stage(self.root, "linux"))
        root = self.root / "out/root"
        self.assertEqual(manifest["deb_depends"], "fontconfig, git, libc6 (>= 2.30), zsh")
        fonts = root / package.LINUX_FONT_DIR
        self.assertEqual(sorted(p.name for p in fonts.iterdir()), ["JetBrainsMono.ttf", "NotoSansCJK.ttc"])
        for directory in package.LINUX_COMPONENT_FONT_DIRS:
            self.assertFalse((root / directory).exists(), directory)
        self.assertFalse((root / "DEBIAN").exists())
        for link, target in package.LINUX_ENTRY_POINTS.items():
            self.assertEqual(os.readlink(root / link), target)
        self.assertEqual((root / "usr/lib/wezterm-gx/wezterm-gui").stat().st_mode & 0o777, 0o755)
        self.assertEqual((root / "usr/share/ohmyzsh-gx/oh-my-zsh.sh").stat().st_mode & 0o777, 0o644)
        self.assertTrue((root / "usr/share/doc/gx-shell/copyright").is_file())

    @unittest.skipUnless(SYMLINKS, "deb payload fixtures need POSIX symlinks")
    def test_linux_copyright_cites_only_installed_paths_including_the_noto_license(self):
        self.assemble("linux", wezterm_stage(self.root, "linux"), ohmyzsh_stage(self.root, "linux"))
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
        wezterm = wezterm_stage(self.root, "linux")
        os.symlink("/etc/passwd", wezterm / "root/usr/share/wezterm-gx/escape")
        with self.assertRaisesRegex(package.PackageError, "unexpected payload symlinks"):
            self.assemble("linux", wezterm, ohmyzsh_stage(self.root, "linux"))

    @unittest.skipUnless(SYMLINKS and shutil.which("dpkg-deb"), "needs dpkg-deb and POSIX symlinks")
    def test_real_deb_build_carries_control_and_maintainer_scripts(self):
        self.assemble("linux", wezterm_stage(self.root, "linux"), ohmyzsh_stage(self.root, "linux"))
        result = package.build(self.root / "out", self.root / "dist")
        deb = self.root / "dist/gx-shell_0.1.0_amd64.deb"
        self.assertIn(deb.name, result["artifacts"])
        info = package.subprocess.run(["dpkg-deb", "--info", str(deb)], check=True, capture_output=True, text=True).stdout
        for text in ("Package: gx-shell", "Replaces: herdr-gx, ohmyzsh-gx, wezterm-gx", " preinst", " postinst", " postrm"):
            self.assertIn(text, info)
        self.assertFalse((self.root / "out/root/DEBIAN").exists())
        contents = package.subprocess.run(["dpkg-deb", "--contents", str(deb)], check=True, capture_output=True, text=True).stdout
        self.assertIn("./usr/bin/gx-zsh -> ../lib/ohmyzsh-gx/bin/gx-zsh", contents)
        self.assertIn("root/root", contents)

    @unittest.skipUnless(SYMLINKS and shutil.which("dpkg-deb"), "needs dpkg-deb and POSIX symlinks")
    def test_real_deb_build_is_reproducible_from_the_manifest_epoch(self):
        self.assemble("linux", wezterm_stage(self.root, "linux"), ohmyzsh_stage(self.root, "linux"))
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
        self.assertIn("Conflicts: herdr, herdr-gx, ohmyzsh-gx, wezterm-gx\n", text)

    def test_release_notes_use_the_changelog_section_and_list_the_assets(self):
        (self.root / "CHANGELOG.md").write_text("# log\n\n## 0.2.0(TBD)\n\n- newer\n\n## 0.1.0(2026-09-28)\n\n- first\n",
                                                encoding="utf-8")
        notes = package.release_notes("0.1.0", self.root)
        self.assertTrue(notes.startswith("- first\n"))
        self.assertNotIn("newer", notes)
        for name in ("GX-Shell-0.1.0-Setup-x64.exe", "gx-shell_0.1.0_amd64.deb", "SHA256SUMS"):
            self.assertIn(name, notes)
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
        wezterm, ohmyzsh = wezterm_stage(self.root, "windows"), ohmyzsh_stage(self.root, "windows")
        with mock.patch.object(package, "git", side_effect=AssertionError("offline assembly must not inspect Git")):
            manifest = self.assemble("windows", wezterm, ohmyzsh)
        self.assertEqual(manifest["schema"], 2)
        self.assertEqual(manifest["coordinator"]["revision"], SHA)
        self.assertEqual(manifest["components_lock"], package.read_json(self.lock))
        self.assertEqual(manifest["components_lock_digest"], package.digest(self.lock))
        self.assertEqual((self.root / "out/components.lock.json").read_bytes(), self.lock.read_bytes())
        for name, revision in (("herdr", HERDR_SHA), ("ohmyzsh", OMZ_SHA), ("wezterm", WEZTERM_SHA)):
            self.assertEqual(manifest["components"][name]["revision"], revision)
            self.assertEqual(manifest["components"][name]["repository"], f"gx0404/{name}")
            self.assertFalse((self.coordinator / name).exists())
        paths = {item["path"] for item in manifest["inventory"]}
        self.assertTrue({"components.lock.json", "build-inputs/terminal.ico", "build-inputs/gx-config-releases.json",
                         "build-inputs/ohmyzsh/windows.iss"} <= paths)
        self.assertEqual((self.root / "out/build-inputs/terminal.ico").read_bytes(), b"fixture-stage-icon")

    def test_full_stage_inventories_reject_missing_extra_and_changed_nonbinary_files(self):
        targets = (
            ("wezterm", "app/resources/resource-version"), ("wezterm", "app/wezterm-gx.exe"),
            ("wezterm", "fonts/JetBrainsMono.ttf"), ("wezterm", "build-inputs/terminal.ico"),
            ("wezterm", "build-inputs/gx-config-releases.json"),
            ("ohmyzsh", "payload/share/ohmyzsh-gx/oh-my-zsh.sh"),
            ("ohmyzsh", "redistribution/dependencies/zsh/SOURCE.txt"),
            ("ohmyzsh", "build-inputs/windows.iss"))
        for index, (component, relative) in enumerate(targets):
            for change in ("missing", "extra", "changed"):
                with self.subTest(component=component, relative=relative, change=change):
                    root = self.root / f"{index}-{change}"
                    wezterm, ohmyzsh = wezterm_stage(root, "windows"), ohmyzsh_stage(root, "windows")
                    target = (wezterm if component == "wezterm" else ohmyzsh) / relative
                    if change == "missing":
                        target.unlink()
                    elif change == "extra":
                        write(target.with_name("unlisted-file"))
                    else:
                        target.write_bytes(b"tampered")
                    with self.assertRaisesRegex(package.PackageError, "inventory mismatch"):
                        self.assemble("windows", wezterm, ohmyzsh)
                    self.assertFalse((self.root / "out").exists())

    def test_inventory_paths_duplicates_sizes_and_hashes_are_strict(self):
        invalid = ("../escape", "/absolute", "C:/escape", "app/../escape", "app//escape",
                   "app/./escape", "app\\escape", "app/escape.", "app/NUL", "")
        for component in ("wezterm", "ohmyzsh"):
            for index, name in enumerate(invalid):
                with self.subTest(component=component, name=name):
                    root = self.root / f"{component}-{index}"
                    wezterm, ohmyzsh = wezterm_stage(root, "windows"), ohmyzsh_stage(root, "windows")
                    path = wezterm / "stage-manifest.json" if component == "wezterm" else ohmyzsh / "package-manifest.json"
                    info = package.read_json(path)
                    field = "files" if component == "wezterm" else "payload"
                    info[field][0]["path"] = name
                    package.write_json(path, info)
                    with self.assertRaises(package.PackageError):
                        self.assemble("windows", wezterm, ohmyzsh)
        for index, change in enumerate(("duplicate", "size", "sha256", "self", "empty")):
            root = self.root / f"record-{index}"
            wezterm, ohmyzsh = wezterm_stage(root, "windows"), ohmyzsh_stage(root, "windows")
            info = package.read_json(wezterm / "stage-manifest.json")
            if change == "duplicate":
                info["files"].append(dict(info["files"][0]))
            elif change == "self":
                info["files"][0]["path"] = "stage-manifest.json"
            elif change == "empty":
                info["files"] = []
            else:
                info["files"][0][change] = True
            package.write_json(wezterm / "stage-manifest.json", info)
            with self.subTest(change=change), self.assertRaises(package.PackageError):
                self.assemble("windows", wezterm, ohmyzsh)

    def test_required_build_inputs_and_herdr_source_cannot_be_removed_with_inventory(self):
        for index, relative in enumerate(("build-inputs/terminal.ico", "build-inputs/gx-config-releases.json")):
            root = self.root / str(index)
            wezterm, ohmyzsh = wezterm_stage(root, "windows"), ohmyzsh_stage(root, "windows")
            (wezterm / relative).unlink()
            refresh_stage(wezterm, "wezterm")
            with self.assertRaisesRegex(package.PackageError, "lacks build-inputs"):
                self.assemble("windows", wezterm, ohmyzsh)
        root = self.root / "source"
        wezterm, ohmyzsh = wezterm_stage(root, "windows"), ohmyzsh_stage(root, "windows")
        (ohmyzsh / "redistribution/dependencies/herdr/redistribution/herdr-source.zip").unlink()
        refresh_stage(ohmyzsh, "ohmyzsh")
        with self.assertRaisesRegex(package.PackageError, "no corresponding redistribution file"):
            self.assemble("windows", wezterm, ohmyzsh)

    def test_build_rechecks_every_assembly_input_before_invoking_a_packager(self):
        self.assemble("windows", wezterm_stage(self.root, "windows"), ohmyzsh_stage(self.root, "windows"))
        assembly = self.root / "out"
        for name in ("payload/bin/gx-zsh.exe", "build-inputs/terminal.ico", "build-inputs/gx-config-releases.json",
                     "build-inputs/ohmyzsh/windows.iss", "redistribution/dependencies/zsh/SOURCE.txt", "components.lock.json"):
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
        self.assemble("windows", wezterm_stage(self.root, "windows"), ohmyzsh_stage(self.root, "windows"))
        assembly = self.root / "out"
        write(assembly / "build-inputs/terminal.ico", b"different icon")
        manifest = package.read_json(assembly / "assembly-manifest.json")
        manifest["inventory"] = fixture_inventory(assembly, "assembly-manifest.json", executable=True)
        package.write_json(assembly / "assembly-manifest.json", manifest)
        with self.assertRaisesRegex(package.PackageError, "inventory mismatch"):
            package.build(assembly, self.root / "dist")

    def test_build_uses_staged_icon_with_no_component_checkout(self):
        self.assemble("windows", wezterm_stage(self.root, "windows"), ohmyzsh_stage(self.root, "windows"))
        assembly = self.root / "out"
        shutil.rmtree(self.root / "wezterm-windows")
        shutil.rmtree(self.root / "ohmyzsh-windows")
        self.lock.unlink()

        def iscc(argv, env=None):
            options = dict(str(item)[2:].split("=", 1) for item in argv if str(item).startswith("/DGx"))
            self.assertEqual(Path(options["GxIcon"]), assembly / "build-inputs/terminal.ico")
            self.assertEqual(Path(options["GxIcon"]).read_bytes(), b"fixture-stage-icon")
            write(Path(options["GxOutput"]) / f"{options['GxFilename']}.exe", b"fixture installer")

        with (mock.patch.object(package, "run", side_effect=iscc),
              mock.patch.object(package, "tool", return_value="ISCC.exe"),
              mock.patch.object(package, "git", side_effect=AssertionError("build must be offline"))):
            result = package.build(assembly, self.root / "dist")
        self.assertEqual(result["components"]["herdr"]["revision"], HERDR_SHA)

    def test_cli_assemble_accepts_explicit_lock_and_root_head_only(self):
        wezterm, ohmyzsh = wezterm_stage(self.root, "windows"), ohmyzsh_stage(self.root, "windows")
        output = io.StringIO()
        with (mock.patch.object(package, "source_info", return_value=(SHA, False, 1700000000)),
              mock.patch.object(package, "validate_version", return_value="0.1.0"), contextlib.redirect_stdout(output)):
            result = package.main(["assemble", "--platform", "windows", "--wezterm-stage", str(wezterm),
                                   "--ohmyzsh-stage", str(ohmyzsh), "--output", str(self.root / "out"),
                                   "--components-lock", str(self.lock)])
        self.assertEqual(result, 0)
        self.assertIn("ASSEMBLED", output.getvalue())
        self.assertEqual(package.read_json(self.root / "out/assembly-manifest.json")["source_commit"], SHA)

    def test_local_assembly_cannot_be_promoted_by_changing_only_manifest_flags(self):
        wezterm = wezterm_stage(self.root, "windows")
        ohmyzsh = ohmyzsh_stage(self.root, "windows", publishable=False, herdr_build={"builder": "local"})
        self.assemble("windows", wezterm, ohmyzsh, allow_dirty=True)
        assembly = self.root / "out"
        info = package.read_json(assembly / "assembly-manifest.json")
        info.update(publishable=True, local_build=False)
        info["stages"]["ohmyzsh"]["publishable"] = True
        package.write_json(assembly / "assembly-manifest.json", info)
        with self.assertRaisesRegex(package.PackageError, "not built on GitHub Actions"):
            package.build(assembly, self.root / "dist")

    @unittest.skipUnless(SYMLINKS, "requires POSIX executable modes")
    def test_stage_and_assembly_executable_modes_are_reverified(self):
        wezterm, ohmyzsh = wezterm_stage(self.root, "linux"), ohmyzsh_stage(self.root, "linux")
        binary = ohmyzsh / "payload/usr/lib/ohmyzsh-gx/bin/gx-zsh"
        binary.chmod(0o644)
        with self.assertRaisesRegex(package.PackageError, "inventory mismatch"):
            self.assemble("linux", wezterm, ohmyzsh)
        binary.chmod(0o755)
        self.assemble("linux", wezterm, ohmyzsh)
        (self.root / "out/root/usr/lib/wezterm-gx/wezterm-gx").chmod(0o644)
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
        self.assertNotIn(coordinator_sha, (HERDR_SHA, OMZ_SHA, WEZTERM_SHA))
        wezterm, ohmyzsh = wezterm_stage(self.root, platform), ohmyzsh_stage(self.root, platform)
        if platform == "windows":
            dib = struct.pack("<IIIHHIIIIII", 40, 16, 32, 1, 32, 0, 1024, 0, 0, 0, 0)
            image = dib + bytes((32, 80, 128, 255)) * 256 + bytes(64)
            icon = struct.pack("<HHHBBBBHHII", 0, 1, 1, 16, 16, 0, 0, 1, 32, len(image), 22) + image
            write(wezterm / "build-inputs/terminal.ico", icon)
            refresh_stage(wezterm, "wezterm")
        assembly, dist = self.root / "standalone-assembly", self.root / "standalone-dist"
        output = command([sys.executable, script, "assemble", "--platform", platform,
                          "--wezterm-stage", wezterm, "--ohmyzsh-stage", ohmyzsh, "--output", assembly,
                          "--components-lock", self.lock, "--allow-dirty"])
        self.assertIn("ASSEMBLED", output)
        manifest = package.read_json(assembly / "assembly-manifest.json")
        self.assertEqual(manifest["source_commit"], coordinator_sha)
        self.assertFalse(manifest["source_dirty"])
        self.assertFalse(manifest["publishable"])
        shutil.rmtree(wezterm)
        shutil.rmtree(ohmyzsh)
        self.lock.unlink()
        for name in ("herdr", "ohmyzsh", "wezterm"):
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
        for index, relative in enumerate(("app/wezterm.exe", "build-inputs/terminal.ico", "fonts/JetBrainsMono.ttf")):
            root = self.root / str(index)
            wezterm, ohmyzsh = wezterm_stage(root, "windows"), ohmyzsh_stage(root, "windows")
            path = wezterm / relative
            path.unlink()
            outside = root / "outside"
            write(outside)
            os.symlink(outside, path)
            with self.assertRaisesRegex(package.PackageError, "symlinks"):
                self.assemble("windows", wezterm, ohmyzsh)

    @unittest.skipUnless(os.name == "nt", "Windows junction protection")
    def test_windows_stage_refuses_directory_junctions(self):
        wezterm, ohmyzsh = wezterm_stage(self.root, "windows"), ohmyzsh_stage(self.root, "windows")
        destination = self.root / "external-inputs"
        (wezterm / "build-inputs").rename(destination)
        link = wezterm / "build-inputs"
        result = package.subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(destination)], capture_output=True)
        if result.returncode:
            self.skipTest("junction creation unavailable")
        try:
            with self.assertRaisesRegex(package.PackageError, "symlinks"):
                self.assemble("windows", wezterm, ohmyzsh)
        finally:
            link.rmdir()


class ReleaseVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gx-shell-release-")
        self.addCleanup(self.temp.cleanup)
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
        wezterm = {"schema": 2, "platform": package.PLATFORMS[platform]["wezterm"],
                   "source_repository": "gx0404/wezterm", "source_commit": WEZTERM_SHA, "source_dirty": False}
        ohmyzsh = {"schema_version": 1, "platform": package.PLATFORMS[platform]["ohmyzsh"],
                   "source": {"repository": "gx0404/ohmyzsh", "revision": OMZ_SHA, "dirty": False},
                   "herdr": {"repository": "gx0404/herdr", "revision": HERDR_SHA},
                   "herdr_build": {"repository": "gx0404/herdr", "revision": HERDR_SHA,
                                   "source_sha256": "e" * 64, "builder": "local" if local else "github-actions",
                                   "package_manager": package.PLATFORMS[platform]["herdr"]},
                   "publishable": not local, "compliance_complete": True}
        lock = package.read_json(self.lock)
        return {"schema": 2, "product": package.PRODUCT, "version": "0.1.0", "platform": platform,
                "architecture": package.PLATFORMS[platform]["arch"], "source_date_epoch": 1700000000,
                "source_commit": SHA, "source_dirty": False, "local_build": local, "publishable": not local,
                "coordinator": {"repository": "gx0404/gx_shell", "revision": SHA, "dirty": False},
                "components_lock": lock, "components_lock_digest": package.digest(self.lock),
                "components": package.component_metadata(lock, wezterm, ohmyzsh),
                "stages": {"wezterm": wezterm, "ohmyzsh": ohmyzsh}, "payload": [{"path": "fixture"}]}

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
        for name in ("herdr", "ohmyzsh", "wezterm"):
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


class RepositoryTests(unittest.TestCase):
    def test_gx_zsh_start_menu_shortcut_opens_in_wezterm_gx_on_the_local_domain(self):
        text = (package.ROOT / "packaging/windows/gx-shell.iss").read_text(encoding="utf-8-sig")
        entry = re.search(r'^Name: "\{autoprograms\}\\GX Zsh";.*$', text, re.M)
        self.assertIsNotNone(entry)
        self.assertIn(r'Filename: "{app}\wezterm\wezterm-gx.exe"', entry.group(0))
        self.assertIn(r'Parameters: "start --domain local --attach -- ""{app}\bin\gx-zsh.exe"""', entry.group(0))

    def test_upgrades_delete_the_pacman_records_of_replaced_base_packages(self):
        text = (package.ROOT / "packaging/windows/gx-shell.iss").read_text(encoding="utf-8-sig")
        section = re.search(r"^\[InstallDelete\]\n(.*?)(?=^\[)", text, re.M | re.S)
        self.assertIsNotNone(section)
        deleted = re.findall(r'^Type: filesandordirs; Name: "\{app\}\\runtime\\msys64\\var\\lib\\pacman\\local\\([^"\\]+)"$',
                             section.group(1), re.M)
        self.assertEqual(len(deleted), len(re.findall(r"^Type:", section.group(1), re.M)))
        lock = package.read_json(Path(__file__).parent / "fixtures/gx-shell/msys2-upgrades.json")
        replaced = {f"{item['name']}-{item['upgrades_base']}" for item in lock["packages"]}
        self.assertIn("msys2-runtime-3.6.10-5", deleted)
        self.assertLessEqual(replaced, set(deleted))

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
            self.assertEqual(set(lock["components"]), {"herdr", "ohmyzsh", "wezterm"})
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

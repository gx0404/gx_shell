import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest import mock

import gx_shell_build as build
import gx_shell_sources as sources


class BuildDriverTests(unittest.TestCase):
    def test_safe_path_rejects_unsafe_paths(self):
        with self.assertRaises(build.BuildError):
            build.safe_path(Path("D:/gx build/run"))
        with self.assertRaises(build.BuildError):
            build.safe_path(Path("D:/gx/../run"))

    def test_power_shell_mapping_is_quoted(self):
        value = build.ps_map({"herdr": r"D:\gx\herdr", "ohmyzsh": r"D:\gx\ohmyzsh"})
        self.assertEqual(value, "@{herdr='D:\\gx\\herdr';ohmyzsh='D:\\gx\\ohmyzsh'}")

    def test_real_lock_has_three_independent_components(self):
        lock = build.read_lock(build.ROOT / "components.lock.json")
        self.assertEqual(set(lock["components"]), {"herdr", "ohmyzsh", "wezterm"})
        for name, entry in lock["components"].items():
            self.assertEqual(entry["repository"], "gx0404/" + name)
            self.assertEqual(entry["branch"], sources.COMPONENT_BRANCHES[name])
            self.assertRegex(entry["revision"], r"^[0-9a-f]{40}$")

    def test_help_is_available_without_sources_or_tools(self):
        with self.assertRaises(SystemExit) as error:
            build.main(["--help"])
        self.assertEqual(error.exception.code, 0)

    def windows_fixture(self):
        temp = tempfile.TemporaryDirectory(prefix="gx-build-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve()
        rust_bin = root / "rust"
        native_bin = root / "MSVC tools"
        for directory in (rust_bin, native_bin):
            directory.mkdir()
        for path in (rust_bin / "rustc.exe", rust_bin / "cargo.exe",
                     native_bin / "cl.exe", native_bin / "link.exe",
                     native_bin / "vcvars64.bat"):
            path.touch()
            path.chmod(0o755)
        selected = "1.96.1-x86_64-pc-windows-msvc"
        report = {
            "ready": True,
            "toolchain": {"ready": True, "selected": selected,
                          "installed_msvc_toolchains": [selected],
                          "host": "x86_64-pc-windows-msvc",
                          "target": "x86_64-pc-windows-msvc", "target_installed": True,
                          "rustc": str(rust_bin / "rustc.exe"),
                          "cargo": str(rust_bin / "cargo.exe")},
            "tools": {"msvc": {"ready": True, "sdk_version": "10.0.26100.0",
                                "vcvars64": str(native_bin / "vcvars64.bat"),
                                "compiler": {"path": str(native_bin / "cl.exe")},
                                "linker": {"path": str(native_bin / "link.exe")}}},
        }
        activated = (f"Path={native_bin}{os.pathsep}{os.environ.get('PATH', '')}\n"
                     "INCLUDE=planned-include\nLIB=planned-lib\n"
                     "WindowsSDKVersion=10.0.26100.0\\\n")
        return root, report, activated

    def test_windows_environment_overrides_gnu_in_actual_child(self):
        root, report, activated = self.windows_fixture()
        parent = dict(os.environ, RUSTUP_TOOLCHAIN="1.96.1-x86_64-pc-windows-gnu",
                      RUSTC="gnu-rustc.exe", CARGO="gnu-cargo.exe",
                      CARGO_BUILD_TARGET="x86_64-pc-windows-gnu", RUSTUP_AUTO_INSTALL="1",
                      CARGO_TARGET_DIR=str(root / "target"), CARGO_HOME=str(root / "cargo"))
        original = parent.copy()
        with mock.patch.object(build.subprocess, "run", return_value=subprocess.CompletedProcess(
                [], 0, activated, "")) as activate:
            env = build.windows_environment(report, parent)
        self.assertEqual(parent, original)
        self.assertEqual(activate.call_args.kwargs["env"]["RUSTUP_AUTO_INSTALL"], "0")
        self.assertEqual(activate.call_args.kwargs["encoding"], "utf-16-le")
        self.assertIn(" /d /u /s /c ", activate.call_args.args[0])
        keys = ["RUSTUP_TOOLCHAIN", "RUSTUP_AUTO_INSTALL", "RUSTC", "CARGO",
                "CARGO_TARGET_DIR", "CARGO_HOME", "INCLUDE", "LIB",
                "CARGO_BUILD_TARGET", "CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER", "PATH"]
        result = subprocess.run([sys.executable, "-c",
                                 "import json,os; print(json.dumps({k:os.environ.get(k) for k in "
                                 + repr(keys) + "}))"], env=env, capture_output=True,
                                text=True, check=True)
        child = json.loads(result.stdout)
        for name in ("RUSTUP_TOOLCHAIN", "RUSTC", "CARGO"):
            field = {"RUSTUP_TOOLCHAIN": "selected", "RUSTC": "rustc", "CARGO": "cargo"}[name]
            self.assertEqual(child[name], report["toolchain"][field])
        self.assertEqual(child["RUSTUP_AUTO_INSTALL"], "0")
        self.assertIsNone(child["CARGO_BUILD_TARGET"])
        for name in ("CARGO_TARGET_DIR", "CARGO_HOME"):
            self.assertEqual(child[name], parent[name])
        self.assertEqual(child["INCLUDE"], "planned-include")
        self.assertEqual(child["LIB"], "planned-lib")
        self.assertEqual(child["CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER"],
                         report["tools"]["msvc"]["linker"]["path"])
        self.assertEqual(child["PATH"].split(os.pathsep)[0], str(root / "rust"))

    def test_windows_environment_rejects_unverified_toolchains(self):
        _, report, _ = self.windows_fixture()
        cases = [("ready", False), ("selected", "1.96.1-x86_64-pc-windows-gnu"),
                 ("installed_msvc_toolchains", []), ("target_installed", False),
                 ("host", "x86_64-pc-windows-gnu"), ("target", "aarch64-pc-windows-msvc")]
        for field, value in cases:
            with self.subTest(field=field), mock.patch.object(build.subprocess, "run") as run:
                invalid = copy.deepcopy(report)
                invalid["toolchain"][field] = value
                with self.assertRaises(build.BuildError):
                    build.windows_environment(invalid, {})
                run.assert_not_called()

    def test_windows_environment_rejects_missing_tools(self):
        _, report, _ = self.windows_fixture()
        report["toolchain"]["cargo"] += ".missing"
        with mock.patch.object(build.subprocess, "run") as run:
            with self.assertRaisesRegex(build.BuildError, "missing planner-selected.*cargo"):
                build.windows_environment(report, {})
            run.assert_not_called()

    def test_windows_environment_rejects_failed_activation(self):
        _, report, _ = self.windows_fixture()
        with mock.patch.object(build.subprocess, "run", return_value=subprocess.CompletedProcess(
                [], 1, "", "private environment output")):
            with self.assertRaisesRegex(build.BuildError, "activation failed"):
                build.windows_environment(report, {})

    def test_windows_environment_rejects_mismatched_native_environment(self):
        _, report, activated = self.windows_fixture()
        for output in (activated.replace("10.0.26100.0", "10.0.22621.0"),
                       activated.replace("INCLUDE=planned-include", "INCLUDE="),
                       "Path=\nINCLUDE=headers\nLIB=libraries\nWindowsSDKVersion=10.0.26100.0\n"):
            with self.subTest(output=output), mock.patch.object(
                    build.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, output, "")):
                with self.assertRaises(build.BuildError):
                    build.windows_environment(report, {})

    def test_windows_environment_rejects_command_metacharacters(self):
        _, report, _ = self.windows_fixture()
        with mock.patch.object(build.subprocess, "run") as run:
            with self.assertRaisesRegex(build.BuildError, "unsupported characters"):
                build.windows_environment(report, {"COMSPEC": "cmd.exe & echo unsafe"})
            run.assert_not_called()

    def local_fixture(self):
        temp = tempfile.TemporaryDirectory(prefix="gx-build-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve()
        local = root / ".local"
        build_root = local / "build"
        sources_root = local / "sources"
        build_root.mkdir(parents=True)
        sources_root.mkdir(parents=True)
        patcher = mock.patch.multiple(build, LOCAL_ROOT=local, LOCAL_BUILD_ROOT=build_root,
                                      LOCAL_SOURCES_ROOT=sources_root)
        patcher.start()
        self.addCleanup(patcher.stop)
        return root, build_root, sources_root

    def test_main_only_activates_windows_and_preserves_local_boundaries(self):
        for platform in ("windows", "linux"):
            with self.subTest(platform=platform):
                root, build_root, sources_root = self.local_fixture()
                work = build_root / ("run-win" if platform == "windows" else "run-lin")
                selected = {"RUSTUP_TOOLCHAIN": "selected-msvc", "RUSTUP_AUTO_INSTALL": "0"}
                checked = {"lock_digest": "fixture", "components": {}}
                with mock.patch.dict(os.environ, {}, clear=True), \
                        mock.patch.object(sources, "checkout", return_value=checked), \
                        mock.patch.object(build, "planner", return_value={}), \
                        mock.patch.object(build, "windows_environment", return_value=selected) as activate, \
                        mock.patch.object(build, "run") as run, redirect_stdout(io.StringIO()):
                    result = build.main(["--platform", platform, "--work-root", str(work),
                                         "--jobs", "4", "--offline"])
                self.assertEqual(result, 0)
                if platform == "windows":
                    activate.assert_called_once()
                    for call in run.call_args_list:
                        self.assertEqual(call.kwargs["env"], selected)
                else:
                    activate.assert_not_called()
                    self.assertNotIn("RUSTUP_TOOLCHAIN", run.call_args_list[0].kwargs["env"])
                    self.assertIn("--container", run.call_args_list[0].args[0])
                self.assertIn("--allow-dirty", run.call_args_list[1].args[0])
                self.assertIn("--allow-dirty", run.call_args_list[2].args[0])
                receipt = json.loads((work / "build-report.json").read_text(encoding="utf-8"))
                self.assertEqual(receipt["builder"], "local")
                self.assertIs(receipt["publishable"], False)

    def test_main_refuses_ci_identity_and_tokens_before_planning(self):
        for key in ("GITHUB_ACTIONS", "GH_TOKEN", "GITHUB_TOKEN"):
            with self.subTest(key=key), mock.patch.dict(os.environ, {key: "present"}, clear=True), \
                    mock.patch.object(build, "planner") as planner, redirect_stderr(io.StringIO()):
                self.assertEqual(build.main(["--platform", "windows", "--work-root", "unused"]), 1)
                planner.assert_not_called()

    def quiet_main(self, argv, report=None, env=None):
        with mock.patch.dict(os.environ, env or {}, clear=True), \
                mock.patch.object(sources, "checkout",
                                  return_value={"lock_digest": "fixture", "components": {}}), \
                mock.patch.object(build, "planner", return_value=report or {}), \
                mock.patch.object(build, "windows_environment", return_value={}), \
                mock.patch.object(build, "run"), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return build.main(argv)

    def test_work_root_must_be_a_new_run_under_local_build(self):
        root, build_root, _ = self.local_fixture()
        cases = [root / "elsewhere", root / ".local", build_root, build_root / "nested" / "run",
                 build_root / "bad name", build_root / "中文run", build_root / ("a" * 33)]
        for work in cases:
            with self.subTest(work=str(work)), mock.patch.dict(os.environ, {}, clear=True), \
                    mock.patch.object(build, "planner") as planner, redirect_stderr(io.StringIO()):
                self.assertEqual(build.main(["--platform", "linux", "--work-root", str(work), "--jobs", "4"]), 1)
                planner.assert_not_called()
        self.assertEqual(self.quiet_main(["--platform", "linux", "--work-root",
                                          str(build_root / "run1"), "--jobs", "4"]), 0)
        self.assertTrue((build_root / "run1" / "build-report.json").is_file())

    def test_sources_root_defaults_to_local_sources_and_rejects_outside(self):
        root, build_root, sources_root = self.local_fixture()
        for index, outside in enumerate((root / "outside", root / ".local", build_root / "run-src")):
            with self.subTest(sources=str(outside)), mock.patch.dict(os.environ, {}, clear=True), \
                    mock.patch.object(build, "planner") as planner, redirect_stderr(io.StringIO()):
                self.assertEqual(build.main(["--platform", "linux", "--work-root",
                                             str(build_root / f"run{index}"),
                                             "--sources-root", str(outside), "--jobs", "4"]), 1)
                planner.assert_not_called()
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(sources, "checkout",
                                  return_value={"lock_digest": "fixture", "components": {}}) as checkout, \
                mock.patch.object(build, "planner", return_value={}), \
                mock.patch.object(build, "run"), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(build.main(["--platform", "linux", "--work-root",
                                         str(build_root / "run-ok"), "--jobs", "4"]), 0)
        self.assertEqual(Path(checkout.call_args.args[1]), sources_root)

    def test_run_name_rules(self):
        for name in ("run1", "20261002-120000", "a_b-c", "x" * 32):
            self.assertEqual(build.run_name(name), name)
        for name in ("", "has space", "run.1", ".hidden", "-lead", "中文", "x" * 33, "CON", "com1", "PRN"):
            with self.subTest(name=name), self.assertRaises(build.BuildError):
                build.run_name(name)

    def test_local_path_enforces_containment_links_and_length(self):
        root, build_root, _ = self.local_fixture()
        inside = build_root / "run1"
        self.assertEqual(build.local_path(inside, build_root, "work-root"), inside)
        for path in (root / "elsewhere", build_root / ".." / "run1", build_root / ("x" * 200)):
            with self.subTest(path=str(path)), self.assertRaises(build.BuildError):
                build.local_path(path, build_root, "work-root")

    def test_local_paths_reject_symlink_escapes(self):
        root, build_root, _ = self.local_fixture()
        outside = root / "outside"
        outside.mkdir()
        link = build_root / "linked-run"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            if os.name != "nt":
                self.skipTest("directory symlinks unavailable")
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                                    capture_output=True, timeout=20)
            if result.returncode:
                self.skipTest("directory symlinks and junctions unavailable")
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(build, "planner") as planner, redirect_stderr(io.StringIO()):
            self.assertEqual(build.main(["--platform", "linux", "--work-root", str(link), "--jobs", "4"]), 1)
            planner.assert_not_called()

    def test_existing_work_root_is_never_reused(self):
        _, build_root, _ = self.local_fixture()
        work = build_root / "run1"
        work.mkdir()
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(build, "planner") as planner, redirect_stderr(io.StringIO()):
            self.assertEqual(build.main(["--platform", "linux", "--work-root", str(work), "--jobs", "4"]), 1)
            planner.assert_not_called()

    def test_planner_selected_paths_must_stay_inside_the_run(self):
        root, build_root, _ = self.local_fixture()
        reports = [
            {"paths": {"build_root": str(root / "gx-b"), "components": {}}},
            {"paths": {"build_root": str(build_root / "run2"),
                       "components": {"wezterm": {"paths": {"cargo_target": str(root / "target")}}}}},
        ]
        for index, report in enumerate(reports):
            with self.subTest(index=index):
                self.assertEqual(self.quiet_main(["--platform", "linux", "--work-root",
                                                  str(build_root / f"run{index}"), "--jobs", "4"],
                                                 report=report), 1)
        inside = {"paths": {"build_root": str(build_root / "run-ok"),
                            "components": {"ohmyzsh": {"paths": {"cache": str(build_root / "run-ok" / "c")}}}}}
        self.assertEqual(self.quiet_main(["--platform", "linux", "--work-root",
                                          str(build_root / "run-ok"), "--jobs", "4"], report=inside), 0)

    def test_preset_local_build_root_must_match_the_run(self):
        root, build_root, _ = self.local_fixture()
        with mock.patch.dict(os.environ, {"GX_LOCAL_BUILD_ROOT": str(root / "other")}, clear=True), \
                mock.patch.object(build, "planner") as planner, redirect_stderr(io.StringIO()):
            self.assertEqual(build.main(["--platform", "linux", "--work-root",
                                         str(build_root / "run1"), "--jobs", "4"]), 1)
            planner.assert_not_called()
        work = build_root / "run2"
        self.assertEqual(self.quiet_main(["--platform", "linux", "--work-root", str(work), "--jobs", "4"],
                                         env={"GX_LOCAL_BUILD_ROOT": str(work)}), 0)

    def test_stage_receives_build_root_matching_its_parent_and_stays_unpublishable(self):
        _, build_root, sources_root = self.local_fixture()
        work = build_root / "run1"
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(sources, "checkout",
                                  return_value={"lock_digest": "fixture", "components": {}}), \
                mock.patch.object(build, "planner", return_value={}), \
                mock.patch.object(build, "run") as run, \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(build.main(["--platform", "linux", "--work-root", str(work), "--jobs", "4"]), 0)
        stage_call = run.call_args_list[1]
        stage_work = Path(stage_call.args[0][3])
        self.assertEqual(stage_work.parent, work)
        self.assertEqual(stage_call.kwargs["env"]["GX_LOCAL_BUILD_ROOT"], str(work))
        self.assertTrue(work.is_relative_to(build_root))
        receipt = json.loads((work / "build-report.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["builder"], "local")
        self.assertIs(receipt["publishable"], False)
        self.assertEqual(receipt["work_root"], str(work))
        self.assertEqual(receipt["sources_root"], str(sources_root))


if __name__ == "__main__":
    unittest.main()

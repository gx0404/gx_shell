"""Source contract tests use temporary Git remotes, never component source trees."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import gx_shell_sources as sources

SCRIPT = Path(__file__).with_name("gx_shell_sources.py")
SECRET = "GX_SOURCE_SECRET_MUST_NOT_LEAK"


def example_lock():
    return {"schema": 1, "components": {
        name: {"repository": f"gx0404/{name}", "branch": "gx", "revision": str(index) * 40}
        for index, name in enumerate(sources.COMPONENTS, 1)},
        "toolchains": {"rust": "fixture-only"}, "metadata": {"preserve": True}}


class LockTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="gx-lock-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "components.lock.json"

    def write(self, value):
        self.path.write_text(json.dumps(value) + "\n", encoding="utf-8")

    def test_complete_lock_and_extra_top_level_metadata_are_preserved(self):
        lock = example_lock()
        lock["components"]["herdr"]["revision"] = "ABCDEF" * 6 + "ABCD"
        self.write(lock)
        self.assertEqual(sources.load_lock(self.path), lock)

    def test_digest_is_of_raw_bytes_not_normalized_json(self):
        lock = example_lock()
        first = json.dumps(lock).encode()
        second = json.dumps(lock, indent=3).encode() + b"\r\n"
        self.path.write_bytes(first)
        digest = sources.lock_digest(str(self.path))
        self.assertEqual(digest, hashlib.sha256(first).hexdigest())
        self.path.write_bytes(second)
        self.assertNotEqual(sources.lock_digest(self.path), digest)
        self.assertEqual(sources.lock_digest(self.path), hashlib.sha256(second).hexdigest())
        self.assertEqual(sources.load_lock(self.path), lock)

    def test_strict_core_contract(self):
        cases = [[], None, {"schema": 1}, {"schema": 1, "components": []}]
        for value in (True, 1.0, 2, "1", None):
            lock = example_lock()
            lock["schema"] = value
            cases.append(lock)
        for name in sources.COMPONENTS:
            lock = example_lock()
            del lock["components"][name]
            cases.append(lock)
        lock = example_lock()
        lock["components"]["unexpected"] = copy.deepcopy(lock["components"]["herdr"])
        cases.append(lock)
        for field, values in {
            "repository": ["another/herdr", "https://github.com/gx0404/herdr.git", "gx0404/wezterm", None],
            "branch": ["main", "refs/heads/gx", None],
            "revision": ["gx", "main", "1" * 39, "1" * 41, "z" * 40, "1" * 40 + "\n", 1, None],
        }.items():
            for value in values:
                lock = example_lock()
                lock["components"]["herdr"][field] = value
                cases.append(lock)
            lock = example_lock()
            del lock["components"]["herdr"][field]
            cases.append(lock)
        for value in (None, [], "gx"):
            lock = example_lock()
            lock["components"]["herdr"] = value
            cases.append(lock)
        lock = example_lock()
        lock["components"]["herdr"]["url"] = "untrusted"
        cases.append(lock)
        for index, value in enumerate(cases):
            with self.subTest(case=index):
                self.write(value)
                with self.assertRaises(sources.SourceError):
                    sources.load_lock(self.path)

    def test_invalid_json_duplicate_keys_and_constants_are_rejected_without_echo(self):
        for raw in (b"{broken", b"\xff", b'{"schema":1,"schema":1}',
                    b'{"schema":NaN}', b'{"schema":Infinity}', SECRET.encode()):
            with self.subTest(raw=raw):
                self.path.write_bytes(raw)
                with self.assertRaises(sources.SourceError) as error:
                    sources.load_lock(self.path)
                self.assertNotIn(SECRET, str(error.exception))

    def test_check_is_offline_and_does_not_change_lock(self):
        self.write(example_lock())
        before = self.path.read_bytes()
        with mock.patch.object(sources.subprocess, "run", side_effect=AssertionError("Git must not run")):
            result = sources.check(self.path)
        self.assertEqual(result["lock_digest"], hashlib.sha256(before).hexdigest())
        self.assertEqual(self.path.read_bytes(), before)

    def test_missing_lock_is_not_created(self):
        for operation in (sources.load_lock, sources.lock_digest, sources.update):
            with self.subTest(operation=operation.__name__), self.assertRaises(sources.SourceError):
                operation(self.path)
        self.assertFalse(self.path.exists())

    def test_offline_missing_checkout_never_runs_git_or_creates_output(self):
        self.write(example_lock())
        output = self.path.parent / "sources"
        with mock.patch.object(sources.subprocess, "run", side_effect=AssertionError("Git must not run")):
            with self.assertRaisesRegex(sources.SourceError, "offline"):
                sources.checkout(self.path, output, offline=True)
        self.assertFalse(output.exists())

    def test_component_api_cannot_escape_output(self):
        self.write(example_lock())
        for name in ("../outside", "/outside", "C:\\outside", "unknown"):
            with self.subTest(name=name), self.assertRaises(sources.SourceError):
                sources.checkout(self.path, self.path.parent / "out", [name])


@unittest.skipUnless(shutil.which("git"), "Git is required for isolated end-to-end source tests")
class GitSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix="gx-source-remotes-")
        cls.addClassCleanup(cls.fixture.cleanup)
        cls.fixture_root = Path(cls.fixture.name)
        cls.remotes = cls.fixture_root / "remotes"
        cls.remotes.mkdir()
        cls.global_config = cls.fixture_root / "gitconfig"
        cls.global_config.write_text(
            '[protocol "file"]\n\tallow = always\n'
            f'[url "{cls.remotes.as_uri()}/"]\n\tinsteadOf = https://github.com/gx0404/\n'
            '[user]\n\tname = Source Fixture\n\temail = fixture@example.invalid\n'
            '[core]\n\tautocrlf = false\n[commit]\n\tgpgsign = false\n', encoding="utf-8")
        cls.fixture_env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
        cls.fixture_env.update(GIT_CONFIG_GLOBAL=str(cls.global_config), GIT_CONFIG_NOSYSTEM="1",
                               GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
        cls.revisions = {}
        cls.heads = {}
        for name in ("leaf", "vendor", *sources.COMPONENTS):
            repo = cls.remotes / f"{name}.git"
            repo.mkdir()
            cls.git_at(repo, "init", "--quiet", "--initial-branch=gx", "--template=")
            (repo / ".gitattributes").write_bytes(b"*.txt text\n")
            (repo / "tracked.txt").write_bytes(f"{name} locked contents\n".encode("utf-8"))
            if name == "ohmyzsh":
                notices = repo / "scripts/packaging/notices/herdr-build"
                notices.mkdir(parents=True)
                (notices / "LICENSE").write_bytes(b"Fixture upstream license\nRedistribution permitted.\n")
            if name == "vendor":
                cls.git_at(repo, "submodule", "add", "--quiet",
                           "https://github.com/gx0404/leaf.git", "nested/leaf")
            if name == "wezterm":
                cls.git_at(repo, "submodule", "add", "--quiet",
                           "https://github.com/gx0404/vendor.git", "deps/vendor module")
            cls.git_at(repo, "add", ".")
            cls.git_at(repo, "commit", "--quiet", "-m", f"{name} locked commit")
            cls.revisions[name] = cls.git_at(repo, "rev-parse", "HEAD")
            if name in sources.COMPONENTS:
                (repo / "latest.txt").write_text(f"{name} newer gx head\n", encoding="utf-8")
                cls.git_at(repo, "add", ".")
                cls.git_at(repo, "commit", "--quiet", "-m", f"{name} later commit")
            cls.heads[name] = cls.git_at(repo, "rev-parse", "HEAD")
        herdr = cls.remotes / "herdr.git"
        cls.git_at(herdr, "checkout", "--quiet", "--orphan", "unrelated")
        cls.git_at(herdr, "commit", "--quiet", "-m", "unrelated root")
        cls.unrelated = cls.git_at(herdr, "rev-parse", "HEAD")
        cls.git_at(herdr, "checkout", "--quiet", "gx")
        cls.blob = cls.git_at(herdr, "rev-parse", "HEAD:tracked.txt")
        cls.git_at(herdr, "tag", "-a", "fixture-tag", "-m", "annotated tag")
        cls.tag = cls.git_at(herdr, "rev-parse", "fixture-tag")

    @classmethod
    def git_at(cls, path, *args, env=None, ok=True):
        result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *args], cwd=path,
                                env=env or cls.fixture_env, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=90)
        if ok and result.returncode:
            raise AssertionError(f"fixture Git failed: {result.stderr}")
        return result.stdout.strip() if ok else result

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="gx-source-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = self.root / "gitconfig"
        shutil.copyfile(self.global_config, self.config)
        self.env = {**self.fixture_env, "GIT_CONFIG_GLOBAL": str(self.config)}
        self.lock = example_lock()
        for name in sources.COMPONENTS:
            self.lock["components"][name]["revision"] = self.revisions[name]
        self.lock_path = self.root / "components.lock.json"
        self.write_lock()
        self.output = self.root / "sources"

    def write_lock(self):
        self.lock_path.write_text(json.dumps(self.lock, indent=2) + "\n", encoding="utf-8")

    def cli(self, command, *args, ok=True, env=None, cwd=None):
        result = subprocess.run([sys.executable, str(SCRIPT.resolve()), command, "--lock",
                                 str(self.lock_path), *map(str, args)], cwd=cwd or self.root,
                                env=env or self.env, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=120)
        self.assertNotIn(SECRET, result.stdout + result.stderr)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout.splitlines()[-1])
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("Traceback", result.stderr)
        return result

    def clone(self, name="herdr", output=None):
        output = output or self.output
        self.cli("checkout", "--output", output, "--component", name)
        return output / name

    def coordinator(self, path=None):
        repo = path or self.root / "coordinator"
        repo.mkdir(parents=True, exist_ok=True)
        self.git_at(repo, "init", "--quiet", "--initial-branch=main", "--template=")
        (repo / "coordinator.txt").write_text("coordinator identity\n", encoding="utf-8")
        self.git_at(repo, "add", "coordinator.txt")
        self.git_at(repo, "commit", "--quiet", "-m", "coordinator")
        return repo, self.git_at(repo, "rev-parse", "HEAD")

    def directory_link(self, path, target):
        try:
            path.symlink_to(target, target_is_directory=True)
        except OSError:
            if os.name != "nt":
                self.skipTest("directory symlinks unavailable")
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(path), str(target)],
                                    capture_output=True, timeout=20)
            if result.returncode:
                self.skipTest("directory symlinks and junctions unavailable")
        self.addCleanup(lambda: path.unlink() if path.is_symlink() else path.rmdir())

    def test_cli_default_checkout_four_independent_revisions_and_recursive_submodules(self):
        coordinator, sha = self.coordinator()
        output = coordinator / "build/sources"
        before = self.lock_path.read_bytes()
        result = self.cli("checkout", "--output", output, cwd=coordinator)
        self.assertEqual(set(result["components"]), set(sources.COMPONENTS))
        self.assertEqual(result["lock_digest"], hashlib.sha256(before).hexdigest())
        self.assertEqual(len({sha, *(entry["revision"] for entry in result["components"].values())}), 4)
        for name, entry in result["components"].items():
            repo = Path(entry["path"])
            self.assertEqual(repo, output / name)
            self.assertTrue((repo / ".git").is_dir())
            self.assertEqual(self.git_at(repo, "rev-parse", "HEAD"), self.revisions[name])
            self.assertEqual(self.git_at(repo, "symbolic-ref", "-q", "HEAD", ok=False).returncode, 1)
            self.assertEqual(self.git_at(repo, "config", "--local", "--get", "remote.origin.url"),
                             f"https://github.com/gx0404/{name}.git")
            self.assertFalse((repo / "latest.txt").exists())
        vendor = output / "wezterm/deps/vendor module"
        leaf = vendor / "nested/leaf"
        self.assertEqual(self.git_at(vendor, "rev-parse", "HEAD"), self.revisions["vendor"])
        self.assertEqual(self.git_at(leaf, "rev-parse", "HEAD"), self.revisions["leaf"])
        self.assertEqual(self.cli("checkout", "--output", output, "--offline"), result)
        self.assertEqual(self.git_at(coordinator, "rev-parse", "HEAD"), sha)
        self.assertEqual(self.lock_path.read_bytes(), before)

    def blob_bytes(self, repo, revision, relative):
        result = subprocess.run(["git", "cat-file", "blob", f"{revision}:{relative}"],
                                cwd=repo, env=self.env, capture_output=True, timeout=90)
        self.assertEqual(result.returncode, 0)
        return result.stdout

    def test_global_autocrlf_cannot_change_new_checkout_material_bytes(self):
        self.git_at(self.root, "config", "--file", str(self.config), "core.autocrlf", "true")
        self.git_at(self.root, "config", "--file", str(self.config), "core.eol", "crlf")
        global_before = self.config.read_bytes()
        lock_before = self.lock_path.read_bytes()
        notice = "scripts/packaging/notices/herdr-build/LICENSE"
        control = self.root / "unfixed-clone"
        self.git_at(self.root, "clone", "--quiet", "--no-checkout",
                    "https://github.com/gx0404/ohmyzsh.git", str(control), env=self.env)
        self.git_at(control, "checkout", "--quiet", "--detach", self.revisions["ohmyzsh"], env=self.env)
        upstream = self.blob_bytes(control, self.revisions["ohmyzsh"], notice)
        self.assertNotIn(b"\r\n", upstream)
        self.assertEqual((control / notice).read_bytes(), upstream.replace(b"\n", b"\r\n"))
        self.assertNotEqual(hashlib.sha256((control / notice).read_bytes()).hexdigest(),
                            hashlib.sha256(upstream).hexdigest())

        result = self.cli("checkout", "--output", self.output)
        repos = [(self.output / name, self.revisions[name]) for name in sources.COMPONENTS]
        vendor = self.output / "wezterm/deps/vendor module"
        repos.extend(((vendor, self.revisions["vendor"]), (vendor / "nested/leaf", self.revisions["leaf"])))
        for repo, revision in repos:
            with self.subTest(repo=repo.name):
                self.assertEqual(self.git_at(repo, "config", "--local", "core.autocrlf"), "false")
                self.assertEqual(self.git_at(repo, "config", "--local", "core.eol"), "lf")
                blob = self.blob_bytes(repo, revision, "tracked.txt")
                self.assertNotIn(b"\r\n", blob)
                self.assertEqual((repo / "tracked.txt").read_bytes(), blob)
        material = (self.output / "ohmyzsh" / notice).read_bytes()
        self.assertEqual(material, upstream)
        self.assertEqual(hashlib.sha256(material).hexdigest(), hashlib.sha256(upstream).hexdigest())
        self.assertEqual(self.cli("checkout", "--output", self.output, "--offline"), result)
        self.assertEqual(self.config.read_bytes(), global_before)
        self.assertEqual(self.lock_path.read_bytes(), lock_before)

    def test_global_autocrlf_never_normalizes_existing_user_edits(self):
        self.git_at(self.root, "config", "--file", str(self.config), "core.autocrlf", "true")
        repo = self.clone("ohmyzsh")
        self.git_at(repo, "config", "--local", "core.autocrlf", "true")
        self.git_at(repo, "config", "--local", "core.eol", "crlf")
        notice = repo / "scripts/packaging/notices/herdr-build/LICENSE"
        user_bytes = b"Manually edited license.\r\nDo not normalize these user bytes.\r\n"
        notice.write_bytes(user_bytes)
        protected = (self.config, self.lock_path, repo / ".git/config", repo / ".git/index")
        before = {path: path.read_bytes() for path in protected}
        for flags in ((), ("--offline",)):
            with self.subTest(offline=bool(flags)):
                result = self.cli("checkout", "--output", self.output, "--component", "ohmyzsh", *flags, ok=False)
                self.assertIn("dirty", result.stderr)
                self.assertEqual(notice.read_bytes(), user_bytes)
                self.assertEqual({path: path.read_bytes() for path in protected}, before)

    def test_repeated_component_selection_and_offline_reuse(self):
        result = self.cli("checkout", "--output", self.output, "--component", "herdr",
                          "--component", "ohmyzsh", "--component", "herdr")
        self.assertEqual(set(result["components"]), {"herdr", "ohmyzsh"})
        self.assertFalse((self.output / "wezterm").exists())
        self.assertEqual(self.cli("checkout", "--output", self.output, "--component", "herdr",
                                  "--component", "ohmyzsh", "--offline"), result)

    def test_offline_reuse_disables_protocols_and_never_fetches(self):
        self.clone()
        original = subprocess.run

        def local_git_only(command, **kwargs):
            self.assertFalse({"fetch", "clone", "ls-remote", "submodule"}.intersection(command))
            self.assertEqual(kwargs["env"]["GIT_ALLOW_PROTOCOL"], "")
            return original(command, **kwargs)

        with mock.patch.dict(os.environ, self.env, clear=True):
            with mock.patch.object(sources.subprocess, "run", side_effect=local_git_only):
                result = sources.checkout(self.lock_path, self.output, ["herdr"], offline=True)
        self.assertEqual(result["components"]["herdr"]["revision"], self.revisions["herdr"])

    def test_global_worktree_cannot_redirect_new_checkout(self):
        outer, sha = self.coordinator()
        before = (outer / ".git/index").read_bytes()
        with self.config.open("a", encoding="utf-8") as stream:
            stream.write(f'[core]\n\tworktree = {outer.as_posix()}\n')
        result = self.cli("checkout", "--output", self.output, "--component", "herdr")
        repo = Path(result["components"]["herdr"]["path"])
        self.assertEqual(Path(self.git_at(repo, "rev-parse", "--show-toplevel")).resolve(), repo.resolve())
        self.assertEqual(self.git_at(outer, "rev-parse", "HEAD"), sha)
        self.assertEqual((outer / ".git/index").read_bytes(), before)

    def test_outer_git_environment_is_not_inherited(self):
        outer, sha = self.coordinator()
        env = {**self.env, "GIT_DIR": str(outer / ".git"), "GIT_WORK_TREE": str(outer),
               "GIT_COMMON_DIR": str(outer / ".git"), "GIT_INDEX_FILE": str(outer / ".git/index"),
               "GIT_OBJECT_DIRECTORY": str(outer / ".git/objects"),
               "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(outer / ".git/objects"),
               "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.worktree",
               "GIT_CONFIG_VALUE_0": str(outer), "GIT_TRACE": "1"}
        before = (outer / ".git/index").read_bytes()
        self.cli("checkout", "--output", self.output, "--component", "herdr", env=env, cwd=outer)
        self.assertEqual(self.git_at(outer, "rev-parse", "HEAD"), sha)
        self.assertEqual((outer / ".git/index").read_bytes(), before)
        self.assertEqual(self.git_at(outer, "status", "--porcelain"), "")

    def test_fake_directory_in_outer_repository_is_rejected(self):
        outer, sha = self.coordinator(self.output)
        (outer / "herdr").mkdir()
        result = self.cli("checkout", "--output", outer, "--component", "herdr", ok=False)
        self.assertIn("own .git", result.stderr)
        self.assertEqual(self.git_at(outer, "rev-parse", "HEAD"), sha)
        self.assertEqual(list((outer / "herdr").iterdir()), [])

    def test_gitfile_to_another_repository_is_rejected(self):
        outer, sha = self.coordinator()
        child = self.output / "herdr"
        child.mkdir(parents=True)
        (child / ".git").write_text(f"gitdir: {outer / '.git'}\n", encoding="utf-8")
        self.cli("checkout", "--output", self.output, "--component", "herdr", ok=False)
        self.assertEqual(self.git_at(outer, "rev-parse", "HEAD"), sha)

    def test_all_existing_targets_are_checked_before_creating_any_clones(self):
        (self.output / "ohmyzsh").mkdir(parents=True)
        self.cli("checkout", "--output", self.output, ok=False)
        self.assertFalse((self.output / "herdr").exists())

    def test_wrong_or_credential_bearing_origin_is_refused_without_echo(self):
        repo = self.clone()
        for url in ("https://github.com/other/herdr.git", f"https://user:{SECRET}@github.com/gx0404/herdr.git"):
            with self.subTest(url_kind="credentials" if SECRET in url else "other"):
                self.git_at(repo, "remote", "set-url", "origin", url)
                self.cli("checkout", "--output", self.output, "--component", "herdr", ok=False)
        self.assertEqual(self.git_at(repo, "rev-parse", "HEAD"), self.revisions["herdr"])

    def test_tracked_untracked_and_staged_changes_are_not_overwritten(self):
        for kind in ("tracked", "untracked", "staged"):
            with self.subTest(kind=kind):
                output = self.root / kind
                repo = self.clone(output=output)
                changed = repo / ("new.txt" if kind == "untracked" else "tracked.txt")
                changed.write_text("user changes\n", encoding="utf-8")
                if kind == "staged":
                    self.git_at(repo, "add", "tracked.txt")
                self.cli("checkout", "--output", output, "--component", "herdr", ok=False)
                self.assertEqual(changed.read_text(encoding="utf-8"), "user changes\n")

    def test_wrong_head_and_attached_head_are_not_reset(self):
        repo = self.clone()
        self.git_at(repo, "switch", "--quiet", "-c", "gx")
        self.cli("checkout", "--output", self.output, "--component", "herdr", ok=False)
        self.assertEqual(self.git_at(repo, "symbolic-ref", "--short", "HEAD"), "gx")
        self.git_at(repo, "fetch", "--quiet", "origin", self.heads["herdr"], env=self.env)
        self.git_at(repo, "checkout", "--quiet", "--detach", self.heads["herdr"] )
        self.cli("checkout", "--output", self.output, "--component", "herdr", ok=False)
        self.assertEqual(self.git_at(repo, "rev-parse", "HEAD"), self.heads["herdr"])

    def test_index_flags_cannot_hide_dirty_files(self):
        for flag in ("--assume-unchanged", "--skip-worktree"):
            with self.subTest(flag=flag):
                output = self.root / flag[2:]
                repo = self.clone(output=output)
                self.git_at(repo, "update-index", flag, "tracked.txt")
                (repo / "tracked.txt").write_text("hidden user edit\n", encoding="utf-8")
                self.cli("checkout", "--output", output, "--component", "herdr", ok=False)
                self.assertEqual((repo / "tracked.txt").read_text(), "hidden user edit\n")

    def test_shared_objects_are_refused(self):
        repo = self.clone()
        (repo / ".git/objects/info/alternates").write_text(
            str(self.remotes / "herdr.git/.git/objects") + "\n", encoding="utf-8")
        self.cli("checkout", "--output", self.output, "--component", "herdr", ok=False)

    def test_root_child_and_ancestor_symlinks_or_junctions_are_refused(self):
        outside, sha = self.coordinator()
        self.output.mkdir()
        for label, link, output in (("root", self.root / "linked", self.root / "linked"),
                                    ("child", self.output / "herdr", self.output),
                                    ("ancestor", self.root / "ancestor", self.root / "ancestor/nested")):
            with self.subTest(kind=label):
                self.directory_link(link, outside)
                self.cli("checkout", "--output", output, "--component", "herdr", ok=False)
        self.assertEqual(self.git_at(outside, "rev-parse", "HEAD"), sha)
        self.assertFalse((outside / "nested").exists())

    def test_symlinked_git_metadata_is_refused(self):
        outside, sha = self.coordinator()
        child = self.output / "herdr"
        child.mkdir(parents=True)
        self.directory_link(child / ".git", outside / ".git")
        self.cli("checkout", "--output", self.output, "--component", "herdr", ok=False)
        self.assertEqual(self.git_at(outside, "rev-parse", "HEAD"), sha)

    def test_output_traversal_and_existing_file_are_refused(self):
        self.cli("checkout", "--output", self.output / "../outside", "--component", "herdr", ok=False)
        self.output.mkdir()
        target = self.output / "herdr"
        target.write_text("user file", encoding="utf-8")
        self.cli("checkout", "--output", self.output, "--component", "herdr", ok=False)
        self.assertEqual(target.read_text(), "user file")

    def test_missing_nested_submodule_is_offline_error_and_online_initializes_it(self):
        repo = self.clone("wezterm")
        vendor = repo / "deps/vendor module"
        self.git_at(vendor, "submodule", "deinit", "--force", "--all")
        self.cli("checkout", "--output", self.output, "--component", "wezterm", "--offline", ok=False)
        self.cli("checkout", "--output", self.output, "--component", "wezterm")
        self.assertEqual(self.git_at(vendor / "nested/leaf", "rev-parse", "HEAD"), self.revisions["leaf"])

    def test_dirty_recursive_submodule_is_preserved(self):
        repo = self.clone("wezterm")
        changed = repo / "deps/vendor module/nested/leaf/tracked.txt"
        changed.write_text("nested user edit\n", encoding="utf-8")
        self.cli("checkout", "--output", self.output, "--component", "wezterm", ok=False)
        self.assertEqual(changed.read_text(), "nested user edit\n")

    def test_submodule_gitfile_cannot_point_to_external_repository(self):
        repo = self.clone("wezterm")
        outside, sha = self.coordinator()
        marker = repo / "deps/vendor module/.git"
        marker.unlink()
        marker.write_text(f"gitdir: {outside / '.git'}\n", encoding="utf-8")
        self.cli("checkout", "--output", self.output, "--component", "wezterm", ok=False)
        self.assertEqual(self.git_at(outside, "rev-parse", "HEAD"), sha)

    def test_remote_check_accepts_ancestors_and_never_changes_lock(self):
        for name in sources.COMPONENTS:
            self.assertNotEqual(self.revisions[name], self.heads[name])
        outer, sha = self.coordinator()
        self.git_at(outer, "remote", "add", "origin",
                    f"https://user:{SECRET}@github.com/gx0404/gx_shell.git")
        config_before = (outer / ".git/config").read_bytes()
        env = {**self.env, "GIT_DIR": str(outer / ".git"), "GIT_WORK_TREE": str(outer),
               "GITHUB_TOKEN": SECRET, "GH_TOKEN": SECRET, "GIT_TRACE": "1"}
        before = self.lock_path.read_bytes()
        result = self.cli("check", "--require-remote", env=env, cwd=outer)
        self.assertEqual(result["components"], self.lock["components"])
        self.assertEqual(self.lock_path.read_bytes(), before)
        self.assertEqual((outer / ".git/config").read_bytes(), config_before)
        self.assertEqual(self.git_at(outer, "rev-parse", "HEAD"), sha)

    def test_commit_existence_and_gx_ancestry_are_separate(self):
        self.lock["components"]["herdr"]["revision"] = self.unrelated
        self.write_lock()
        self.cli("check")
        self.clone()
        result = self.cli("check", "--require-remote", ok=False)
        self.assertIn("not an ancestor of gx", result.stderr)

    def test_tags_blobs_and_missing_objects_are_not_commit_revisions(self):
        for label, revision in (("blob", self.blob), ("tag", self.tag), ("missing", "f" * 40)):
            with self.subTest(kind=label):
                self.lock["components"]["herdr"]["revision"] = revision
                self.write_lock()
                self.cli("checkout", "--output", self.output, "--component", "herdr", ok=False)
                self.assertFalse((self.output / "herdr").exists())
                self.assertEqual(list(self.output.iterdir()), [])

    def remove_remote_gx(self):
        isolated = self.root / "isolated.git"
        shutil.copytree(self.remotes / "herdr.git", isolated)
        self.git_at(isolated, "update-ref", "-d", "refs/heads/gx")
        with self.config.open("a", encoding="utf-8") as stream:
            stream.write(f'[url "{isolated.as_uri()}"]\n\tinsteadOf = https://github.com/gx0404/herdr.git\n')

    def test_checkout_does_not_require_or_reresolve_floating_gx(self):
        self.remove_remote_gx()
        self.clone()
        self.cli("check", "--require-remote", ok=False)

    def test_explicit_update_preserves_metadata_and_writes_all_heads_atomically(self):
        result = self.cli("update")
        updated = sources.load_lock(self.lock_path)
        for name in sources.COMPONENTS:
            self.assertEqual(updated["components"][name]["revision"], self.heads[name])
        self.assertEqual(updated["metadata"], self.lock["metadata"])
        self.assertEqual(updated["toolchains"], self.lock["toolchains"])
        self.assertNotIn("lock_digest", updated)
        self.assertNotIn("digest", updated)
        self.assertEqual(result["lock_digest"], sources.lock_digest(self.lock_path))
        self.assertEqual(list(self.root.glob(".components.lock.json-*")), [])

    def test_missing_remote_gx_never_partially_updates_lock(self):
        self.remove_remote_gx()
        before = self.lock_path.read_bytes()
        self.cli("update", ok=False)
        self.assertEqual(self.lock_path.read_bytes(), before)

    def test_failed_atomic_replace_preserves_original_and_cleans_temporary_file(self):
        before = self.lock_path.read_bytes()
        with mock.patch.dict(os.environ, self.env, clear=True):
            with mock.patch.object(sources.os, "replace", side_effect=OSError("replace denied")):
                with self.assertRaises(OSError):
                    sources.update(self.lock_path)
        self.assertEqual(self.lock_path.read_bytes(), before)
        self.assertEqual(list(self.root.glob(".components.lock.json-*")), [])

    def test_concurrent_lock_edit_is_not_overwritten(self):
        original = sources._remote_head
        replacement = json.dumps({**self.lock, "user_edit": True}).encode()

        def fetch_and_edit(path, entry):
            result = original(path, entry)
            self.lock_path.write_bytes(replacement)
            return result

        with mock.patch.dict(os.environ, self.env, clear=True):
            with mock.patch.object(sources, "_remote_head", side_effect=fetch_and_edit):
                with self.assertRaisesRegex(sources.SourceError, "changed during update"):
                    sources.update(self.lock_path)
        self.assertEqual(self.lock_path.read_bytes(), replacement)
        self.assertEqual(list(self.root.glob(".components.lock.json-*")), [])

    def test_transport_output_does_not_echo_credentials_or_tokens(self):
        missing = (self.root / SECRET / "missing.git").as_uri()
        with self.config.open("a", encoding="utf-8") as stream:
            stream.write(f'[url "{missing}"]\n\tinsteadOf = https://github.com/gx0404/herdr.git\n')
        self.cli("check", "--require-remote", ok=False)
        self.cli("checkout", "--output", self.output, "--component", "herdr", ok=False)


if __name__ == "__main__":
    unittest.main()

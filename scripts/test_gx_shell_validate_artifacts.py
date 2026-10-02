import contextlib
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import unittest
from unittest import mock
import warnings
import zipfile

import gx_shell_package as package
import gx_shell_validate_artifacts as validation
import test_gx_shell_package as fixtures

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 1, 15, tzinfo=timezone.utc)
VALIDATOR = {"repository": validation.REPOSITORY, "sha": "f" * 40, "run_id": 456, "run_attempt": 1}


def source_fixture(raw_lock=b"locked bytes\n"):
    workflow_text = (ROOT / validation.WORKFLOW).read_text(encoding="utf-8")
    run = {"id": 123, "head_sha": fixtures.SHA, "run_attempt": 1, "status": "completed", "conclusion": "failure",
           "event": "workflow_dispatch", "path": validation.WORKFLOW, "workflow_id": 9,
           "repository": {"full_name": validation.REPOSITORY, "id": 7},
           "head_repository": {"full_name": validation.REPOSITORY, "id": 7}, "pull_requests": []}
    workflow = {"id": 9, "path": validation.WORKFLOW}
    jobs = [{"id": 10, "name": "prepare", "run_id": 123, "run_attempt": 1, "head_sha": fixtures.SHA,
             "status": "completed", "conclusion": "success", "steps": []}]
    artifacts = []
    for index, platform in enumerate(validation.BUILD_STEPS):
        number, upload = validation.upload_step(workflow_text, platform)
        jobs.append({"id": 11 + index, "name": "package-" + platform, "run_id": 123, "run_attempt": 1,
                     "head_sha": fixtures.SHA, "status": "completed", "conclusion": "failure", "steps": [
                         {"number": number, "name": validation.BUILD_STEPS[platform], "status": "completed",
                          "conclusion": "success", "completed_at": "2026-10-01T10:11:00Z"},
                         {"number": number + 1, "name": upload, "status": "completed", "conclusion": "success",
                          "started_at": "2026-10-01T10:11:01Z", "completed_at": "2026-10-01T10:12:00Z"}]})
        artifacts.append({"id": 20 + index, "name": "release-" + platform, "size_in_bytes": 10,
                          "digest": "sha256:" + "d" * 64, "expired": False,
                          "created_at": "2026-10-01T10:11:30Z", "expires_at": "2099-10-15T10:12:00Z",
                          "workflow_run": {"id": 123, "head_sha": fixtures.SHA, "repository_id": 7, "head_repository_id": 7}})
    return {"run": run, "workflow": workflow, "workflow_text": workflow_text, "jobs": jobs,
            "artifacts": artifacts, "run_id": 123, "raw_lock": raw_lock, "current_lock": raw_lock, "now": NOW}


class SourceIdentityTests(unittest.TestCase):
    def test_completed_failed_run_can_reuse_successful_build_and_upload(self):
        source = validation.validate_source(**source_fixture())
        self.assertEqual(set(source["artifacts"]), {"windows", "linux"})
        self.assertEqual(source["coordinator_sha"], fixtures.SHA)

    def test_run_id_is_strictly_positive_decimal(self):
        self.assertEqual(validation.positive_id("36873407073"), 36873407073)
        for value in ("0", "-1", "+1", "01", "1.0", "1e2", " 1", "1\n", "1;echo x", True, 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validation.positive_id(value)

    def test_wrong_run_repository_workflow_event_and_sha_are_rejected(self):
        cases = (("id", 124), ("path", ".github/workflows/other.yml"), ("workflow_id", 10),
                 ("event", "pull_request"), ("event", "pull_request_target"), ("event", "push"), ("head_sha", "main"),
                 ("head_sha", "A" * 40), ("run_attempt", True), ("status", "in_progress"),
                 ("conclusion", "cancelled"), ("pull_requests", [{}]))
        for key, value in cases:
            case = source_fixture()
            case["run"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validation.validate_source(**case)
        for field in ("repository", "head_repository"):
            for key, value in (("full_name", "other/gx_shell"), ("id", 8)):
                case = source_fixture()
                case["run"][field][key] = value
                with self.subTest(field=field, key=key), self.assertRaises(ValueError):
                    validation.validate_source(**case)

    def test_cross_lock_bytes_are_rejected_without_normalization(self):
        case = source_fixture(b'{"same": true}\n')
        case["current_lock"] = b'{ "same": true }\n'
        with self.assertRaisesRegex(ValueError, "lock bytes"):
            validation.validate_source(**case)

    def test_producer_job_identity_and_successful_steps_are_required(self):
        for key, value in (("head_sha", fixtures.HERDR_SHA), ("run_id", 124), ("run_attempt", 2),
                           ("status", "in_progress")):
            case = source_fixture()
            case["jobs"][1][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validation.validate_source(**case)
        for index in (0, 1):
            for key, value in (("conclusion", "failure"), ("conclusion", "skipped"),
                               ("status", "in_progress"), ("name", "different step"), ("number", 99)):
                case = source_fixture()
                case["jobs"][1]["steps"][index][key] = value
                with self.subTest(index=index, key=key, value=value), self.assertRaises(ValueError):
                    validation.validate_source(**case)

    def test_missing_duplicate_jobs_and_failed_prepare_are_rejected(self):
        for change in (lambda case: case["jobs"].pop(),
                       lambda case: case["jobs"].append(copy.deepcopy(case["jobs"][1])),
                       lambda case: case["jobs"][0].update(conclusion="failure")):
            case = source_fixture()
            change(case)
            with self.assertRaises(ValueError):
                validation.validate_source(**case)

    def test_only_the_source_workflow_release_upload_is_accepted(self):
        for before, after in (("name: release-linux", "name: unrelated-linux"),
                              ("path: dist/*", "path: unverified/*"),
                              ("Assemble and build the GX Shell deb", "Dummy production"),
                              ("if-no-files-found: error", "if-no-files-found: ignore")):
            case = source_fixture()
            case["workflow_text"] = case["workflow_text"].replace(before, after)
            with self.subTest(before=before), self.assertRaises(ValueError):
                validation.validate_source(**case)

    def test_both_unique_artifacts_are_required(self):
        for change in (lambda case: case["artifacts"].pop(),
                       lambda case: case["artifacts"].append(copy.deepcopy(case["artifacts"][0]))):
            case = source_fixture()
            change(case)
            with self.assertRaisesRegex(ValueError, "both unique"):
                validation.validate_source(**case)

    def test_expired_missing_digest_and_old_attempt_artifacts_are_rejected(self):
        cases = (("expired", True), ("expired", None), ("expires_at", "2026-10-01T14:00:00Z"),
                 ("created_at", "2026-09-30T10:11:30Z"), ("created_at", "2026-10-01T10:12:01Z"),
                 ("digest", None), ("digest", "sha256:bad"), ("size_in_bytes", 0),
                 ("size_in_bytes", True), ("id", -1))
        for key, value in cases:
            case = source_fixture()
            case["artifacts"][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validation.validate_source(**case)
        for key in ("id", "head_sha", "repository_id", "head_repository_id"):
            case = source_fixture()
            case["artifacts"][0]["workflow_run"][key] = 999
            with self.subTest(key=key), self.assertRaises(ValueError):
                validation.validate_source(**case)


class StreamingAndZipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gx-artifact-unit-")
        self.addCleanup(fixtures.cleanup_temp, self.temp)
        self.root = Path(self.temp.name)

    def test_download_reads_only_bounded_chunks_and_matches_api_digest(self):
        data = b"z" * (2 * validation.CHUNK + 7)
        class Bounded(io.BytesIO):
            def read(stream, size=-1):
                self.assertEqual(size, validation.CHUNK)
                return super().read(size)
        output = self.root / "archive.zip"
        validation.stream_zip(Bounded(data), output, len(data), "sha256:" + hashlib.sha256(data).hexdigest())
        self.assertEqual(output.stat().st_size, len(data))

    def test_download_rejects_wrong_digest_short_long_and_existing_output(self):
        for index, (size, checksum) in enumerate(((3, "0" * 64), (2, hashlib.sha256(b"abc").hexdigest()),
                                                (4, hashlib.sha256(b"abc").hexdigest()))):
            with self.subTest(size=size), self.assertRaises(ValueError):
                validation.stream_zip(io.BytesIO(b"abc"), self.root / str(index), size, "sha256:" + checksum)
        existing = self.root / "existing"
        existing.write_bytes(b"keep")
        with self.assertRaises(FileExistsError):
            validation.stream_zip(io.BytesIO(b"abc"), existing, 3, "sha256:" + hashlib.sha256(b"abc").hexdigest())
        self.assertEqual(existing.read_bytes(), b"keep")

    def zipped(self, names, attributes=None):
        path = self.root / "test.zip"
        with zipfile.ZipFile(path, "w") as archive, warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            for index, name in enumerate(names):
                entry = zipfile.ZipInfo(name)
                if attributes and index == 0:
                    entry.external_attr = attributes
                archive.writestr(entry, b"fixture")
        return path

    def test_flat_four_file_release_zip_is_extracted(self):
        names = validation.package_names("0.1.0", "linux")
        destination = self.root / "dist"
        self.assertEqual(validation.extract_zip(self.zipped(names), destination, "linux"), "0.1.0")
        self.assertEqual({p.name for p in destination.iterdir()}, set(names))

    def test_zip_traversal_duplicates_case_collisions_links_and_directories_are_rejected(self):
        names = list(validation.package_names("0.1.0", "linux"))
        invalid = ("../escape", "/absolute", "C:/escape", "dir/file", "dir\\file", "NUL",
                   "escape.", "name:stream", names[1], names[1].upper(), "directory/")
        for index, name in enumerate(invalid):
            case = [name] + names[1:]
            destination = self.root / f"bad-{index}"
            with self.subTest(name=name), self.assertRaises(ValueError):
                validation.extract_zip(self.zipped(case), destination, "linux")
            self.assertFalse(destination.exists())
        for kind in (stat.S_IFLNK, stat.S_IFIFO, stat.S_IFDIR, stat.S_IFCHR):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                validation.extract_zip(self.zipped(names, (kind | 0o777) << 16), self.root / f"kind-{kind}", "linux")

    def test_zip_missing_extra_wrong_platform_and_size_limit_are_rejected(self):
        names = validation.package_names("0.1.0", "linux")
        for index, case in enumerate((names[:-1], (*names, "extra"), validation.package_names("0.1.0", "windows"))):
            with self.subTest(index=index), self.assertRaises(ValueError):
                validation.extract_zip(self.zipped(case), self.root / f"bad-{index}", "linux")
        with mock.patch.object(validation, "MAX_ZIP", 1), self.assertRaisesRegex(ValueError, "size limit"):
            validation.extract_zip(self.zipped(names), self.root / "oversized", "linux")

    def test_fresh_workspace_cannot_escape_reuse_or_use_a_link(self):
        with mock.patch.dict(os.environ, {"RUNNER_TEMP": str(self.root)}):
            path = validation.fresh_workspace(self.root / "new")
            self.assertTrue(path.is_dir())
            for target in (path, self.root, self.root.parent / "outside-gx-validation"):
                with self.subTest(target=target), self.assertRaises(ValueError):
                    validation.fresh_workspace(target)
            with mock.patch.object(package, "is_link", return_value=True), self.assertRaisesRegex(ValueError, "reparse"):
                validation.fresh_workspace(self.root / "linked")
            self.assertFalse((self.root / "linked").exists())


class RunnerBoundaryTests(unittest.TestCase):
    def test_local_and_self_hosted_execution_are_refused_before_git(self):
        for environment in ({}, {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "self-hosted"}):
            with (mock.patch.dict(os.environ, environment, clear=True),
                  mock.patch.object(validation.subprocess, "run") as run, self.assertRaisesRegex(ValueError, "GitHub-hosted")):
                validation.validator_identity()
            run.assert_not_called()

    def test_validator_sha_is_distinct_and_git_does_not_inherit_credentials(self):
        environment = {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted",
            "GITHUB_REPOSITORY": validation.REPOSITORY, "GITHUB_SHA": VALIDATOR["sha"],
            "GITHUB_RUN_ID": "456", "GITHUB_RUN_ATTEMPT": "1",
            "GH_TOKEN": "fixture-gh-secret", "GITHUB_TOKEN": "fixture-github-secret", "GH_DEBUG": "api"}
        with (mock.patch.dict(os.environ, environment), mock.patch.object(validation.subprocess, "run") as run):
            run.return_value.stdout = VALIDATOR["sha"] + "\n"
            self.assertEqual(validation.validator_identity(), VALIDATOR)
            for name in ("GH_TOKEN", "GITHUB_TOKEN", "GH_DEBUG"):
                self.assertNotIn(name, run.call_args.kwargs["env"])
            run.return_value.stdout = fixtures.SHA
            with self.assertRaisesRegex(ValueError, "validator checkout"):
                validation.validator_identity()


class PackageAndReceiptTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.ReleaseVerificationTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.root = fixture.dir / "validation"
        self.root.mkdir()
        self.lock = self.root / "components.lock.json"
        self.lock.write_bytes(fixture.lock.read_bytes())
        self.case = source_fixture(self.lock.read_bytes())
        source = validation.validate_source(**self.case)
        self.inputs = {"schema": 1, "source": source, "inputs_digest": validation.fingerprint(source),
                       "validator": copy.deepcopy(VALIDATOR), "packages": {}}
        for platform in validation.BUILD_STEPS:
            folder = self.root / platform
            folder.mkdir()
            for name in validation.package_names("0.1.0", platform):
                shutil.copyfile(fixture.dir / name, folder / name)
            self.inputs["packages"][platform] = validation.verify_platform(folder, platform, "0.1.0", fixtures.SHA, self.lock)
        self.input_path = self.root / "input.json"
        package.write_json(self.input_path, self.inputs)

    def smoke(self, platform):
        record = self.inputs["packages"][platform]
        manifest = package.read_json(self.root / platform / (record["installer"] + ".manifest.json"))
        return {"schema": 1, "status": "PASS", "platform": platform, "coordinator": manifest["coordinator"],
                "components_lock_digest": manifest["components_lock_digest"], "components": manifest["components"],
                "stages": manifest["stages"],
                "package": {"sha256": record["files"][record["installer"]]["sha256"], "version": "0.1.0"},
                "package_manifest": {"sha256": record["files"][record["installer"] + ".manifest.json"]["sha256"]},
                "herdr_probe": {"revision": fixtures.OMZ_SHA},
                "coverage": {**{key: "PASS" for key in validation.COVERAGE[platform]}, "hardware_gpu": "NOT_RUN"}}, manifest

    def test_original_package_identity_passes_without_relabeling(self):
        record = self.inputs["packages"]["linux"]
        self.assertEqual(validation.verify_platform(self.root / "linux", "linux", "0.1.0", fixtures.SHA, self.lock), record)
        with self.assertRaisesRegex(ValueError, "source_commit"):
            validation.verify_platform(self.root / "linux", "linux", "0.1.0", VALIDATOR["sha"], self.lock)

    def test_package_source_archive_and_sidecar_tampering_are_rejected(self):
        folder = self.root / "linux"
        for name in validation.package_names("0.1.0", "linux"):
            path = folder / name
            original = path.read_bytes()
            path.write_bytes(original + b"tampered")
            with self.subTest(name=name), self.assertRaises(ValueError):
                validation.verify_platform(folder, "linux", "0.1.0", fixtures.SHA, self.lock)
            path.write_bytes(original)

    def test_missing_extra_files_and_cross_lock_identity_are_rejected(self):
        folder = self.root / "linux"
        extra = folder / "extra"
        extra.write_bytes(b"extra")
        with self.assertRaisesRegex(ValueError, "missing or extra"):
            validation.verify_platform(folder, "linux", "0.1.0", fixtures.SHA, self.lock)
        extra.unlink()
        raw = self.lock.read_bytes()
        self.lock.write_bytes(raw + b"\n")
        with self.assertRaisesRegex(ValueError, "lock snapshot or digest"):
            validation.verify_platform(folder, "linux", "0.1.0", fixtures.SHA, self.lock)

    def test_development_and_cross_component_manifests_are_rejected(self):
        folder = self.root / "linux"
        names = validation.package_names("0.1.0", "linux")
        original = package.read_json(folder / names[2])
        for change in (lambda value: value.update(publishable=False), lambda value: value.update(source_dirty=True),
                       lambda value: value["components"]["herdr"].update(revision=fixtures.OMZ_SHA)):
            info = copy.deepcopy(original)
            change(info)
            package.write_json(folder / names[2], info)
            with self.assertRaises(ValueError):
                validation.verify_platform(folder, "linux", "0.1.0", fixtures.SHA, self.lock)

    def test_smoke_requires_complete_lifecycle_and_the_same_package(self):
        for target, platform in validation.TARGETS.items():
            smoke, manifest = self.smoke(platform)
            validation.validate_smoke(smoke, self.inputs, target, manifest)
            for change in (lambda value: value.update(status="PREFLIGHT_PASS"),
                           lambda value: value["coverage"].update(reinstall_runtime="NOT_RUN"),
                           lambda value: value["package"].update(sha256="0" * 64),
                           lambda value: value["package_manifest"].update(sha256="0" * 64),
                           lambda value: value.update(components_lock_digest="0" * 64),
                           lambda value: value["herdr_probe"].update(revision=fixtures.HERDR_SHA),
                           lambda value: value["coordinator"].update(revision=VALIDATOR["sha"])):
                changed = copy.deepcopy(smoke)
                change(changed)
                with self.subTest(target=target), self.assertRaises(ValueError):
                    validation.validate_smoke(changed, self.inputs, target, manifest)

    def test_record_requires_successful_step_and_actual_ubuntu_target(self):
        evidence = self.root / "evidence"
        evidence.mkdir()
        smoke, _ = self.smoke("linux")
        package.write_json(evidence / "smoke-provenance.json", smoke)
        (evidence / "result.txt").write_text("PASS: fixture lifecycle\n")
        (evidence / "os-release").write_text('ID=ubuntu\nVERSION_ID="20.04"\n')
        receipt = validation.record_smoke(self.input_path, self.lock, VALIDATOR, "ubuntu-20.04", evidence, "success")
        self.assertEqual(receipt["source"]["coordinator_sha"], fixtures.SHA)
        self.assertEqual(receipt["validator"]["sha"], VALIDATOR["sha"])
        for outcome, target in (("failure", "ubuntu-20.04"), ("skipped", "ubuntu-20.04"), ("success", "ubuntu-24.04")):
            with self.subTest(outcome=outcome, target=target), self.assertRaises(ValueError):
                validation.record_smoke(self.input_path, self.lock, VALIDATOR, target, evidence, outcome)

    def receipts(self):
        root = self.root / "receipts"
        root.mkdir()
        for target, platform in validation.TARGETS.items():
            folder = root / target
            folder.mkdir()
            package.write_json(folder / "validation-receipt.json", {
                "schema": 1, "status": "PASS", "validation_only": True, "target": target,
                "validator": VALIDATOR, "source": self.inputs["source"], "inputs_digest": self.inputs["inputs_digest"],
                "package": self.inputs["packages"][platform], "coverage": self.smoke(platform)[0]["coverage"]})
        return root

    def test_aggregate_accepts_only_all_current_validator_smokes(self):
        root = self.receipts()
        result = validation.aggregate(self.input_path, self.lock, VALIDATOR, root, fixtures.SHA)
        self.assertEqual(result["targets"], sorted(validation.TARGETS))
        self.assertFalse(result["published"])
        path = root / "windows/validation-receipt.json"
        original = package.read_json(path)
        for change in (lambda value: value.update(status="FAIL"), lambda value: value["validator"].update(run_id=455),
                       lambda value: value["validator"].update(run_attempt=2),
                       lambda value: value["source"].update(coordinator_sha=VALIDATOR["sha"]),
                       lambda value: value["package"].update(version="9.9.9"),
                       lambda value: value["coverage"].update(uninstall="NOT_RUN"),
                       lambda value: value.update(target="ubuntu-20.04")):
            changed = copy.deepcopy(original)
            change(changed)
            package.write_json(path, changed)
            with self.assertRaises(ValueError):
                validation.aggregate(self.input_path, self.lock, VALIDATOR, root, fixtures.SHA)
        path.unlink()
        with self.assertRaisesRegex(ValueError, "all three"):
            validation.aggregate(self.input_path, self.lock, VALIDATOR, root, fixtures.SHA)

    def test_api_cli_fixture_downloads_verifies_and_keeps_original_provenance(self):
        blobs = {}
        for index, platform in enumerate(validation.BUILD_STEPS):
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as archive:
                for path in (self.root / platform).iterdir():
                    archive.write(path, path.name)
            blobs[20 + index] = output.getvalue()
            self.case["artifacts"][index].update(size_in_bytes=len(output.getvalue()),
                digest="sha256:" + hashlib.sha256(output.getvalue()).hexdigest())
        case = self.case
        endpoints = []
        class API:
            def get(self, endpoint):
                endpoints.append(endpoint)
                return case["workflow"] if endpoint.endswith("/workflows/release.yml") else case["run"]
            def raw(self, endpoint):
                endpoints.append(endpoint)
                if "components.lock.json?ref=" in endpoint:
                    return case["raw_lock"]
                return case["workflow_text"].encode()
            def collection(self, endpoint, key):
                endpoints.append(endpoint)
                return case[key]
            def download(self, artifact, destination):
                validation.stream_zip(io.BytesIO(blobs[artifact["id"]]), destination, artifact["size_in_bytes"], artifact["digest"])
        source = validation.validate_source(**case)
        out = self.root / "downloaded"
        with (mock.patch.object(validation, "GitHub", API), mock.patch.object(validation, "validator_identity", return_value=VALIDATOR),
              mock.patch.dict(os.environ, {"RUNNER_TEMP": str(self.root)}), contextlib.redirect_stdout(io.StringIO()),
              mock.patch.object(package, "verify", wraps=package.verify) as verify):
            result = validation.main(["download", "--source-run-id", "123", "--platform", "both",
                "--expected-inputs-digest", validation.fingerprint(source), "--components-lock", str(self.lock), "--output", str(out)])
        self.assertEqual(result, 0)
        verify.assert_called_once()
        self.assertEqual(verify.call_args.args[2], fixtures.SHA)
        self.assertEqual((out / "components.lock.json").read_bytes(), self.lock.read_bytes())
        info = package.read_json(out / "input.json")
        self.assertEqual(info["source"]["coordinator_sha"], fixtures.SHA)
        self.assertEqual(info["validator"], VALIDATOR)
        self.assertEqual(len((out / "dist/SHA256SUMS").read_text().splitlines()), 6)
        self.assertIn(f"repos/{validation.REPOSITORY}/contents/components.lock.json?ref={fixtures.SHA}", endpoints)
        self.assertIn(f"repos/{validation.REPOSITORY}/actions/runs/123/attempts/1/jobs", endpoints)
        self.assertNotIn("main", "\n".join(endpoints))

    def test_failure_report_never_claims_success_and_redacts_tokens(self):
        output = self.root / "failed.json"
        with (mock.patch.object(validation, "validator_identity", return_value=VALIDATOR),
              mock.patch.dict(os.environ, {"GH_TOKEN": "fixture-secret"}),
              mock.patch.object(validation, "record_smoke", side_effect=ValueError("fixture-secret rejected")),
              contextlib.redirect_stderr(io.StringIO()) as stderr):
            result = validation.main(["record", "--input", str(self.input_path), "--components-lock", str(self.lock),
                "--target", "windows", "--evidence", str(self.root), "--smoke-outcome", "failure", "--output", str(output)])
        self.assertEqual(result, 1)
        self.assertEqual(package.read_json(output)["status"], "FAIL")
        self.assertNotIn("fixture-secret", output.read_text() + stderr.getvalue())


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / ".github/workflows/validate-artifacts.yml").read_text(encoding="utf-8")

    def job(self, name):
        match = re.search(r"^  " + name + r":\n(.*?)(?=^  [a-z][a-z0-9-]*:|\Z)", self.text, re.M | re.S)
        self.assertIsNotNone(match)
        return match[1]

    def test_dispatch_only_read_permissions_and_no_build_or_publish(self):
        self.assertNotIn("workflow_dispatch:", self.text)
        self.assertIn("workflow_call:", self.text)
        self.assertIn("source_run_id:", self.text)
        self.assertIn("contents: read\n  actions: read", self.text)
        for forbidden in ("contents: write", "push:", "pull_request:", "gh release", "git tag", "git push",
                          "cargo " , "gx_shell_build.py", "gx_shell_package.py assemble", "gx_shell_package.py build",
                          "continue-on-error:", "--allow-dirty", "GITHUB_ACTIONS=true"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.text)

    def test_release_dispatch_routes_source_run_id_to_validation_only(self):
        release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_call:", release)
        self.assertIn("source_run_id:", release)
        self.assertIn("validate-artifacts:", release)
        validate = release[release.index("  validate-artifacts:"):release.rindex("\n  publish:")]
        self.assertIn("if: needs.prepare.outputs.source_run_id != ''", validate)
        self.assertIn("uses: ./.github/workflows/validate-artifacts.yml", validate)
        self.assertIn("source_run_id: ${{ needs.prepare.outputs.source_run_id }}", validate)
        for name in ("wezterm-windows", "wezterm-linux", "wezterm-tests", "shell-windows", "shell-linux",
                     "ohmyzsh-posix", "package-windows", "package-linux", "smoke-linux", "verify"):
            match = re.search(r"^  " + re.escape(name) + r":\n(.*?)(?=^  [a-z][a-z0-9-]*:|\Z)", release, re.M | re.S)
            self.assertIsNotNone(match, name)
            self.assertIn("if: needs.prepare.outputs.source_run_id == ''", match[1], name)
        self.assertIn("INPUT_PUBLISH\" != true", release)
        self.assertIn("source run cannot be the current run", release)
        publish = re.search(r"^  publish:\n(.*?)\Z", release, re.M | re.S).group(1)
        self.assertIn("needs.prepare.outputs.source_run_id == ''", publish)

    def test_tokens_exist_only_on_download_steps_and_never_enter_container(self):
        steps = re.findall(r"^      - .*?(?=^      - |^  [a-z]|\Z)", self.text, re.M | re.S)
        auth = [step for step in steps if re.search(r"^          GH_TOKEN:", step, re.M)]
        self.assertEqual(len(auth), 4)
        for step in auth:
            self.assertTrue(step.startswith("      - name: Download"))
            self.assertNotIn("docker ", step)
            self.assertNotIn("gx_shell_sources.py checkout", step)
            self.assertNotIn("gx_shell_smoke_", step)
        self.assertNotIn("--env GH_TOKEN", self.text)
        self.assertNotIn("--env GITHUB_TOKEN", self.text)
        self.assertEqual(self.text.count("persist-credentials: false"), 4)

    def test_current_smokes_use_original_packages_lock_and_locked_probe(self):
        linux = self.job("smoke-linux")
        windows = self.job("smoke-windows")
        self.assertIn("ubuntu: ['20.04', '24.04']", linux)
        self.assertIn("--platform linux", linux)
        self.assertIn("packaging/debian/smoke.Dockerfile", linux)
        self.assertIn("GX_SMOKE_PYTHON=/opt/gx-smoke-python/bin/python3.14", linux)
        self.assertIn("GX_SMOKE_COMPONENTS_LOCK=/inputs/components.lock.json", linux)
        self.assertIn("bash scripts/gx_shell_smoke_linux.sh", linux)
        self.assertIn("runs-on: windows-2025", windows)
        self.assertIn("RUNNER_ENVIRONMENT -ne 'github-hosted'", windows)
        self.assertIn("--platform windows", windows)
        self.assertIn("./scripts/gx_shell_smoke_windows.ps1", windows)
        for job in (linux, windows):
            self.assertIn("--component ohmyzsh", job)
            self.assertIn("--expected-inputs-digest", job)
            self.assertIn("--smoke-outcome", job)
            self.assertIn("if: always()", job)
            self.assertLess(job.index("gx_shell_validate_artifacts.py download"), job.index("gx_shell_sources.py checkout"))

    def test_aggregate_requires_all_smokes_and_unchanged_package_verify(self):
        verify = self.job("verify")
        self.assertIn("needs: [prepare, smoke-linux, smoke-windows]", verify)
        self.assertIn("if: always()", verify)
        self.assertIn("LINUX_RESULT: ${{ needs.smoke-linux.result }}", verify)
        self.assertIn("WINDOWS_RESULT: ${{ needs.smoke-windows.result }}", verify)
        self.assertIn("all(value == 'success' for value in results.values())", verify)
        self.assertLess(verify.index("Require both complete smoke jobs"), verify.index("Download and verify both original"))
        self.assertIn("--platform both", verify)
        self.assertIn('python scripts/gx_shell_package.py verify', verify)
        self.assertIn('--sha "$SOURCE_SHA"', verify)
        self.assertIn('--components-lock "$RUNNER_TEMP/validation-inputs/components.lock.json"', verify)
        self.assertIn("gx_shell_validate_artifacts.py aggregate", verify)
        for target in validation.TARGETS:
            self.assertIn("name: validation-evidence-" + target, verify)
        self.assertLess(verify.index("gx_shell_package.py verify"), verify.index("gx_shell_validate_artifacts.py aggregate"))


if __name__ == "__main__":
    unittest.main()

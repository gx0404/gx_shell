#!/usr/bin/env python3
"""Validate existing release artifacts without building, relabeling, or publishing them."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import zipfile

import gx_shell_package as package

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "gx0404/gx_shell"
WORKFLOW = ".github/workflows/release.yml"
CHUNK = 1024 * 1024
MAX_ZIP = 16 * 1024**3
BUILD_STEPS = {
    "linux": "Assemble and build the GX Shell deb",
    "windows": "Assemble and build the GX Shell installer",
}
STAGES = {
    "wezterm-windows": ("wezterm", "windows", "Build and stage WezTerm for Windows",
                        "scripts/gx_package.py windows", "stage.tar"),
    "wezterm-linux": ("wezterm", "linux", "Build and stage WezTerm on the Ubuntu 20.04 baseline",
                      "scripts/gx_package.py deb", "stage.tar"),
    "shell-windows": ("ohmyzsh", "windows", "Build locked herdr, Zsh and dependencies, then stage Oh My Zsh GX",
                      "platform=windows-x64", "shell-build/stage.tar"),
    "shell-linux": ("ohmyzsh", "linux", "Build locked herdr, Zsh and dependencies, then stage Oh My Zsh GX",
                    "platform=ubuntu-amd64", "shell-build/stage.tar"),
}
SOURCE_TEST_JOBS = ("wezterm-tests", "ohmyzsh-posix")
TARGETS = {"ubuntu-20.04": "linux", "ubuntu-24.04": "linux", "windows": "windows"}
COVERAGE = {
    "linux": ("install", "same_version_reinstall", "reinstall_runtime", "remove", "purge",
              "user_configuration", "user_data_content_and_ownership", "witness_home_unchanged"),
    "windows": ("install", "same_version_reinstall", "uninstall", "user_configuration",
                "occupied_file_refusal", "reinstall_runtime", "second_install_runtime",
                "profile_contents", "non_owned_baseline"),
}
require = package.require


def positive_id(value: str) -> int:
    require(isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value), "expected a positive decimal run ID")
    return int(value)


def timestamp(value: str) -> datetime:
    require(isinstance(value, str), "missing API timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.tzinfo is not None, "API timestamp lacks timezone")
    return result


def fingerprint(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def no_tokens() -> dict:
    return {key: value for key, value in os.environ.items()
            if key.upper() not in ("GH_TOKEN", "GITHUB_TOKEN", "GH_DEBUG")}


class GitHub:
    def command(self, endpoint: str, raw: bool = False) -> list[str]:
        return ["gh", "api", "--hostname", "github.com", "--method", "GET",
                "-H", "Accept: application/vnd.github.raw+json" if raw else "Accept: application/vnd.github+json",
                "-H", "X-GitHub-Api-Version: 2022-11-28", endpoint]

    def raw(self, endpoint: str) -> bytes:
        result = subprocess.run(self.command(endpoint, True), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                env={key: value for key, value in os.environ.items() if key.upper() != "GH_DEBUG"},
                                timeout=120)
        require(result.returncode == 0, "GitHub metadata request failed")
        require(len(result.stdout) <= 8 * CHUNK, "GitHub metadata response is too large")
        return result.stdout

    def get(self, endpoint: str) -> dict:
        result = json.loads(self.raw(endpoint))
        require(isinstance(result, dict), "invalid GitHub API object")
        return result

    def collection(self, endpoint: str, key: str) -> list[dict]:
        items = []
        total = None
        for page in range(1, 101):
            value = self.get(f"{endpoint}?per_page=100&page={page}")
            require(type(value.get("total_count")) is int and isinstance(value.get(key), list), "invalid API pagination")
            require(total is None or total == value["total_count"], "API collection changed during validation")
            total = value["total_count"]
            items.extend(value[key])
            if len(items) == total:
                return items
            require(value[key] and len(items) < total, "incomplete or inconsistent API pagination")
        raise package.PackageError("API collection exceeds validation limit")

    def download(self, artifact: dict, destination: Path) -> None:
        endpoint = f"repos/{REPOSITORY}/actions/artifacts/{artifact['id']}/zip"
        with subprocess.Popen(self.command(endpoint), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              env={key: value for key, value in os.environ.items() if key.upper() != "GH_DEBUG"}) as process:
            try:
                stream_zip(process.stdout, destination, artifact["size_in_bytes"], artifact["digest"])
                require(process.wait(timeout=120) == 0, "GitHub artifact download failed")
            except BaseException:
                process.kill()
                process.wait()
                raise


def upload_step(workflow: str, platform: str) -> tuple[int, str]:
    match = re.search(r"^  package-" + platform + r":\n(.*?)(?=^  [a-z][a-z0-9-]*:|\Z)", workflow, re.M | re.S)
    require(match is not None, "source workflow lacks the package job")
    steps = re.findall(r"^      - .*?(?=^      - |\Z)", match[1], re.M | re.S)
    builds = [index for index, step in enumerate(steps)
              if step.startswith("      - name: " + BUILD_STEPS[platform] + "\n")]
    require(len(builds) == 1 and builds[0] + 1 < len(steps), "source workflow has ambiguous production steps")
    index = builds[0]
    require("scripts/gx_shell_package.py assemble --platform " + platform in steps[index]
            and "scripts/gx_shell_package.py build --assembly" in steps[index]
            and "continue-on-error:" not in steps[index], "unsupported source production step")
    expected = ("      - uses: actions/upload-artifact@v7\n        with:\n"
                f"          name: release-{platform}\n          path: dist/*\n"
                "          if-no-files-found: error\n          compression-level: 0\n          retention-days: 14")
    require(steps[index + 1].rstrip() == expected, "source release upload contract differs")
    return index + 2, "Run actions/upload-artifact@v7"


def stage_upload_step(workflow: str, key: str) -> tuple[int, str]:
    component, platform, build_name, marker, tar_path = STAGES[key]
    match = re.search(r"^  " + re.escape(key) + r":\n(.*?)(?=^  [a-z][a-z0-9-]*:|\Z)", workflow, re.M | re.S)
    require(match is not None, "source workflow lacks the stage producer")
    steps = re.findall(r"^      - .*?(?=^      - |\Z)", match[1], re.M | re.S)
    builds = [index for index, step in enumerate(steps) if step.startswith("      - name: " + build_name + "\n")]
    require(len(builds) == 1 and builds[0] + 1 < len(steps), "ambiguous stage producer")
    index = builds[0]
    require(marker in steps[index] and "tar -cf" in steps[index] and "continue-on-error:" not in steps[index],
            "unsupported stage production step")
    expected = ("      - uses: actions/upload-artifact@v7\n        with:\n"
                f"          name: stage-{key}\n          path: ${{{{ runner.temp }}}}/{tar_path}\n"
                "          if-no-files-found: error\n          retention-days: 7")
    require(steps[index + 1].rstrip() == expected, "source stage upload contract differs")
    return index + 2, "Run actions/upload-artifact@v7"


def validate_source(run: dict, workflow: dict, workflow_text: str, jobs: list[dict], artifacts: list[dict],
                    run_id: int, raw_lock: bytes, current_lock: bytes, now: datetime, *, stages: bool = False) -> dict:
    require(type(run.get("id")) is int and run["id"] == run_id, "source run ID mismatch")
    repository = run.get("repository", {})
    head_repository = run.get("head_repository", {})
    require(repository.get("full_name") == head_repository.get("full_name") == REPOSITORY
            and type(repository.get("id")) is int and repository["id"] > 0
            and repository["id"] == head_repository.get("id"), "source repository or fork mismatch")
    require(run.get("path") == workflow.get("path") == WORKFLOW
            and type(workflow.get("id")) is int and workflow["id"] == run.get("workflow_id"),
            "source is not the release.yml workflow")
    require(run.get("event") == "workflow_dispatch" and not run.get("pull_requests"), "untrusted source event")
    sha = run.get("head_sha")
    require(isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha), "invalid source coordinator SHA")
    require(run.get("status") == "completed" and run.get("conclusion") in ("success", "failure"),
            "source run must finish before artifact validation")
    attempt = run.get("run_attempt")
    require(type(attempt) is int and attempt > 0, "invalid source run attempt")
    require(raw_lock == current_lock, "source and validator lock bytes differ")
    producer_names = tuple(STAGES) if stages else ("package-linux", "package-windows")
    selected_jobs = {}
    for name in ("prepare", *producer_names, *(SOURCE_TEST_JOBS if stages else ())):
        matches = [job for job in jobs if job.get("name") == name]
        require(len(matches) == 1, "missing or duplicate source production job")
        job = matches[0]
        require(job.get("run_id") == run_id and job.get("head_sha") == sha
                and job.get("run_attempt") == attempt and job.get("status") == "completed",
                "production job belongs to another source identity or attempt")
        require(not stages or job.get("conclusion") == "success", "source stage producer or component tests did not pass")
        selected_jobs[name] = job
    require(selected_jobs["prepare"].get("conclusion") == "success", "source prepare did not pass")
    selected = {}
    for key in (STAGES if stages else BUILD_STEPS):
        job = selected_jobs[key if stages else "package-" + key]
        number, upload_name = stage_upload_step(workflow_text, key) if stages else upload_step(workflow_text, key)
        build_name = STAGES[key][2] if stages else BUILD_STEPS[key]
        artifact_name = ("stage-" if stages else "release-") + key
        steps = job.get("steps", [])
        build = [step for step in steps if step.get("number") == number]
        uploaded = [step for step in steps if step.get("number") == number + 1]
        require(len(build) == len(uploaded) == 1, "missing production or upload step")
        build, uploaded = build[0], uploaded[0]
        for step, name in ((build, build_name), (uploaded, upload_name)):
            require(step.get("name") == name and step.get("status") == "completed"
                    and step.get("conclusion") == "success", "production or release upload did not pass")
        require(timestamp(build["completed_at"]) <= timestamp(uploaded["started_at"]), "upload precedes production")
        matches = [item for item in artifacts if item.get("name") == artifact_name]
        require(len(matches) == 1, "all unique stage artifacts are required" if stages else "both unique release artifacts are required")
        artifact = matches[0]
        identity = artifact.get("workflow_run", {})
        require(identity.get("id") == run_id and identity.get("head_sha") == sha
                and identity.get("repository_id") == identity.get("head_repository_id") == repository["id"],
                "artifact belongs to another source run or repository")
        require(type(artifact.get("id")) is int and artifact["id"] > 0
                and type(artifact.get("size_in_bytes")) is int and 0 < artifact["size_in_bytes"] <= MAX_ZIP,
                "invalid artifact ID or size")
        require(artifact.get("expired") is False and timestamp(artifact["expires_at"]) > now, "artifact expired")
        require(timestamp(uploaded["started_at"]) <= timestamp(artifact["created_at"]) <= timestamp(uploaded["completed_at"]),
                "artifact was not created by this successful upload attempt")
        require(isinstance(artifact.get("digest"), str) and re.fullmatch(r"sha256:[0-9a-f]{64}", artifact["digest"]),
                "artifact lacks an API ZIP SHA-256")
        selected[key] = {field: artifact[field] for field in ("id", "name", "size_in_bytes", "digest")}
        selected[key]["producer_job_id"] = job["id"]
    require(len({item["id"] for item in selected.values()}) == len(selected), "platform artifacts share an ID")
    result = {"repository": REPOSITORY, "workflow": WORKFLOW, "workflow_id": workflow["id"],
              "run_id": run_id, "run_attempt": attempt, "event": run["event"], "coordinator_sha": sha,
              "components_lock_digest": hashlib.sha256(raw_lock).hexdigest(), "artifacts": selected}
    if stages:
        result["kind"] = "component-stages"
        result["source_test_jobs"] = {name: selected_jobs[name]["id"] for name in SOURCE_TEST_JOBS}
    return result


def inspect_source(api: GitHub, run_id: int, lock_path: Path, *, stages: bool = False) -> tuple[dict, bytes]:
    _, _, current = package.read_components_lock(lock_path)
    prefix = f"repos/{REPOSITORY}"
    run = api.get(f"{prefix}/actions/runs/{run_id}")
    sha = run.get("head_sha")
    require(isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha), "invalid source coordinator SHA")
    attempt = run.get("run_attempt")
    require(type(attempt) is int and attempt > 0, "invalid source run attempt")
    workflow = api.get(f"{prefix}/actions/workflows/release.yml")
    raw_lock = api.raw(f"{prefix}/contents/components.lock.json?ref={sha}")
    text = api.raw(f"{prefix}/contents/{WORKFLOW}?ref={sha}").decode("utf-8")
    jobs = api.collection(f"{prefix}/actions/runs/{run_id}/attempts/{attempt}/jobs", "jobs")
    artifacts = api.collection(f"{prefix}/actions/runs/{run_id}/artifacts", "artifacts")
    return validate_source(run, workflow, text, jobs, artifacts, run_id, raw_lock, current,
                           datetime.now(timezone.utc), stages=stages), raw_lock


def stream_zip(stream, destination: Path, size: int, expected: str) -> None:
    require(type(size) is int and 0 < size <= MAX_ZIP and re.fullmatch(r"sha256:[0-9a-f]{64}", expected),
            "invalid expected ZIP size or digest")
    checksum, total = hashlib.sha256(), 0
    with destination.open("xb") as output:
        while block := stream.read(CHUNK):
            total += len(block)
            require(total <= size, "download exceeds API ZIP size")
            checksum.update(block)
            output.write(block)
    require(total == size and "sha256:" + checksum.hexdigest() == expected, "API ZIP size or SHA-256 mismatch")


def package_names(version: str, platform: str) -> tuple[str, ...]:
    installer, archive = package.artifact_names(version, platform)
    return installer, archive, installer + ".manifest.json", installer + ".sha256"


def extract_zip(path: Path, destination: Path, platform: str, *, stage: bool = False) -> str:
    package.safe_directory(destination.parent)
    require(not destination.exists() and not destination.is_symlink(), "ZIP destination must be new")
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        require(len(members) == (1 if stage else 4), "ZIP has an unexpected regular file count")
        names = []
        for member in members:
            name = package.relative_path(member.filename)
            require(name == member.orig_filename and "/" not in name and not member.is_dir(), "unsafe ZIP member")
            kind = stat.S_IFMT(member.external_attr >> 16)
            require(kind in (0, stat.S_IFREG) and not member.external_attr & 0x400
                    and not member.flag_bits & 1, "ZIP links, special files and encrypted entries are forbidden")
            require(name.casefold() not in {item.casefold() for item in names}, "duplicate ZIP member")
            names.append(name)
        require(sum(item.file_size for item in members) <= MAX_ZIP, "expanded ZIP exceeds size limit")
        version = ""
        if stage:
            require(names == ["stage.tar"], "stage ZIP must contain only stage.tar")
        else:
            pattern = (r"gx-shell_([0-9]+\.[0-9]+\.[0-9]+)_amd64\.deb\.manifest\.json" if platform == "linux"
                       else r"GX-Shell-([0-9]+\.[0-9]+\.[0-9]+)-Setup-x64\.exe\.manifest\.json")
            versions = [match[1] for name in names if (match := re.fullmatch(pattern, name))]
            require(len(versions) == 1 and set(names) == set(package_names(versions[0], platform)), "unexpected release ZIP filenames")
            version = versions[0]
        for member in members:
            if member.filename.endswith(".manifest.json"):
                require(member.file_size <= 32 * CHUNK, "manifest is too large")
            if member.filename.endswith(".sha256"):
                require(member.file_size <= 4096, "sidecar is too large")
        destination.mkdir()
        for member in members:
            with archive.open(member) as stream, (destination / member.filename).open("xb") as output:
                total = 0
                while block := stream.read(CHUNK):
                    total += len(block)
                    require(total <= member.file_size, "ZIP member exceeds declared size")
                    output.write(block)
                require(total == member.file_size, "truncated ZIP member")
    return version


def require_native_stage(key: str) -> tuple[str, str]:
    require(key in STAGES, "unknown component stage")
    component, platform = STAGES[key][:2]
    require((platform == "windows" and os.name == "nt")
            or (platform == "linux" and sys.platform.startswith("linux")), "stage requires its native platform")
    return component, platform


def stage_tar_layout(archive, component: str, platform: str) -> dict:
    links = package.stage_links(platform, component, "root/" if component == "wezterm" else "payload/")
    entries, folded, total, roots = {}, set(), 0, 0
    for member in archive:
        require(len(entries) < 250000, "stage tar has too many members")
        if member.name in (".", "./"):
            roots += 1
            require(member.isdir() and roots == 1, "invalid duplicate tar root")
            continue
        name = member.name.removeprefix("./")
        if member.isdir():
            name = name.removesuffix("/")
        package.relative_path(name)
        require(name.casefold() not in folded, "duplicate or case-colliding stage tar member")
        require(not member.mode & 0o7000 and not member.issparse(), "special tar permissions or sparse files are forbidden")
        require(member.isdir() or member.isfile() or (member.issym() and links.get(name) == member.linkname),
                "stage tar contains a forbidden link or special file")
        require(not member.islnk() and member.size >= 0, "stage tar hardlinks or negative sizes are forbidden")
        total += member.size
        require(total <= MAX_ZIP, "expanded stage tar exceeds size limit")
        entries[name] = member
        folded.add(name.casefold())
    require(bool(entries), "empty stage tar")
    for name in entries:
        parts = name.split("/")
        for index in range(1, len(parts)):
            parent = "/".join(parts[:index])
            require(parent not in entries or entries[parent].isdir(), "stage tar traverses a non-directory member")
    return entries


def extract_stage_tar(path: Path, destination: Path, key: str) -> None:
    import tarfile

    component, platform = require_native_stage(key)
    package.safe_directory(destination.parent)
    require(not destination.exists() and not destination.is_symlink(), "stage directory must be new")
    require(path.is_file() and not package.is_link(path) and 0 < path.stat().st_size <= MAX_ZIP, "invalid stage tar file")
    try:
        with tarfile.open(path, "r:") as archive:
            entries = stage_tar_layout(archive, component, platform)
            destination.mkdir()
            for name, member in entries.items():
                target = destination / name
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as stream, target.open("xb") as output:
                        copied = 0
                        while block := stream.read(CHUNK):
                            copied += len(block)
                            require(copied <= member.size, "stage member exceeds declared size")
                            output.write(block)
                        require(copied == member.size, "truncated stage member")
                    target.chmod(member.mode & 0o777)
            for name, member in entries.items():
                if member.issym():
                    target = destination / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.symlink(member.linkname, target)
    except tarfile.TarError as error:
        raise package.PackageError("invalid stage tar") from error


def verify_native_stage(stage: Path, key: str, lock_path: Path) -> dict:
    component, platform = require_native_stage(key)
    lock, checksum, _ = package.read_components_lock(lock_path)
    if component == "wezterm":
        info = package.check_wezterm_stage(stage, platform, lock["components"]["wezterm"]["revision"], False)
        manifest = stage / "stage-manifest.json"
    else:
        info = package.check_ohmyzsh_stage(stage, platform, lock["components"]["ohmyzsh"]["revision"], False,
                                           herdr_sha=lock["components"]["herdr"]["revision"])
        manifest = stage / "package-manifest.json"
    return {"key": key, "platform": platform, "component_revision": lock["components"][component]["revision"],
            "components_lock_digest": checksum, "manifest_sha256": package.digest(manifest),
            "herdr_builder": info.get("herdr_build", {}).get("builder")}


def download_stage(api: GitHub, source: dict, key: str, work: Path, lock_path: Path) -> dict:
    component, platform = require_native_stage(key)
    _, checksum, _ = package.read_components_lock(lock_path)
    require(source.get("kind") == "component-stages" and source["components_lock_digest"] == checksum
            and source["artifacts"][key]["name"] == "stage-" + key, "stage source lock or identity differs")
    api.download(source["artifacts"][key], work / "artifact.zip")
    extract_zip(work / "artifact.zip", work / "archive", platform, stage=True)
    tar_path = work / "archive/stage.tar"
    extract_stage_tar(tar_path, work / "stage", key)
    result = verify_native_stage(work / "stage", key, lock_path)
    result["stage_tar_sha256"] = package.digest(tar_path)
    return result


def validate_request(stage_run: str, release_run: str, publish: str, event: str) -> str:
    require(publish in ("", "false", "true"), "invalid publish flag")
    require(not (stage_run and release_run), "stage reuse and artifact-only validation are mutually exclusive")
    if stage_run or release_run:
        require(event == "workflow_dispatch" and publish == "false", "reuse requires explicit publish=false and manual dispatch")
        positive_id(stage_run or release_run)
    return "reuse-stages" if stage_run else "validate-artifacts" if release_run else "native-build"


def verify_platform(folder: Path, platform: str, version: str, sha: str, lock_path: Path) -> dict:
    package.safe_directory(folder)
    lock, checksum, _ = package.read_components_lock(lock_path)
    names = package_names(version, platform)
    require({item.name for item in folder.iterdir()} == set(names), "release folder has missing or extra files")
    for name in names:
        path = folder / name
        require(path.is_file() and not package.is_link(path) and path.stat().st_size > 0, "missing regular release file")
    info = package.read_json(folder / names[2])
    require(info.get("version") == version and info.get("platform") == platform, "package version or platform mismatch")
    package.verify_provenance(info, lock, checksum, sha, allow_dirty=False)
    require(isinstance(info.get("artifacts"), dict) and set(info["artifacts"]) == set(names[:2]), "unexpected manifest artifacts")
    files = {name: {"sha256": package.digest(folder / name), "size": (folder / name).stat().st_size} for name in names}
    for name in names[:2]:
        record = info["artifacts"][name]
        require(isinstance(record, dict) and type(record.get("size")) is int
                and record == files[name], "release package or source archive hash/size mismatch")
    expected = sorted(f"{files[name]['sha256']}  {name}" for name in names[:3])
    require(sorted((folder / names[3]).read_text(encoding="ascii").splitlines()) == expected, "release sidecar mismatch")
    return {"version": version, "installer": names[0], "files": files}


def validator_identity() -> dict:
    require(os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted",
            "validator requires a real disposable GitHub-hosted runner")
    require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY, "validator repository mismatch")
    sha = os.environ.get("GITHUB_SHA", "")
    require(re.fullmatch(r"[0-9a-f]{40}", sha), "invalid validator SHA")
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True,
                          env=no_tokens(), check=True).stdout.strip()
    require(head == sha, "validator checkout differs from validator SHA")
    return {"repository": REPOSITORY, "sha": sha, "run_id": positive_id(os.environ.get("GITHUB_RUN_ID", "")),
            "run_attempt": positive_id(os.environ.get("GITHUB_RUN_ATTEMPT", ""))}


def fresh_workspace(path: Path) -> Path:
    root = Path(os.environ["RUNNER_TEMP"]).absolute()
    package.safe_directory(root)
    path = path.absolute()
    package.safe_directory(path.parent)
    require(path != root and path.is_relative_to(root) and not path.exists() and not path.is_symlink(),
            "download workspace must be a new RUNNER_TEMP directory")
    path.mkdir()
    return path


def read_input(path: Path, lock_path: Path, validator: dict) -> dict:
    package.safe_directory(path.parent)
    info = package.read_json(path)
    require(info.get("schema") == 1 and info.get("validator") == validator, "validation receipt identity mismatch")
    _, checksum, raw = package.read_components_lock(lock_path)
    require((path.parent / "components.lock.json").read_bytes() == raw
            and info["source"]["components_lock_digest"] == checksum, "validation receipt lock mismatch")
    require(info.get("inputs_digest") == fingerprint(info["source"]), "validation input identity changed")
    return info


def validate_smoke(smoke: dict, inputs: dict, target: str, manifest: dict) -> None:
    platform = TARGETS[target]
    record = inputs["packages"][platform]
    name = record["installer"]
    require(smoke.get("schema") == 1 and smoke.get("status") == "PASS" and smoke.get("platform") == platform,
            "complete platform smoke did not pass")
    require(smoke.get("coordinator") == manifest["coordinator"]
            and smoke.get("components_lock_digest") == inputs["source"]["components_lock_digest"]
            and smoke.get("components") == manifest["components"]
            and smoke.get("stages") == manifest["stages"], "smoke provenance differs from original package")
    require(smoke.get("package", {}).get("sha256") == record["files"][name]["sha256"]
            and smoke.get("package", {}).get("version") == record["version"]
            and smoke.get("package_manifest", {}).get("sha256") == record["files"][name + ".manifest.json"]["sha256"],
            "smoke tested a different package or manifest")
    require(smoke.get("herdr_probe", {}).get("revision") == manifest["components"]["ohmyzsh"]["revision"],
            "smoke probe differs from the locked revision")
    require(all(smoke.get("coverage", {}).get(key) == "PASS" for key in COVERAGE[platform]),
            "smoke lifecycle coverage is incomplete")


def record_smoke(input_path: Path, lock_path: Path, validator: dict, target: str, evidence: Path, outcome: str) -> dict:
    inputs = read_input(input_path, lock_path, validator)
    require(outcome == "success", "smoke step did not succeed")
    platform = TARGETS[target]
    record = inputs["packages"][platform]
    folder = input_path.parent / platform
    require(verify_platform(folder, platform, record["version"], inputs["source"]["coordinator_sha"], lock_path) == record,
            "package changed during smoke")
    package.safe_directory(evidence)
    smoke = package.read_json(evidence / "smoke-provenance.json")
    manifest = package.read_json(folder / (record["installer"] + ".manifest.json"))
    validate_smoke(smoke, inputs, target, manifest)
    require((evidence / "result.txt").read_text(encoding="utf-8-sig").startswith("PASS:"), "smoke lacks its final result")
    if platform == "linux":
        release = dict(line.split("=", 1) for line in (evidence / "os-release").read_text().splitlines() if "=" in line)
        require(release.get("ID", "").strip('"') == "ubuntu"
                and release.get("VERSION_ID", "").strip('"') == target.removeprefix("ubuntu-"), "smoke Ubuntu version mismatch")
    else:
        require(os.name == "nt" and os.environ.get("RUNNER_OS") == "Windows", "Windows smoke requires a Windows runner")
    return {"schema": 1, "status": "PASS", "validation_only": True, "target": target,
            "source": inputs["source"], "inputs_digest": inputs["inputs_digest"], "validator": validator,
            "package": record, "smoke_provenance_sha256": package.digest(evidence / "smoke-provenance.json"),
            "coverage": smoke["coverage"]}


def aggregate(input_path: Path, lock_path: Path, validator: dict, receipts: Path, sha: str) -> dict:
    inputs = read_input(input_path, lock_path, validator)
    require(sha == inputs["source"]["coordinator_sha"] and set(inputs["packages"]) == set(BUILD_STEPS),
            "aggregate requires original coordinator and both platforms")
    package.safe_directory(receipts)
    paths = list(receipts.rglob("validation-receipt.json"))
    require(len(paths) == len(TARGETS), "aggregate requires all three fresh smoke receipts")
    targets = set()
    for path in paths:
        package.safe_directory(path.parent)
        require(not package.is_link(path), "smoke receipt must not be a link")
        receipt = package.read_json(path)
        target = receipt.get("target")
        require(target in TARGETS and target not in targets and receipt.get("status") == "PASS",
                "missing, duplicate or failed smoke target")
        require(receipt.get("validator") == validator and receipt.get("source") == inputs["source"]
                and receipt.get("inputs_digest") == inputs["inputs_digest"]
                and receipt.get("package") == inputs["packages"][TARGETS[target]],
                "smoke receipt is from another validator run or package")
        require(all(receipt.get("coverage", {}).get(key) == "PASS" for key in COVERAGE[TARGETS[target]]),
                "aggregate smoke coverage is incomplete")
        targets.add(target)
    return {"schema": 1, "status": "PASS", "validation_only": True, "source": inputs["source"],
            "validator": validator, "inputs_digest": inputs["inputs_digest"], "targets": sorted(targets),
            "packages": inputs["packages"], "published": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("inspect", "download"):
        step = commands.add_parser(command)
        step.add_argument("--source-run-id", required=True)
        step.add_argument("--output", required=True, type=Path)
        step.add_argument("--components-lock", type=Path, default=ROOT / "components.lock.json")
        step.add_argument("--github-output", action="store_true")
        if command == "download":
            step.add_argument("--platform", choices=("linux", "windows", "both"), required=True)
            step.add_argument("--expected-inputs-digest", required=True)
    for command in ("record", "aggregate"):
        step = commands.add_parser(command)
        step.add_argument("--input", required=True, type=Path)
        step.add_argument("--components-lock", required=True, type=Path)
        step.add_argument("--output", required=True, type=Path)
        if command == "record":
            step.add_argument("--target", choices=tuple(TARGETS), required=True)
            step.add_argument("--evidence", type=Path, required=True)
            step.add_argument("--smoke-outcome", required=True)
        else:
            step.add_argument("--receipts", type=Path, required=True)
            step.add_argument("--sha", required=True)
    args = parser.parse_args(argv)
    failure_path = None
    try:
        validator = validator_identity()
        if args.command in ("inspect", "download"):
            run_id = positive_id(args.source_run_id)
            work = fresh_workspace(args.output)
            failure_path = work / "failure.json"
            api = GitHub()
            source, raw_lock = inspect_source(api, run_id, args.components_lock)
            inputs = {"schema": 1, "source": source, "inputs_digest": fingerprint(source), "validator": validator}
            package.write_json(work / "source.json", inputs)
            (work / "components.lock.json").write_bytes(raw_lock)
            if args.command == "download":
                require(args.expected_inputs_digest == inputs["inputs_digest"], "source artifacts changed after preflight")
                inputs["packages"] = {}
                platforms = tuple(BUILD_STEPS) if args.platform == "both" else (args.platform,)
                for platform in platforms:
                    zipped = work / (platform + ".zip")
                    api.download(source["artifacts"][platform], zipped)
                    version = extract_zip(zipped, work / platform, platform)
                    inputs["packages"][platform] = verify_platform(work / platform, platform, version,
                        source["coordinator_sha"], work / "components.lock.json")
                require(len({item["version"] for item in inputs["packages"].values()}) == 1, "platform versions differ")
                if args.platform == "both":
                    combined = work / "dist"
                    combined.mkdir()
                    for platform in platforms:
                        for path in (work / platform).iterdir():
                            os.link(path, combined / path.name)
                    package.verify(combined, version, source["coordinator_sha"], components_lock=work / "components.lock.json")
                package.write_json(work / "input.json", inputs)
            if args.github_output:
                with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
                    for key, value in (("source_sha", source["coordinator_sha"]),
                                       ("lock_digest", source["components_lock_digest"]), ("inputs_digest", inputs["inputs_digest"])):
                        print(f"{key}={value}", file=stream)
                    if args.command == "download":
                        print(f"version={version}", file=stream)
            print(json.dumps(inputs, sort_keys=True))
        else:
            package.safe_directory(args.output.parent)
            require(not args.output.exists() and not args.output.is_symlink(), "validation report must be new")
            failure_path = args.output
            if args.command == "record":
                result = record_smoke(args.input, args.components_lock, validator, args.target, args.evidence, args.smoke_outcome)
            else:
                result = aggregate(args.input, args.components_lock, validator, args.receipts, args.sha)
            package.write_json(args.output, result)
            print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        message = str(error)
        for name in ("GH_TOKEN", "GITHUB_TOKEN"):
            if os.environ.get(name):
                message = message.replace(os.environ[name], "[REDACTED]")
        if failure_path is not None:
            package.write_json(failure_path, {"schema": 1, "status": "FAIL", "validation_only": True,
                "validator": validator, "requested_source_run_id": getattr(args, "source_run_id", None), "error": message})
        print(f"gx-shell-validate-artifacts: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

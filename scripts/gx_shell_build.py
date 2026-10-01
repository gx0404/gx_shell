#!/usr/bin/env python3
"""Run one local GX Shell build from independently locked component checkouts.

The driver is deliberately local-only: it never publishes, never sets CI identity,
and marks the resulting assembly as a development build. Component compilation is
serialized under one CPU/memory budget; cache roots are keyed by the locked source
revisions and toolchain selected by the planner.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ("herdr", "ohmyzsh", "wezterm")
PLATFORMS = {
    "windows": "windows-x64",
    "linux": "ubuntu-amd64",
}


class BuildError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BuildError(message)


def safe_path(path: Path, *, must_exist: bool = False, ascii_only: bool = True) -> Path:
    path = path.absolute()
    text = str(path)
    require(".." not in path.parts, "paths must not contain parent traversal")
    if ascii_only:
        require(len(text) <= 100 and re.fullmatch(r"[A-Za-z0-9_./:\\-]+", text) is not None,
                "build paths must be short ASCII paths without spaces or shell metacharacters")
    if must_exist:
        require(path.exists(), f"missing path: {path}")
    return path


def read_lock(path: Path) -> dict:
    sys.path.insert(0, str(ROOT / "scripts"))
    import gx_shell_sources as sources
    try:
        return sources.load_lock(path)
    except (ValueError, OSError) as error:
        raise BuildError(f"invalid components lock: {error}") from None


def run(command: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None,
        log: list[dict] | None = None) -> None:
    started = time.monotonic()
    printable = [str(item) for item in command]
    print("gx-shell-build: " + " ".join(printable), flush=True)
    process = subprocess.run(printable, cwd=cwd, env=env, check=False)
    elapsed = round(time.monotonic() - started, 3)
    if log is not None:
        log.append({"command": printable, "cwd": str(cwd), "exit_code": process.returncode, "seconds": elapsed})
    if process.returncode:
        raise BuildError(f"command failed with exit code {process.returncode}: {printable[0]}")


def ps_quote(value: str) -> str:
    require("'" not in value and "\r" not in value and "\n" not in value, "PowerShell path contains unsupported characters")
    return "'" + value + "'"


def ps_map(values: dict[str, str]) -> str:
    return "@{" + ";".join(f"{key}={ps_quote(value)}" for key, value in values.items()) + "}"


def planner(root: Path, sources: Path, lock: dict, jobs: int | None, memory: str | None,
            component: str) -> dict:
    if os.name != "nt":
        return {"ready": True, "budget": {"cpu_jobs": jobs or 4, "zsh_jobs": jobs or 4}, "toolchain": {}}
    script = ROOT / "scripts/gx_shell_local_build.ps1"
    command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
               "-Command", "& " + ps_quote(str(script)) + " -Format Json -RepoRoot " + ps_quote(str(ROOT))
               + " -Component " + component
               + " -ComponentRoots " + ps_map({name: str(sources / name) for name in COMPONENTS})
               + " -ComponentRevisions " + ps_map({name: lock["components"][name]["revision"] for name in COMPONENTS})]
    env = os.environ.copy()
    if jobs is not None:
        env["GX_CPU_JOBS"] = str(jobs)
        env["GX_ZSH_JOBS"] = str(min(jobs, 8))
    if memory:
        env["GX_MEMORY_BUDGET_GB"] = memory
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        raise BuildError(result.stderr.strip() or "local resource planner failed")
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise BuildError("local resource planner returned invalid JSON") from None
    require(report.get("ready") is True, "local resource planner is not ready; install the pinned toolchain or adjust resources")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=tuple(PLATFORMS), required=True)
    parser.add_argument("--components-lock", type=Path, default=ROOT / "components.lock.json")
    parser.add_argument("--work-root", type=Path, required=True,
                        help="new short ASCII directory outside the coordinator checkout")
    parser.add_argument("--sources-root", type=Path,
                        help="existing independent checkout root; otherwise checkout into a sibling directory")
    parser.add_argument("--jobs", type=int, help="shared CPU ceiling for one component at a time")
    parser.add_argument("--memory-budget-gb", type=str)
    parser.add_argument("--offline", action="store_true", help="reuse existing pinned checkouts; never fetch")
    parser.add_argument("--plan", action="store_true", help="validate sources and print the plan without building")
    parser.add_argument("--iscc", help="optional Inno Setup 7.1 ISCC.exe path")
    args = parser.parse_args(argv)
    try:
        require(not os.environ.get("GITHUB_ACTIONS") and not os.environ.get("GH_TOKEN")
                and not os.environ.get("GITHUB_TOKEN"),
                "local build refuses CI identity and API tokens")
        lock_path = safe_path(args.components_lock, must_exist=True, ascii_only=False)
        work = safe_path(args.work_root)
        require(not work.exists(), "work-root must be new; choose a fresh build directory")
        lock = read_lock(lock_path)
        source_root = safe_path(args.sources_root) if args.sources_root else safe_path(work.parent / (work.name + "-sources"))
        if source_root.exists() and not args.sources_root:
            raise BuildError(f"derived sources-root already exists: {source_root}")
        if args.jobs is not None:
            require(1 <= args.jobs <= 32, "jobs must be between 1 and 32")
        if args.memory_budget_gb is not None:
            require(re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", args.memory_budget_gb) is not None,
                    "memory budget must be a positive decimal")
        import gx_shell_sources as sources
        checked = sources.checkout(lock_path, source_root, list(COMPONENTS), offline=args.offline)
        report = planner(ROOT, source_root, lock, args.jobs, args.memory_budget_gb, "wezterm" if args.platform == "windows" else "ohmyzsh")
        jobs = args.jobs or int(report.get("budget", {}).get("cpu_jobs", 4))
        zsh_jobs = min(jobs, 8)
        work.mkdir(parents=True)
        commands: list[dict] = []
        env = os.environ.copy()
        selected_name = "wezterm" if args.platform == "windows" else "ohmyzsh"
        selected_paths = report.get("paths", {}).get("components", {}).get(selected_name, {}).get("paths", {})
        env.update({"GX_LOCAL_BUILD_ROOT": str(work.parent), "GX_CPU_JOBS": str(jobs),
                    "GX_ZSH_JOBS": str(zsh_jobs), "CARGO_BUILD_JOBS": str(jobs),
                    "CMAKE_BUILD_PARALLEL_LEVEL": str(jobs), "MAKEFLAGS": f"-j{jobs}",
                    "RUSTUP_AUTO_INSTALL": "0", "CARGO_NET_OFFLINE": "true" if args.offline else "false",
                    "PYTHONDONTWRITEBYTECODE": "1"})
        if selected_paths.get("cargo_home"):
            env["CARGO_HOME"] = selected_paths["cargo_home"]
        if selected_paths.get("cargo_target"):
            env["CARGO_TARGET_DIR"] = selected_paths["cargo_target"]
        if selected_paths.get("sccache") and report.get("tools", {}).get("sccache", {}).get("found"):
            env["SCCACHE_DIR"] = selected_paths["sccache"]
        platform = PLATFORMS[args.platform]
        if args.plan:
            print(json.dumps({"platform": platform, "jobs": jobs, "zsh_jobs": zsh_jobs,
                              "work_root": str(work), "sources_root": str(source_root),
                              "lock_digest": checked["lock_digest"], "planner": report},
                             ensure_ascii=False, indent=2))
            return 0
        wezterm = source_root / "wezterm"
        shell_work = work / "shell"
        wezterm_stage = work / "wezterm-stage"
        if args.platform == "windows":
            run([sys.executable, "-B", str(wezterm / "scripts/gx_package.py"), "windows",
                 "--stage-dir", str(wezterm_stage)], cwd=wezterm, env=env, log=commands)
        else:
            run([sys.executable, "-B", str(wezterm / "scripts/gx_package.py"), "deb", "--container",
                 "--cache-dir", str(work / "wezterm-cache"), "--stage-dir", str(wezterm_stage)],
                cwd=wezterm, env=env, log=commands)
        stage_command = ["bash", str(ROOT / "scripts/gx_shell_stage_shell.sh"), platform, str(shell_work),
                         "--ohmyzsh-root", str(source_root / "ohmyzsh"), "--herdr-root", str(source_root / "herdr"),
                         "--components-lock", str(lock_path), "--component-revision", lock["components"]["ohmyzsh"]["revision"],
                         "--jobs", str(jobs), "--allow-dirty"]
        run(stage_command, cwd=ROOT, env=env, log=commands)
        assembly = work / "assembly"
        dist = work / "dist"
        assemble = [sys.executable, "-B", str(ROOT / "scripts/gx_shell_package.py"), "assemble",
                    "--platform", args.platform, "--components-lock", str(lock_path),
                    "--wezterm-stage", str(wezterm_stage), "--ohmyzsh-stage", str(shell_work / "ohmyzsh-stage"),
                    "--output", str(assembly), "--allow-dirty"]
        run(assemble, cwd=ROOT, env=env, log=commands)
        build = [sys.executable, "-B", str(ROOT / "scripts/gx_shell_package.py"), "build",
                 "--assembly", str(assembly), "--output", str(dist)]
        if args.iscc:
            build += ["--iscc", args.iscc]
        run(build, cwd=ROOT, env=env, log=commands)
        (work / "build-report.json").write_text(json.dumps({
            "schema": 1, "platform": args.platform, "builder": "local", "publishable": False,
            "lock_digest": checked["lock_digest"], "components": checked["components"],
            "jobs": jobs, "zsh_jobs": zsh_jobs, "commands": commands,
            "planner": report, "work_root": str(work), "sources_root": str(source_root),
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps({"ok": True, "platform": args.platform, "dist": str(dist),
                          "work_root": str(work), "lock_digest": checked["lock_digest"]}, ensure_ascii=False))
        return 0
    except (BuildError, OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f"gx-shell-build: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

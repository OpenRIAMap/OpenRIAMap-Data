from __future__ import annotations

from pathlib import Path
import subprocess


class GitCommandError(RuntimeError):
    pass


def run_git(repo_root: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if check and proc.returncode != 0:
        raise GitCommandError(proc.stderr.strip() or proc.stdout.strip() or f"git {' '.join(args)} failed")
    return proc


def git_status_porcelain(repo_root: Path) -> str:
    return run_git(repo_root, ["status", "--porcelain"]).stdout


def git_add_all(repo_root: Path) -> None:
    run_git(repo_root, ["add", "-A"])


def git_commit(repo_root: Path, message: str) -> str:
    proc = run_git(repo_root, ["commit", "-m", message], check=False)
    if proc.returncode != 0:
        out = (proc.stderr or proc.stdout or "").strip()
        if "nothing to commit" in out.lower():
            return ""
        raise GitCommandError(out or "git commit failed")
    return get_git_head_hash(repo_root)


def git_pull_rebase(repo_root: Path, remote: str = "origin", branch: str = "main") -> None:
    run_git(repo_root, ["pull", "--rebase", remote, branch])


def git_push(repo_root: Path, remote: str = "origin", branch: str = "main") -> None:
    run_git(repo_root, ["push", remote, branch])


def get_git_head_hash(repo_root: Path) -> str:
    return run_git(repo_root, ["rev-parse", "HEAD"]).stdout.strip()


def get_current_branch(repo_root: Path) -> str:
    return run_git(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()


def get_remote_url(repo_root: Path, remote: str = "origin") -> str:
    return run_git(repo_root, ["remote", "get-url", remote]).stdout.strip()

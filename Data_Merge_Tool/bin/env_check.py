from __future__ import annotations

from pathlib import Path
import os
import shutil
import socket
from urllib import request

from git_utils import get_current_branch, get_remote_url, git_status_porcelain
from github_release_api import get_repo


def _check_http_endpoint(url: str, timeout: float = 4.0) -> tuple[str, str]:
    req = request.Request(url, method="HEAD")
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return "PASS", f"HTTP {getattr(resp, 'status', 200)}"
    except Exception as e:
        try:
            req = request.Request(url, method="GET")
            with request.urlopen(req, timeout=timeout) as resp:
                return "PASS", f"HTTP {getattr(resp, 'status', 200)}"
        except Exception as e2:
            return "WARN", f"{type(e2).__name__}: {e2}"


def _check_dns(hostname: str) -> tuple[str, str]:
    try:
        ip = socket.gethostbyname(hostname)
        return "PASS", ip
    except Exception as e:
        return "WARN", f"DNS 解析失败：{e}"


def run_env_checks(repo_root: Path, tool_root: Path, config: dict) -> dict:
    results = []

    def add(name: str, status: str, detail: str):
        results.append({"name": name, "status": status, "detail": detail})

    git_bin = shutil.which("git")
    gh_bin = shutil.which("gh")
    add("git 可执行", "PASS" if git_bin else "FAIL", git_bin or "未找到 git")
    add("gh 可执行", "PASS" if gh_bin else "WARN", gh_bin or "未找到 gh（可选）")
    add("仓库根目录", "PASS" if (repo_root / ".git").exists() else "FAIL", str(repo_root))

    for rel in [
        tool_root / "config" / "tool_config.json",
        tool_root / "config" / "policy_config.json",
        tool_root / "source_data" / "json_inputs",
        tool_root / "source_data" / "image_inputs",
        tool_root / "source_data" / "relay_packages",
    ]:
        add(f"路径检查 {rel.relative_to(tool_root)}", "PASS" if rel.exists() else "FAIL", str(rel))

    if git_bin and (repo_root / ".git").exists():
        try:
            add("当前分支", "PASS", get_current_branch(repo_root))
        except Exception as e:
            add("当前分支", "FAIL", str(e))
        try:
            add("origin URL", "PASS", get_remote_url(repo_root))
        except Exception as e:
            add("origin URL", "FAIL", str(e))
        try:
            dirty = git_status_porcelain(repo_root).strip()
            add("工作区状态", "PASS" if dirty == "" else "WARN", "干净" if dirty == "" else "存在未提交改动")
        except Exception as e:
            add("工作区状态", "FAIL", str(e))

    # GitHub 连通性轻量检查：优先 DNS + HTTPS，避免仅依赖系统 ping/ICMP。
    for host in ["github.com", "api.github.com", "uploads.github.com"]:
        status, detail = _check_dns(host)
        add(f"GitHub DNS {host}", status, detail)
    for label, url in [
        ("GitHub 主站连通", "https://github.com/"),
        ("GitHub API 连通", "https://api.github.com/"),
        ("GitHub Upload 连通", "https://uploads.github.com/"),
    ]:
        status, detail = _check_http_endpoint(url)
        add(label, status, detail)

    token_env = config.get("github", {}).get("cold_token_env", "OPENRIAMAP_COLD_PAT")
    token = os.environ.get(token_env, "")
    if token:
        add("冷仓库令牌", "PASS", f"环境变量 {token_env} 已设置")
        repo_name = config.get("github", {}).get("cold_repo", "OpenRIAMap/ColdToolArchive")
        try:
            get_repo(repo_name, token)
            add("冷仓库访问", "PASS", repo_name)
        except Exception as e:
            add("冷仓库访问", "FAIL", str(e))
    else:
        add("冷仓库令牌", "FAIL", f"缺少环境变量 {token_env}")

    # Data 仓库远端与冷仓库目标的简单可达性提示
    data_remote = config.get("github", {}).get("data_remote_url") or None
    if not data_remote:
        try:
            if git_bin and (repo_root / ".git").exists():
                data_remote = get_remote_url(repo_root)
        except Exception:
            data_remote = None
    if data_remote:
        add("Data 仓库远端", "PASS", data_remote)

    overall = "PASS"
    if any(x["status"] == "FAIL" for x in results):
        overall = "FAIL"
    elif any(x["status"] == "WARN" for x in results):
        overall = "WARN"
    return {"overall": overall, "items": results}

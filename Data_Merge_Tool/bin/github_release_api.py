from __future__ import annotations

from pathlib import Path
from urllib import request, parse
from urllib.error import HTTPError
import json
import mimetypes


class GitHubReleaseError(RuntimeError):
    pass


def _api_request(url: str, token: str, method: str = "GET", data: bytes | None = None, headers: dict | None = None):
    req = request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with request.urlopen(req) as resp:
            content = resp.read()
            if not content:
                return None
            return json.loads(content.decode("utf-8"))
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise GitHubReleaseError(f"GitHub API error {e.code}: {body}")


def get_repo(repo: str, token: str):
    return _api_request(f"https://api.github.com/repos/{repo}", token)


def list_releases(repo: str, token: str):
    return _api_request(f"https://api.github.com/repos/{repo}/releases", token) or []


def ensure_monthly_release(repo: str, token: str, tag_month: str, title: str):
    releases = list_releases(repo, token)
    for rel in releases:
        if rel.get("tag_name") == tag_month:
            return rel
    payload = json.dumps({
        "tag_name": tag_month,
        "name": title,
        "draft": False,
        "prerelease": False,
        "generate_release_notes": False,
    }).encode("utf-8")
    return _api_request(
        f"https://api.github.com/repos/{repo}/releases",
        token,
        method="POST",
        data=payload,
        headers={"Content-Type": "application/json"},
    )


def list_release_assets(repo: str, release_id: int, token: str):
    return _api_request(f"https://api.github.com/repos/{repo}/releases/{release_id}/assets", token) or []


def upload_release_asset(upload_url: str, token: str, zip_path: Path, asset_name: str):
    base = upload_url.split("{")[0]
    url = f"{base}?name={parse.quote(asset_name)}"
    ctype = mimetypes.guess_type(asset_name)[0] or "application/zip"
    data = zip_path.read_bytes()
    req = request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", ctype)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    try:
        with request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise GitHubReleaseError(f"GitHub upload error {e.code}: {body}")


def find_release_asset(repo: str, release_id: int, token: str, asset_name: str):
    for asset in list_release_assets(repo, release_id, token):
        if asset.get("name") == asset_name:
            return asset
    return None

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
PYPROJECT_VERSION_RE = re.compile(r'(?m)^(version\s*=\s*")([^"]+)(")$')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a GitHub Release for the current PiPhi integration/sidecar version."
    )
    parser.add_argument("--title", help="Optional release title. Defaults to v<version>.")
    parser.add_argument("--target", help="Optional commit/branch to tag from.")
    parser.add_argument("--draft", action="store_true", help="Create the GitHub release as a draft.")
    parser.add_argument(
        "--notes-file",
        help="Optional file path to use as release notes instead of auto-generated notes.",
    )
    parser.add_argument(
        "--verify-tag-absent",
        action="store_true",
        help="Fail if the GitHub release tag already exists.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root. Defaults to the parent directory of this script.",
    )
    parser.add_argument(
        "--pyproject",
        default="pyproject.toml",
        help="Path to pyproject.toml, relative to repo-root unless absolute.",
    )
    parser.add_argument(
        "--manifest",
        default="src/manifest.json",
        help="Path to manifest.json, relative to repo-root unless absolute.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the gh command without executing it.")
    return parser.parse_args()


def ensure_semver(value: str) -> str:
    if not SEMVER_RE.match(value):
        raise ValueError(f"Invalid semantic version: {value}")
    return value


def resolve_repo_root(value: str | None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def resolve_path(repo_root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def read_current_version(repo_root: Path, *, pyproject_rel: str, manifest_rel: str) -> str:
    pyproject_path = resolve_path(repo_root, pyproject_rel)
    manifest_path = resolve_path(repo_root, manifest_rel)

    pyproject_text = pyproject_path.read_text(encoding="utf-8")
    pyproject_match = PYPROJECT_VERSION_RE.search(pyproject_text)
    if pyproject_match is None:
        raise ValueError("Unable to find version in pyproject.toml")
    pyproject_version = ensure_semver(pyproject_match.group(2))

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_version = ensure_semver(str(manifest.get("version") or "").strip())
    if pyproject_version != manifest_version:
        raise ValueError(
            f"Version mismatch: pyproject.toml={pyproject_version} manifest.json={manifest_version}"
        )
    return pyproject_version


def check_gh_installed() -> None:
    if shutil.which("gh") is None:
        raise RuntimeError("GitHub CLI 'gh' is required to create a GitHub Release.")


def main() -> int:
    args = parse_args()
    repo_root = resolve_repo_root(args.repo_root)
    version = read_current_version(repo_root, pyproject_rel=args.pyproject, manifest_rel=args.manifest)
    tag = f"v{version}"
    prerelease = "-" in version
    title = args.title or tag

    if not args.dry_run or args.verify_tag_absent:
        check_gh_installed()

    if args.verify_tag_absent:
        result = subprocess.run(
            ["gh", "release", "view", tag],
            cwd=repo_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 0:
            raise RuntimeError(f"GitHub Release {tag} already exists.")

    command: list[str] = ["gh", "release", "create", tag, "--title", title]
    if args.notes_file:
        command.extend(["--notes-file", args.notes_file])
    else:
        command.append("--generate-notes")
    if prerelease:
        command.append("--prerelease")
    if args.draft:
        command.append("--draft")
    if args.target:
        command.extend(["--target", args.target])

    if args.dry_run:
        print(" ".join(command))
        return 0

    subprocess.run(command, cwd=repo_root, check=True)
    print(tag)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover
        print(f"create_github_release.py failed: {exc}", file=sys.stderr)
        raise SystemExit(1)

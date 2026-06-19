#!/usr/bin/env python3
"""
Optional app root folder rename at repository level (e.g. pimcore/ -> opendxp/)
plus path-string updates in the parent repo (docker-compose, deployment, …).

Run from the **repository root**, not from inside the app directory.

Usage:
  opendxp_migrate_root.py /path/to/repo audit  [--app-dir pimcore] [--target-dir opendxp]
  opendxp_migrate_root.py /path/to/repo rename [--config config/root.yaml] [--dry-run|--apply]
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from migrate_lib import (
    apply_directory_renames,
    apply_rules_to_text,
    audit_directories,
    build_app_root_path_rules,
    is_docker_compose_bind_mount_line,
    is_docker_compose_file,
    load_config,
    matches_any,
    read_text,
    root_migrate_line_in_scope,
)

DEFAULT_CONFIG: dict[str, Any] = {
    "root_files": [
        "docker-compose.yaml",
        "docker-compose.yml",
        ".gitmodules",
        "README.md",
    ],
    "scan_paths": ["deployment"],
    "exclude_globs": [
        "vendor/**",
        "node_modules/**",
        "tools/**",
        "mysql_data/**",
        ".git/**",
        "**/__pycache__/**",
        "**/*.sql.gz",
        "**/*.tgz",
    ],
    "manual_review_substrings": [
        "demo.pimcore.org",
        "pimcore.com",
        "pimcore.org",
    ],
}


def build_directory_renames(app_dir: str, target_dir: str) -> list[dict[str, str]]:
    return [{"from": app_dir, "to": target_dir}]


def iter_parent_files(
    repo_root: Path,
    app_dir: str,
    target_dir: str,
    config: dict[str, Any],
) -> list[Path]:
    exclude = list(config.get("exclude_globs", []))
    exclude.extend([f"{app_dir}/**", f"{target_dir}/**"])

    files: list[Path] = []
    for name in config.get("root_files", []):
        path = repo_root / name
        if path.is_file():
            files.append(path)

    for scan_path in config.get("scan_paths", []):
        base = repo_root / scan_path
        if not base.is_dir():
            continue
        for candidate in base.rglob("*"):
            if not candidate.is_file():
                continue
            rel = candidate.relative_to(repo_root)
            if rel.parts and rel.parts[0] in (app_dir, target_dir):
                continue
            if matches_any(rel, exclude):
                continue
            files.append(candidate)

    return sorted(set(files))


def check_layout(
    repo_root: Path,
    app_dir: str,
    target_dir: str,
) -> tuple[list[str], bool]:
    """Return validation errors and whether the folder rename was already applied."""
    errors: list[str] = []
    app_path = repo_root / app_dir
    target_path = repo_root / target_dir

    if app_dir == target_dir:
        errors.append(f"--app-dir and --target-dir must differ (both {app_dir!r})")
        return errors, False

    app_exists = app_path.is_dir()
    target_exists = target_path.is_dir()

    if app_exists and target_exists:
        errors.append(f"both {app_dir}/ and {target_dir}/ exist — resolve manually")
    elif target_exists and not app_exists:
        return [], True
    elif not app_exists:
        errors.append(f"app directory not found: {app_path}")

    return errors, False


def cmd_audit(args: argparse.Namespace) -> int:
    config = load_config(DEFAULT_CONFIG, args.config)
    repo_root = args.project.resolve()
    app_dir = args.app_dir
    target_dir = args.target_dir

    errors, already_migrated = check_layout(repo_root, app_dir, target_dir)
    if errors:
        for message in errors:
            print(f"[!!] {message}")
        return 1

    files = iter_parent_files(repo_root, app_dir, target_dir, config)
    rules = build_app_root_path_rules(app_dir, target_dir)

    print(f"Auditing parent repo {repo_root} (app {app_dir}/ -> {target_dir}/)")
    if already_migrated:
        print(f"[ok] root rename already applied ({target_dir}/)")
    print(f"Files scanned: {len(files)}\n")

    pattern_hits: dict[str, set[str]] = defaultdict(set)
    manual_markers = config.get("manual_review_substrings", [])

    for file_path in files:
        rel = str(file_path.relative_to(repo_root))
        for line_no, line in enumerate(read_text(file_path).splitlines(), start=1):
            if root_migrate_line_in_scope(line, file_path, rules, manual_markers):
                pattern_hits[rel].add(f"line {line_no}")

    has_findings = False
    if pattern_hits:
        has_findings = True
        total = sum(len(lines) for lines in pattern_hits.values())
        print(f"[!!] path references to `{app_dir}`: {total} line(s) in {len(pattern_hits)} file(s)")
        for rel, lines in sorted(pattern_hits.items()):
            print(f"      {rel}: {', '.join(sorted(lines)[:5])}")
    else:
        print(f"[ok] path references to `{app_dir}`: no matches in parent scope")

    dir_pending, dir_messages = audit_directories(
        repo_root,
        build_directory_renames(app_dir, target_dir),
    )
    has_findings = has_findings or dir_pending
    for message in dir_messages:
        print(message)

    if not has_findings:
        if already_migrated:
            print("\nAudit finished clean (migration already applied).")
        else:
            print("\nAudit finished clean.")
    else:
        print("\nRun rename --dry-run, then --apply when ready.")

    return 1 if has_findings else 0


def cmd_rename(args: argparse.Namespace) -> int:
    config = load_config(DEFAULT_CONFIG, args.config)
    repo_root = args.project.resolve()
    app_dir = args.app_dir
    target_dir = args.target_dir
    apply = args.apply

    errors, already_migrated = check_layout(repo_root, app_dir, target_dir)
    if errors:
        for message in errors:
            print(f"[!!] {message}", file=sys.stderr)
        return 1

    if already_migrated:
        print(f"Root rename already applied ({target_dir}/). Nothing to do.")
        return 0

    files = iter_parent_files(repo_root, app_dir, target_dir, config)
    rules = build_app_root_path_rules(app_dir, target_dir)
    manual_markers = config.get("manual_review_substrings", [])

    mode = "Applying" if apply else "Dry-run"
    print(f"{mode} parent-repo root rename in {repo_root} ({app_dir}/ -> {target_dir}/)")
    print(f"Files to patch: {len(files)}\n")

    for file_path in files:
        rel = file_path.relative_to(repo_root)
        original = read_text(file_path)
        if is_docker_compose_file(file_path):
            skip = lambda line: not is_docker_compose_bind_mount_line(line)
        else:
            skip = None
        updated, changes = apply_rules_to_text(
            original,
            rules,
            manual_markers,
            skip=skip,
        )
        if not changes:
            continue
        print(f"{'patch' if apply else 'plan'} {rel}:")
        seen: set[str] = set()
        for change in changes:
            if change in seen:
                continue
            seen.add(change)
            print(f"  - {change}")
        if apply:
            file_path.write_text(updated, encoding="utf-8")

    print()
    for message in apply_directory_renames(
        repo_root,
        build_directory_renames(app_dir, target_dir),
        apply,
    ):
        print(message)

    if not apply:
        print("\nDry-run complete. Re-run with --apply to write changes.")
    else:
        print("\nDone. Update submodule paths and re-run preflight against ./opendxp (or your target name).")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Optional app root folder rename at repository level.",
    )
    parser.add_argument(
        "project",
        type=Path,
        help="Repository root (parent of the app folder, e.g. .)",
    )
    parser.add_argument(
        "--app-dir",
        default="pimcore",
        help="Current app directory name under the repo root (default: pimcore)",
    )
    parser.add_argument(
        "--target-dir",
        default="opendxp",
        help="Target app directory name (default: opendxp)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Optional YAML config merged over built-in defaults (e.g. config/root.yaml)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("audit", help="Report parent-repo path references and pending folder rename.")

    rename = sub.add_parser("rename", help="Patch parent paths and rename the app folder.")
    group = rename.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Show planned changes only.")
    group.add_argument("--apply", action="store_true", help="Write changes and rename the folder.")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.project.is_dir():
        print(f"Repository directory not found: {args.project}", file=sys.stderr)
        return 2
    if args.command == "audit":
        return cmd_audit(args)
    if args.command == "rename":
        return cmd_rename(args)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Audit and patch class definitions, var/config, src/Resources and config/.

Usage:
  opendxp_migrate_definitions.py audit  /path/to/project [--config config/definitions.yaml]
  opendxp_migrate_definitions.py patch  /path/to/project [--config ...] [--dry-run|--apply]
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from migrate_lib import (
    COMMON_DIRECTORY_RENAMES,
    COMMON_JS_REPLACEMENTS,
    COMMON_PATH_REPLACEMENTS,
    apply_directory_renames,
    apply_rules_to_text,
    audit_directories,
    is_manual_review_line,
    iter_files,
    load_config,
    read_text,
)

DEFAULT_CONFIG: dict[str, Any] = {
    "scan_paths": [
        "var/classes",
        "var/config",
        "src/Resources",
        "config",
    ],
    "exclude_globs": [
        "vendor/**",
        "var/cache/**",
        "var/tmp/**",
        "src/Migrations/**",
        "**/ckeditor-plugins/**",
    ],
    "manual_review_substrings": [
        "Pimcore-Schulung",
        "demo.pimcore.org",
        "pimcore.com",
        "pimcore.org",
    ],
    "audit_patterns": [
        {"name": "php-model-namespace", "pattern": r"\bPimcore\\Model\\"},
        {"name": "php-bundle-namespace", "pattern": r"\bPimcore\\Bundle\\"},
        {"name": "php-facade", "pattern": r"\\Pimcore::"},
        {"name": "class-layout-root", "pattern": r"\bpimcore_root\b"},
        {"name": "admin-icon-path", "pattern": r"/bundles/pimcoreadmin/"},
        {"name": "bundle-asset-path", "pattern": r"/bundles/pimcore/"},
        {"name": "app-bundle-js-path", "pattern": r"/bundles/app/pimcore/"},
        {"name": "admin-icon-class", "pattern": r"\bpimcore_icon_[a-zA-Z0-9_-]+"},
        {"name": "portal-portlets", "pattern": r"\bpimcore\.layout\.portlets\."},
        {"name": "portal-layout", "pattern": r"\bpimcore\.layout\."},
        {"name": "js-global", "pattern": r"\bpimcore\.[a-zA-Z]"},
        {
            "name": "config-path",
            "pattern": r"""(?:^|["'])(?:src/Resources/)?config/pimcore(?:/|["']|$)""",
        },
        {"name": "resources-public-path", "pattern": r"src/Resources/public/pimcore(?:/|$)"},
        {"name": "return-model-namespace", "pattern": r"return Pimcore\\Model\\"},
    ],
    "replacement_rules": [
        {"name": "php-model-namespace", "from": "Pimcore\\Model\\", "to": "OpenDxp\\Model\\"},
        {"name": "php-bundle-namespace", "from": "Pimcore\\Bundle\\", "to": "OpenDxp\\Bundle\\"},
        {"name": "php-facade", "from": "\\Pimcore::", "to": "\\OpenDxp::"},
        {"name": "class-layout-root", "from": "pimcore_root", "to": "opendxp_root"},
        {"name": "admin-icon-class-prefix", "from": "pimcore_icon_", "to": "opendxp_icon_"},
        *COMMON_PATH_REPLACEMENTS,
        *COMMON_JS_REPLACEMENTS,
    ],
    "directory_renames": COMMON_DIRECTORY_RENAMES,
}


def cmd_audit(args: argparse.Namespace) -> int:
    config = load_config(DEFAULT_CONFIG, args.config)
    project_root = args.project.resolve()
    files = iter_files(project_root, config["scan_paths"], config["exclude_globs"])
    if not files:
        print(f"No files found under {project_root} (check scan_paths in config).")
        return 1

    print(f"Auditing definitions/config/resources in {project_root}")
    print(f"Files scanned: {len(files)}\n")

    compiled = [
        (item["name"], re.compile(item["pattern"]))
        for item in config.get("audit_patterns", [])
    ]
    manual_markers = config.get("manual_review_substrings", [])
    pattern_hits: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    manual_hits: dict[str, list[str]] = defaultdict(list)

    for file_path in files:
        rel = str(file_path.relative_to(project_root))
        for line_no, line in enumerate(read_text(file_path).splitlines(), start=1):
            if is_manual_review_line(line, manual_markers):
                for marker in manual_markers:
                    if marker in line:
                        manual_hits[rel].append(f"line {line_no}: contains {marker!r}")
            for name, regex in compiled:
                if is_manual_review_line(line, manual_markers):
                    continue
                for match in regex.findall(line):
                    pattern_hits[name][rel].add(match)

    has_findings = False
    for name, _regex in compiled:
        file_map = pattern_hits.get(name, {})
        if not file_map:
            print(f"[ok] {name}: no matches")
            continue
        has_findings = True
        total = sum(len(values) for values in file_map.values())
        print(f"[!!] {name}: {total} match(es) in {len(file_map)} file(s)")
        for rel, values in sorted(file_map.items()):
            preview = ", ".join(sorted(values)[:6])
            suffix = " ..." if len(values) > 6 else ""
            print(f"      {rel}: {preview}{suffix}")

    dir_has_findings, dir_messages = audit_directories(
        project_root,
        config.get("directory_renames", []),
    )
    has_findings = has_findings or dir_has_findings
    if dir_messages:
        print()
        for message in dir_messages:
            print(message)

    if manual_hits:
        print("\n[..] manual review (not auto-patched):")
        for rel, notes in sorted(manual_hits.items()):
            for note in notes[:3]:
                print(f"      {rel}: {note}")
            if len(notes) > 3:
                print(f"      {rel}: ... {len(notes) - 3} more")

    if has_findings:
        print("\nAudit finished with findings.")
    else:
        print("\nAudit finished clean.")

    print(
        "\nAfter patching, run:\n"
        "  bin/console opendxp:deployment:classes-rebuild -c -v\n"
        "  bin/console opendxp:cache:clear"
    )
    return 1 if has_findings else 0


def cmd_patch(args: argparse.Namespace) -> int:
    if not args.apply and not args.dry_run:
        args.dry_run = True

    config = load_config(DEFAULT_CONFIG, args.config)
    project_root = args.project.resolve()
    files = iter_files(project_root, config["scan_paths"], config["exclude_globs"])
    rules = config.get("replacement_rules", [])
    manual_markers = config.get("manual_review_substrings", [])

    print(f"{'Applying' if args.apply else 'Dry-run'} patch in {project_root}")
    print(f"Files considered: {len(files)}\n")

    changed_files = 0
    for file_path in files:
        rel = file_path.relative_to(project_root)
        original = read_text(file_path)
        updated, file_changes = apply_rules_to_text(original, rules, manual_markers)

        if updated != original:
            changed_files += 1
            print(f"{'[write]' if args.apply else '[plan]'} {rel}")
            seen: set[str] = set()
            for change in file_changes:
                if change not in seen:
                    seen.add(change)
                    print(f"        {change}")
            if args.apply:
                file_path.write_text(updated, encoding="utf-8")

    dir_messages = apply_directory_renames(
        project_root,
        config.get("directory_renames", []),
        apply=args.apply,
    )
    if dir_messages:
        print()
        for message in dir_messages:
            print(message)

    print(
        f"\n{'Applied' if args.apply else 'Planned'} content changes in "
        f"{changed_files} file(s)."
    )
    if args.dry_run and (changed_files or dir_messages):
        print("Re-run with --apply to write changes.")
    if changed_files or dir_messages:
        print(
            "\nRecommended follow-up:\n"
            "  bin/console opendxp:deployment:classes-rebuild -c -v\n"
            "  bin/console opendxp:cache:clear"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit/patch definitions, var/config, src/Resources and config/.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit", help="Report Pimcore remnants.")
    audit.add_argument("project", type=Path, help="Project root (e.g. ./opendxp)")
    audit.add_argument("--config", type=Path, default=None, help="Optional YAML config")
    audit.set_defaults(func=cmd_audit)

    patch = sub.add_parser("patch", help="Apply configured replacements and directory renames.")
    patch.add_argument("project", type=Path, help="Project root (e.g. ./opendxp)")
    patch.add_argument("--config", type=Path, default=None, help="Optional YAML config")
    mode = patch.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Show planned changes (default)")
    mode.add_argument("--apply", action="store_true", help="Write changes to disk")
    patch.set_defaults(func=cmd_patch)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.config is not None and not args.config.is_file():
        print(f"Config not found: {args.config}", file=sys.stderr)
        return 2
    if not args.project.is_dir():
        print(f"Project directory not found: {args.project}", file=sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

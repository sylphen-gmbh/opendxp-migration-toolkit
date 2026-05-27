#!/usr/bin/env python3
"""
Audit and rename helpers for Pimcore v11 -> OpenDXP v1 migrations.

Usage:
  opendxp_migrate.py audit  /path/to/project [--config config/default.yaml]
  opendxp_migrate.py rename /path/to/project [--config ...] [--dry-run|--apply]
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from migrate_lib import (
    COMMON_DIRECTORY_RENAMES,
    COMMON_JS_REPLACEMENTS,
    COMMON_PATH_REPLACEMENTS,
    apply_directory_renames,
    audit_directories,
)

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


DEFAULT_CONFIG: dict[str, Any] = {
    "scan_paths": [
        "templates",
        "public/static/css",
        "src",
        "config",
    ],
    "exclude_globs": [
        "vendor/**",
        "var/**",
        "node_modules/**",
        "web/js/fos_js_routes.js",
        "**/fos_js_routes.js",
    ],
    "audit_patterns": [
        {"name": "twig-functions", "pattern": r"\bpimcore_[a-zA-Z0-9_]+"},
        {"name": "php-namespace", "pattern": r"\bPimcore\\"},
        {"name": "php-constants", "pattern": r"\bPIMCORE_[A-Z0-9_]+"},
        {"name": "config-blocks", "pattern": r"\bpimcore_[a-zA-Z0-9_-]+:"},
        {"name": "css-area-classes", "pattern": r"\bpimcore_area_[a-zA-Z0-9_-]+"},
        {"name": "css-tag-classes", "pattern": r"\bpimcore_tag_[a-zA-Z0-9_-]+"},
        {"name": "css-wysiwyg-class", "pattern": r"\bpimcore_wysiwyg\b"},
        {"name": "commands", "pattern": r"\bpimcore:[a-zA-Z0-9:-]+"},
        {"name": "js-global", "pattern": r"\bpimcore\.[a-zA-Z]"},
        {"name": "config-path", "pattern": r"(?:^|[\"'])(?:src/Resources/)?config/pimcore(?:/|[\"']|$)"},
        {"name": "portal-layout", "pattern": r"\bpimcore\.layout\."},
    ],
    "area_class_sources": {
        "templates_glob": "**/*.twig",
        "template_pattern": r"\bopendxp_area_[a-zA-Z0-9_-]+",
        "css_glob": "**/*.css",
        "css_patterns": [
            r"\bopendxp_area_[a-zA-Z0-9_-]+",
            r"\bpimcore_area_[a-zA-Z0-9_-]+",
        ],
    },
    "replacement_groups": [
        {
            "name": "twig",
            "globs": ["**/*.twig"],
            "rules": [{"from": "pimcore_", "to": "opendxp_"}],
        },
        {
            "name": "css",
            "globs": ["**/*.css"],
            "rules": [
                {"from": "pimcore_area_", "to": "opendxp_area_"},
                {"from": "pimcore_tag_", "to": "opendxp_editable_"},
                {"from": "pimcore_wysiwyg", "to": "opendxp_editable_wysiwyg"},
            ],
        },
        {
            "name": "php",
            "globs": ["**/*.php"],
            "rules": [
                {"from": "Pimcore\\", "to": "OpenDxp\\"},
                {"from": "PIMCORE_", "to": "OPENDXP_"},
            ],
        },
        {
            "name": "yaml",
            "globs": ["**/*.yaml", "**/*.yml"],
            "rules": [{"from": "pimcore_", "to": "opendxp_"}],
        },
        {
            "name": "js",
            "globs": ["**/*.js"],
            "rules": [
                {"from": rule["from"], "to": rule["to"]}
                for rule in COMMON_JS_REPLACEMENTS
            ],
        },
        {
            "name": "paths",
            "globs": ["**/*"],
            "rules": [
                {"from": rule["from"], "to": rule["to"]}
                for rule in COMMON_PATH_REPLACEMENTS
            ],
        },
    ],
    "directory_renames": COMMON_DIRECTORY_RENAMES,
    "manual_review_substrings": [
        "Pimcore-Schulung",
        "demo.pimcore.org",
        "pimcore.com",
        "pimcore.org",
    ],
}


@dataclass
class Config:
    root: Path
    data: dict[str, Any] = field(default_factory=lambda: DEFAULT_CONFIG.copy())

    @classmethod
    def load(cls, project_root: Path, config_path: Path | None) -> Config:
        data = _deep_copy(DEFAULT_CONFIG)
        if config_path is not None:
            data = _merge_dict(data, _load_yaml(config_path))
        return cls(root=project_root.resolve(), data=data)


def _deep_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _deep_copy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deep_copy(v) for v in value]
    return value


def _merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = _deep_copy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = _deep_copy(value)
    return merged


def _load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise SystemExit(
            "PyYAML is required for custom config files. Install with: pip install pyyaml\n"
            "Or omit --config to use built-in defaults."
        )
    with path.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise SystemExit(f"Config must be a mapping: {path}")
    return loaded


def _matches_any(path: Path, patterns: list[str]) -> bool:
    normalized = path.as_posix()
    for pattern in patterns:
        if fnmatch.fnmatch(normalized, pattern):
            return True
        if fnmatch.fnmatch(path.name, pattern):
            return True
    return False


def iter_files(project_root: Path, config: Config) -> list[Path]:
    scan_paths = config.data.get("scan_paths", [])
    exclude_globs = config.data.get("exclude_globs", [])
    files: list[Path] = []

    for scan_path in scan_paths:
        base = project_root / scan_path
        if not base.exists():
            continue
        if base.is_file():
            candidates = [base]
        else:
            candidates = [p for p in base.rglob("*") if p.is_file()]

        for candidate in candidates:
            rel = candidate.relative_to(project_root)
            if _matches_any(rel, exclude_globs):
                continue
            files.append(candidate)

    return sorted(set(files))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def cmd_audit(args: argparse.Namespace) -> int:
    config = Config.load(args.project, args.config)
    files = iter_files(config.root, config)
    if not files:
        print(f"No files found under {config.root} (check scan_paths in config).")
        return 1

    print(f"Auditing {config.root}")
    print(f"Files scanned: {len(files)}\n")

    pattern_hits: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    compiled = [
        (item["name"], re.compile(item["pattern"]))
        for item in config.data.get("audit_patterns", [])
    ]

    for file_path in files:
        rel = file_path.relative_to(config.root)
        text = read_text(file_path)
        for name, regex in compiled:
            for match in regex.findall(text):
                pattern_hits[name][str(rel)].add(match)

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
            preview = ", ".join(sorted(values)[:8])
            suffix = " ..." if len(values) > 8 else ""
            print(f"      {rel}: {preview}{suffix}")

    print()
    has_findings = _audit_area_class_mismatch(config, files) or has_findings

    dir_has_findings, dir_messages = audit_directories(
        config.root,
        config.data.get("directory_renames", []),
    )
    has_findings = has_findings or dir_has_findings
    if dir_messages:
        for message in dir_messages:
            print(message)

    return 1 if has_findings else 0


def _audit_area_class_mismatch(config: Config, files: list[Path]) -> bool:
    area_cfg = config.data.get("area_class_sources")
    if not area_cfg:
        return False

    tpl_pattern = re.compile(area_cfg["template_pattern"])
    css_patterns = [re.compile(p) for p in area_cfg["css_patterns"]]
    tpl_glob = area_cfg["templates_glob"]
    css_glob = area_cfg["css_glob"]

    template_areas: set[str] = set()
    css_areas: set[str] = set()

    for file_path in files:
        rel = file_path.relative_to(config.root)
        if fnmatch.fnmatch(rel.as_posix(), tpl_glob):
            template_areas.update(tpl_pattern.findall(read_text(file_path)))
        if fnmatch.fnmatch(rel.as_posix(), css_glob):
            text = read_text(file_path)
            for regex in css_patterns:
                css_areas.update(regex.findall(text))

    css_opendxp = {a for a in css_areas if a.startswith("opendxp_area_")}
    css_pimcore = {a for a in css_areas if a.startswith("pimcore_area_")}

    mismatches: list[str] = []
    without_css: list[str] = []
    for area in sorted(template_areas):
        if area in css_opendxp:
            continue
        legacy = area.replace("opendxp_area_", "pimcore_area_", 1)
        if legacy in css_pimcore:
            mismatches.append(f"{area}  (CSS still uses {legacy})")
        else:
            without_css.append(area)

    if mismatches:
        print("[!!] area-class mismatch (template vs CSS):")
        for line in mismatches:
            print(f"      {line}")
    else:
        print("[ok] area-class mismatch: none")

    if without_css:
        print(f"[..] area-class without dedicated CSS ({len(without_css)}): "
              + ", ".join(without_css))

    return bool(mismatches)


def file_matches_globs(rel: Path, globs: list[str]) -> bool:
    rel_posix = rel.as_posix()
    return any(fnmatch.fnmatch(rel_posix, pattern) for pattern in globs)


def cmd_rename(args: argparse.Namespace) -> int:
    if not args.apply and not args.dry_run:
        args.dry_run = True

    config = Config.load(args.project, args.config)
    files = iter_files(config.root, config)
    groups = config.data.get("replacement_groups", [])
    manual_markers = config.data.get("manual_review_substrings", [])

    print(f"{'Applying' if args.apply else 'Dry-run'} rename in {config.root}")
    print(f"Files considered: {len(files)}\n")

    changed_files = 0

    for file_path in files:
        rel = file_path.relative_to(config.root)
        original = read_text(file_path)
        file_changes: list[str] = []
        updated_lines: list[str] = []

        for line in original.splitlines(keepends=True):
            new_line = line
            if not any(marker in line for marker in manual_markers):
                for group in groups:
                    if not file_matches_globs(rel, group.get("globs", [])):
                        continue
                    for rule in group.get("rules", []):
                        src = rule["from"]
                        dst = rule["to"]
                        count = new_line.count(src)
                        if count:
                            new_line = new_line.replace(src, dst)
                            file_changes.append(
                                f"{group['name']}: {src!r} -> {dst!r} ({count}x)"
                            )
            updated_lines.append(new_line)

        updated = "".join(updated_lines)

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
        config.root,
        config.data.get("directory_renames", []),
        apply=args.apply,
    )
    if dir_messages:
        print()
        for message in dir_messages:
            print(message)

    print(
        f"\n{'Applied' if args.apply else 'Planned'} changes in "
        f"{changed_files} file(s)."
    )
    if args.dry_run and changed_files:
        print("Re-run with --apply to write changes.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit/rename helpers for Pimcore -> OpenDXP migrations.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit", help="Report remaining Pimcore identifiers.")
    audit.add_argument("project", type=Path, help="Project root (e.g. ./pimcore)")
    audit.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Optional YAML config (defaults are built in)",
    )
    audit.set_defaults(func=cmd_audit)

    rename = sub.add_parser("rename", help="Apply configured text replacements.")
    rename.add_argument("project", type=Path, help="Project root (e.g. ./pimcore)")
    rename.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Optional YAML config (defaults are built in)",
    )
    mode = rename.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Show planned changes (default)")
    mode.add_argument("--apply", action="store_true", help="Write changes to disk")
    rename.set_defaults(func=cmd_rename)

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

"""Shared helpers for opendxp-migration-toolkit scripts."""

from __future__ import annotations

import fnmatch
from collections.abc import Callable
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

COMMON_PATH_REPLACEMENTS: list[dict[str, str]] = [
    {"name": "portal-portlets", "from": "pimcore.layout.portlets.", "to": "opendxp.layout.portlets."},
    {"name": "portal-layout", "from": "pimcore.layout.", "to": "opendxp.layout."},
    {"name": "resources-config-path", "from": "src/Resources/config/pimcore/", "to": "src/Resources/config/opendxp/"},
    {"name": "resources-config-path-no-slash", "from": "src/Resources/config/pimcore", "to": "src/Resources/config/opendxp"},
    {"name": "app-config-path", "from": "config/pimcore/", "to": "config/opendxp/"},
    {"name": "app-config-path-no-slash", "from": "config/pimcore", "to": "config/opendxp"},
    {"name": "resources-public-path", "from": "src/Resources/public/pimcore/", "to": "src/Resources/public/opendxp/"},
    {"name": "resources-public-path-no-slash", "from": "src/Resources/public/pimcore", "to": "src/Resources/public/opendxp"},
    {"name": "app-bundle-js-path", "from": "/bundles/app/pimcore/", "to": "/bundles/app/opendxp/"},
    {"name": "admin-icon-path", "from": "/bundles/pimcoreadmin/", "to": "/bundles/opendxpadmin/"},
    {"name": "bundle-asset-path", "from": "/bundles/pimcore/", "to": "/bundles/opendxp/"},
]

COMMON_JS_REPLACEMENTS: list[dict[str, str]] = [
    {"name": "js-document", "from": "pimcore.document", "to": "opendxp.document"},
    {"name": "js-object", "from": "pimcore.object", "to": "opendxp.object"},
    {"name": "js-typeof", "from": "typeof pimcore", "to": "typeof opendxp"},
    {"name": "js-global", "from": "pimcore.", "to": "opendxp."},
]

COMMON_DIRECTORY_RENAMES: list[dict[str, str]] = [
    {"from": "src/Resources/config/pimcore", "to": "src/Resources/config/opendxp"},
    {"from": "config/pimcore", "to": "config/opendxp"},
    {"from": "src/Resources/public/pimcore", "to": "src/Resources/public/opendxp"},
]


def deep_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: deep_copy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [deep_copy(v) for v in value]
    return value


def merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deep_copy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dict(merged[key], value)
        else:
            merged[key] = deep_copy(value)
    return merged


def load_yaml(path: Path) -> dict[str, Any]:
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


def load_config(defaults: dict[str, Any], config_path: Path | None) -> dict[str, Any]:
    data = deep_copy(defaults)
    if config_path is not None:
        data = merge_dict(data, load_yaml(config_path))
    return data


def matches_any(path: Path, patterns: list[str]) -> bool:
    normalized = path.as_posix()
    for pattern in patterns:
        if fnmatch.fnmatch(normalized, pattern):
            return True
        if fnmatch.fnmatch(path.name, pattern):
            return True
    return False


def iter_files(project_root: Path, scan_paths: list[str], exclude_globs: list[str]) -> list[Path]:
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
            if matches_any(rel, exclude_globs):
                continue
            files.append(candidate)

    return sorted(set(files))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def file_matches_globs(rel: Path, globs: list[str]) -> bool:
    rel_posix = rel.as_posix()
    return any(fnmatch.fnmatch(rel_posix, pattern) for pattern in globs)


def is_manual_review_line(line: str, markers: list[str]) -> bool:
    return any(marker in line for marker in markers)


def apply_rules_to_line(
    line: str,
    rules: list[dict[str, str]],
    skip: Callable[[str], bool] | None = None,
) -> tuple[str, list[str]]:
    if skip and skip(line):
        return line, []

    changes: list[str] = []
    updated = line
    for rule in rules:
        src = rule["from"]
        dst = rule["to"]
        count = updated.count(src)
        if count:
            updated = updated.replace(src, dst)
            changes.append(f"{rule['name']}: {src!r} -> {dst!r} ({count}x)")
    return updated, changes


def apply_rules_to_text(
    text: str,
    rules: list[dict[str, str]],
    manual_markers: list[str] | None = None,
) -> tuple[str, list[str]]:
    markers = manual_markers or []
    lines: list[str] = []
    all_changes: list[str] = []

    for line in text.splitlines(keepends=True):
        updated, changes = apply_rules_to_line(
            line,
            rules,
            skip=lambda value: is_manual_review_line(value, markers),
        )
        lines.append(updated)
        all_changes.extend(changes)

    return "".join(lines), all_changes


def audit_directories(project_root: Path, renames: list[dict[str, str]]) -> tuple[bool, list[str]]:
    messages: list[str] = []
    has_findings = False

    for item in renames:
        src = project_root / item["from"]
        dst = project_root / item["to"]
        if src.is_dir():
            has_findings = True
            messages.append(f"[!!] directory rename pending: {item['from']} -> {item['to']}")
        elif dst.is_dir():
            messages.append(f"[ok] directory already renamed: {item['to']}")

    return has_findings, messages


def apply_directory_renames(
    project_root: Path,
    renames: list[dict[str, str]],
    apply: bool,
) -> list[str]:
    messages: list[str] = []

    for item in renames:
        src = project_root / item["from"]
        dst = project_root / item["to"]
        if not src.is_dir():
            continue
        if dst.exists():
            messages.append(f"[skip] {item['from']} -> {item['to']} (target exists)")
            continue
        label = "rename" if apply else "plan"
        messages.append(f"[{label}] {item['from']} -> {item['to']}")
        if apply:
            src.rename(dst)

    return messages

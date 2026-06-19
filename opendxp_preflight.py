#!/usr/bin/env python3
"""
Preflight checks for Pimcore v11 -> OpenDXP v1 migrations.

Read-only environment & repository checks. Run this FIRST, before `composer update`,
to surface the blockers the rename/patch scripts deliberately do NOT handle
(PHP version, composer packages, bootstrap files, routing/security/templating).

Also checks project layout: app directory vs. repository root, optional legacy
`pimcore/` folder name, and parent-repo path references (for optional
`opendxp_migrate_root.py`).

Usage:
  opendxp_preflight.py /path/to/project [--min-php 8.3]

Exit codes:
  0 = no FAIL findings (WARN may still be present)
  1 = at least one FAIL finding
  2 = bad invocation
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from migrate_lib import build_app_root_path_rules, root_migrate_line_in_scope

OK = "OK"
WARN = "WARN"
FAIL = "FAIL"
SKIP = "SKIP"

LABEL = {OK: "[ OK ]", WARN: "[WARN]", FAIL: "[FAIL]", SKIP: "[SKIP]"}


@dataclass
class Result:
    level: str
    title: str
    detail: str = ""


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def tree_grep(base: Path, pattern: str, suffixes: tuple[str, ...]) -> list[str]:
    rx = re.compile(pattern)
    hits: list[str] = []
    if not base.is_dir():
        return hits
    for path in base.rglob("*"):
        if path.is_file() and path.suffix in suffixes and rx.search(read_text(path)):
            hits.append(path.as_posix())
    return hits


def check_php_version(min_php: tuple[int, int]) -> Result:
    php = shutil.which("php")
    target = f"{min_php[0]}.{min_php[1]}"
    if not php:
        return Result(
            SKIP, "PHP version",
            f"`php` not on PATH - run inside the app container; OpenDXP needs >= {target}.",
        )
    try:
        out = subprocess.run(
            [php, "-r", "echo PHP_VERSION;"],
            capture_output=True, text=True, timeout=15,
        ).stdout.strip()
    except Exception as exc:  # noqa: BLE001
        return Result(WARN, "PHP version", f"could not run php: {exc}")
    match = re.match(r"(\d+)\.(\d+)", out)
    if not match:
        return Result(WARN, "PHP version", f"unparseable version: {out!r}")
    current = (int(match.group(1)), int(match.group(2)))
    if current < min_php:
        return Result(
            FAIL, "PHP version",
            f"{out} < required {target} - bump the docker image "
            f"(e.g. pimcore/pimcore:php8.3-debug-latest).",
        )
    return Result(OK, "PHP version", out)


def is_app_root(path: Path) -> bool:
    if not (path / "composer.json").is_file():
        return False
    return (path / "bin/console").is_file() or (path / "public/index.php").is_file()


def scan_parent_path_refs(parent: Path, app_dir_name: str) -> list[str]:
    """Parent-repo files with path references that root rename would patch."""
    rules = build_app_root_path_rules(app_dir_name, "opendxp")
    candidates: list[Path] = [
        parent / "docker-compose.yaml",
        parent / "docker-compose.yml",
        parent / ".gitmodules",
    ]
    deployment = parent / "deployment"
    if deployment.is_dir():
        candidates.extend(p for p in deployment.iterdir() if p.is_file())
    hits: list[str] = []
    for path in candidates:
        if not path.is_file():
            continue
        for line in read_text(path).splitlines():
            if root_migrate_line_in_scope(line, path, rules):
                hits.append(path.relative_to(parent).as_posix())
                break
    return hits


def check_project_layout(root: Path) -> list[Result]:
    results: list[Result] = []

    if not is_app_root(root):
        for name in ("pimcore", "opendxp"):
            child = root / name
            if child.is_dir() and is_app_root(child):
                return [Result(
                    WARN, "project root",
                    f"not an app directory — pass ./{name} "
                    f"(e.g. opendxp_preflight.py ./{name})",
                )]
        return [Result(
            WARN, "project root",
            "does not look like an app root "
            "(expected composer.json and bin/console or public/index.php)",
        )]

    results.append(Result(OK, "project root", "valid app directory"))

    name = root.name
    if name == "pimcore":
        results.append(Result(
            WARN, "app folder name",
            "still `pimcore/` — OpenDXP does not require renaming to `opendxp/`. "
            "An optional parent-repo rename is available via "
            "`opendxp_migrate_root.py` (run from the repository root). "
            "Keep using this path for all toolkit commands until then.",
        ))
    elif name == "opendxp":
        results.append(Result(OK, "app folder name", "`opendxp/`"))
    else:
        results.append(Result(OK, "app folder name", f"custom directory `{name}/`"))

    if name == "pimcore":
        parent_refs = scan_parent_path_refs(root.parent, name)
        if parent_refs:
            sample = ", ".join(parent_refs[:3])
            extra = f" (+{len(parent_refs) - 3} more)" if len(parent_refs) > 3 else ""
            results.append(Result(
                WARN, "parent path references",
                f"{len(parent_refs)} file(s) outside the app reference `{name}/` "
                f"({sample}{extra}) — use `opendxp_migrate_root.py audit` "
                f"from the repository root to review a rename",
            ))

    return results


def check_composer(root: Path) -> list[Result]:
    composer = root / "composer.json"
    if not composer.is_file():
        return [Result(SKIP, "composer.json", "not found")]
    try:
        data = json.loads(read_text(composer))
    except json.JSONDecodeError as exc:
        return [Result(WARN, "composer.json", f"invalid JSON: {exc}")]

    require = {**data.get("require", {}), **data.get("require-dev", {})}
    results: list[Result] = []

    if "pimcore/pimcore" in require:
        results.append(Result(FAIL, "composer core",
                              "pimcore/pimcore present -> replace with open-dxp/opendxp"))
    elif "open-dxp/opendxp" in require:
        results.append(Result(OK, "composer core", "open-dxp/opendxp"))
    else:
        results.append(Result(WARN, "composer core",
                              "neither pimcore/pimcore nor open-dxp/opendxp found"))

    pimcore_pkgs = sorted(k for k in require if k.startswith("pimcore/"))
    if pimcore_pkgs:
        results.append(Result(WARN, "composer pimcore packages",
                              "still present (map to open-dxp/* or drop): "
                              + ", ".join(pimcore_pkgs)))

    symfony6 = sorted(
        k for k, v in require.items()
        if k.startswith("symfony/") and re.search(r"(^|[^\d])6\.", str(v))
    )
    if symfony6:
        results.append(Result(WARN, "symfony version",
                              "constrained to 6.x (OpenDXP needs ^7.4): "
                              + ", ".join(symfony6)))

    autoload = data.get("autoload", {}).get("psr-4", {})
    if "Pimcore\\Model\\DataObject\\" in autoload:
        results.append(Result(WARN, "composer autoload",
                              "psr-4 still maps Pimcore\\Model\\DataObject\\ "
                              "-> OpenDxp\\Model\\DataObject\\"))
    return results


def check_bootstrap(root: Path) -> list[Result]:
    results: list[Result] = []
    for rel in ("bin/console", "public/index.php"):
        path = root / rel
        if not path.is_file():
            results.append(Result(SKIP, f"bootstrap {rel}", "not found"))
            continue
        text = read_text(path)
        if "Pimcore\\Bootstrap" in text or "Pimcore\\Console" in text:
            results.append(Result(
                FAIL, f"bootstrap {rel}",
                "still references Pimcore\\Bootstrap/Console - patch it "
                "(outside the default scan paths!) or copy the OpenDXP skeleton file.",
            ))
        else:
            results.append(Result(OK, f"bootstrap {rel}", "no Pimcore bootstrap reference"))
    return results


def check_routes(root: Path) -> Result:
    hits = []
    rx = re.compile(r"type:\s*['\"]?annotation")
    base = root / "config"
    if base.is_dir():
        for path in base.rglob("*"):
            if path.suffix in (".yaml", ".yml") and rx.search(read_text(path)):
                hits.append(path.relative_to(root).as_posix())
    if hits:
        return Result(WARN, "routing loader",
                      "`type: annotation` (use `attribute` on Symfony 7): " + ", ".join(hits))
    return Result(OK, "routing loader", "no `type: annotation`")


def check_security(root: Path) -> list[Result]:
    path = root / "config/packages/security.yaml"
    if not path.is_file():
        return [Result(SKIP, "security.yaml", "not found")]
    text = read_text(path)
    results: list[Result] = []
    if "enable_authenticator_manager" in text:
        results.append(Result(WARN, "security authenticator",
                              "remove `enable_authenticator_manager` (gone in Symfony 7.3)"))
    if "ROLE_PIMCORE_" in text:
        results.append(Result(WARN, "security roles",
                              "ROLE_PIMCORE_* -> ROLE_OPENDXP_*"))
    if not results:
        results.append(Result(OK, "security.yaml", "no legacy auth flags / roles"))
    return results


def check_removed_twig_cache(root: Path) -> Result:
    # The pimcore_cache()/opendxp_cache() Twig FUNCTION (CacheExtension) is removed in
    # OpenDXP. The `opendxpcache` tag only accepts a STRING-LITERAL key, so it is not a
    # drop-in for dynamic-key caching -> must be handled manually.
    rx = re.compile(r"\b(?:pimcore|opendxp)_cache\s*\(")
    hits: list[str] = []
    for sub in ("templates", "src"):
        base = root / sub
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.suffix in (".twig", ".php") and rx.search(read_text(path)):
                hits.append(path.relative_to(root).as_posix())
    if hits:
        return Result(WARN, "twig cache function",
                      "pimcore_cache()/opendxp_cache() removed in OpenDXP "
                      "(use the `opendxpcache` tag with a static key, or drop caching): "
                      + ", ".join(sorted(hits)))
    return Result(OK, "twig cache function", "no pimcore_cache()/opendxp_cache() usage")


def check_carbon_formatlocalized(root: Path) -> Result:
    # Carbon::formatLocalized() (strftime-style) was removed in Carbon 3 (pulled in via
    # Symfony 7 / OpenDXP). Replace with ->locale(...)->translatedFormat('D, d.m.Y ...').
    hits = tree_grep(root / "src", r"->\s*formatLocalized\s*\(", (".php",))
    if hits:
        rels = [Path(h).relative_to(root).as_posix() for h in hits]
        return Result(WARN, "carbon formatLocalized",
                      "removed in Carbon 3 - use ->locale(...)->translatedFormat(...): "
                      + ", ".join(rels))
    return Result(OK, "carbon formatLocalized", "no formatLocalized() usage")


def check_templating(root: Path) -> Result:
    hits = tree_grep(root / "src", r"Symfony\\Component\\Templating", (".php",))
    if hits:
        rels = [Path(h).relative_to(root).as_posix() for h in hits]
        return Result(WARN, "symfony/templating",
                      "removed in OpenDXP - refactor: " + ", ".join(rels))
    return Result(OK, "symfony/templating", "no symfony/templating usage")


def check_bundle_classes(root: Path) -> list[Result]:
    results: list[Result] = []
    for rel in ("config/bundles.php", "src/Kernel.php", "src/App.php"):
        path = root / rel
        if not path.is_file():
            continue
        # Only flag real identifiers, not copyright headers like "Pimcore GmbH".
        if re.search(r"Pimcore\\|Pimcore\w*Bundle|PimcoreKernel|AbstractPimcoreBundle",
                     read_text(path)):
            results.append(Result(WARN, f"bundle classes {rel}",
                                  "contains 'Pimcore...' identifiers (e.g. PimcoreXxxBundle, "
                                  "PimcoreKernel, AbstractPimcoreBundle)"))
        else:
            results.append(Result(OK, f"bundle classes {rel}", "no Pimcore identifiers"))
    return results


def run(root: Path, min_php: tuple[int, int]) -> int:
    results: list[Result] = []
    results.extend(check_project_layout(root))
    results.append(check_php_version(min_php))
    results.extend(check_composer(root))
    results.extend(check_bootstrap(root))
    results.append(check_routes(root))
    results.extend(check_security(root))
    results.append(check_templating(root))
    results.append(check_removed_twig_cache(root))
    results.append(check_carbon_formatlocalized(root))
    results.extend(check_bundle_classes(root))

    print(f"OpenDXP preflight for {root}\n")
    for res in results:
        line = f"{LABEL[res.level]} {res.title}"
        if res.detail:
            line += f": {res.detail}"
        print(line)

    fails = sum(1 for r in results if r.level == FAIL)
    warns = sum(1 for r in results if r.level == WARN)
    print(f"\nSummary: {fails} FAIL, {warns} WARN, "
          f"{sum(1 for r in results if r.level == OK)} OK, "
          f"{sum(1 for r in results if r.level == SKIP)} SKIP")
    if fails:
        print("Resolve FAIL items before running `composer update`.")
    return 1 if fails else 0


def parse_min_php(value: str) -> tuple[int, int]:
    match = re.match(r"(\d+)\.(\d+)", value)
    if not match:
        raise argparse.ArgumentTypeError(f"invalid --min-php: {value!r} (expected e.g. 8.3)")
    return (int(match.group(1)), int(match.group(2)))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only preflight checks for Pimcore -> OpenDXP migrations.",
    )
    parser.add_argument("project", type=Path, help="Project root (e.g. ./pimcore)")
    parser.add_argument("--min-php", type=parse_min_php, default=(8, 3),
                        help="Minimum required PHP version (default: 8.3 for OpenDXP 1.3)")
    args = parser.parse_args()
    if not args.project.is_dir():
        print(f"Project directory not found: {args.project}", file=sys.stderr)
        return 2
    return run(args.project.resolve(), args.min_php)


if __name__ == "__main__":
    raise SystemExit(main())

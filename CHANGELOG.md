# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/). Versions: [SemVer](https://semver.org/).

## [Unreleased]

## [0.9.0] - 2026-06-17

Initial public release.

### Added

- `opendxp_preflight.py` — read-only checks before migration (environment and known
  pitfalls).
- `opendxp_migrate.py` — text replacements for templates, CSS, PHP/YAML and
  bootstrap files (`audit` / `rename`).
- `opendxp_migrate_definitions.py` — replacements for classes, `var/config/`,
  `src/Resources/` and `config/`, plus directory renames (`audit` / `patch`).
- `opendxp_migrate_db.py` — SQL emitter for `settings_store` and optional
  `migration_versions` cleanup.
- Configurable rule sets in `config/default.yaml` and `config/definitions.yaml`.
- English `README.md` and German `README.de.md` with a language switcher.

[0.9.0]: https://github.com/sylphen-gmbh/opendxp-migration-toolkit/releases/tag/v0.9.0

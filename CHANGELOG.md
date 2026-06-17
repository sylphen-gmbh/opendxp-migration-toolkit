# Changelog

All notable changes to this project are documented here. The format is loosely
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- English `README.md` and German `README.de.md` with a language switcher.
- `LICENSE` file (MIT).
- `CONTRIBUTING.md` with development and PR guidelines.
- GitHub Actions CI: byte-compile + CLI smoke tests on Python 3.9–3.12.

## [0.1.0]

### Added

- `opendxp_preflight.py` — read-only environment and known-pitfall checks.
- `opendxp_migrate.py` — text replacements for templates, CSS, PHP/YAML and
  bootstrap files (`audit` / `rename`).
- `opendxp_migrate_definitions.py` — class, `var/config/`, `src/Resources/` and
  `config/` replacements plus directory renames (`audit` / `patch`).
- `opendxp_migrate_db.py` — SQL emitter for `settings_store` and optional
  `migration_versions` cleanup.
- Configurable rule sets in `config/default.yaml` and `config/definitions.yaml`.

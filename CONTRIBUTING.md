# Contributing

Thanks for your interest in improving the OpenDXP Migration Toolkit! This is a
small, dependency-light helper toolkit — contributions that keep it simple and
reviewable are very welcome.

## Ground rules

- **Keep it standard-library-first.** The scripts must run with plain Python 3.9+
  without third-party packages. `PyYAML` is the only optional dependency and is
  used solely when a custom `--config` is passed.
- **No implicit changes.** Every script defaults to a read-only/dry-run mode.
  Destructive behavior must be opt-in (`--apply`, `--with-migration-cleanup`, …).
- **Rules over code.** Prefer adding/adjusting replacement rules in
  `config/default.yaml` / `config/definitions.yaml` over hard-coding logic.

## Development setup

```bash
git clone https://github.com/sylphen/opendxp-migration-toolkit.git
cd opendxp-migration-toolkit
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # only needed for custom --config
```

## Before opening a pull request

1. Make sure every script still byte-compiles:

   ```bash
   python3 -m compileall -q .
   ```

2. Run the CLIs against a throwaway directory to confirm they don't crash:

   ```bash
   mkdir -p /tmp/fixture/pimcore
   python3 opendxp_preflight.py /tmp/fixture/pimcore || true
   python3 opendxp_migrate.py audit /tmp/fixture/pimcore
   python3 opendxp_migrate_definitions.py audit /tmp/fixture/pimcore
   python3 opendxp_migrate_db.py emit-sql > /dev/null
   ```

3. If you change behavior, update both `README.md` (English) **and**
   `README.de.md` (German), plus `CHANGELOG.md`.

## Commit messages

Short, imperative summaries (e.g. `add bootstrap rule for bin/console`). Group
related changes into a single commit where it makes sense.

## Reporting bugs

Open an issue with the command you ran, the expected vs. actual behavior, your
Python version, and (if relevant) a minimal example of the file that was/was not
matched.

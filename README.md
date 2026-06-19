# OpenDXP Migration Toolkit

> 🇬🇧 You are reading the English version · 🇩🇪 Deutsche Version: [`README.de.md`](README.de.md)

Reusable helper toolkit for Pimcore v11 → OpenDXP v1 migrations.

It is **not** a full migrator. Instead it automates the recurring, easily
verifiable renames (`Pimcore` → `OpenDxp`, `pimcore_*` → `opendxp_*`, …) and uses a
preflight check to point out the things that have to be decided manually.

## Scripts

| Script | Purpose | Config |
|---|---|---|
| `opendxp_preflight.py` | Read-only checks before the migration (environment, project layout, known pitfalls) | – |
| `opendxp_migrate_root.py` | Optional parent-repo app folder rename (`pimcore/` → `opendxp/`) and path patches | optional via `--config` (`config/root.yaml`) |
| `opendxp_migrate.py` | Text replacements in templates, CSS, PHP/YAML, bootstrap files | `config/default.yaml` |
| `opendxp_migrate_definitions.py` | Classes, `var/config/`, `src/Resources/`, `config/` | `config/definitions.yaml` |
| `opendxp_migrate_db.py` | SQL emitter for DB leftovers (`settings_store`, optional `migration_versions`) | – |

## Integration

As a Git submodule (recommended) or a standalone clone:

```bash
git submodule add git@github.com:sylphen-gmbh/opendxp-migration-toolkit.git tools/opendxp-migration-toolkit
git submodule update --init --recursive
```

## Requirements

- Python 3.9+
- `PyYAML` only if you pass your own `--config` (without `--config` the built-in
  defaults are used):

```bash
pip install pyyaml
```

## Running in a throwaway container (no host install)

If you do not want to install Python on the host, the toolkit runs in a
short-lived container. The repo is only mounted, the container is discarded via
`--rm` — nothing is left on the host. Run from the repo root (where `tools/` and
the app folder live):

```bash
# Read-only (Python standard library only, no PyYAML needed)
docker run --rm -v "$PWD":/work -w /work python:3.12-alpine \
  python3 tools/opendxp-migration-toolkit/opendxp_preflight.py ./pimcore

docker run --rm -v "$PWD":/work -w /work python:3.12-alpine \
  python3 tools/opendxp-migration-toolkit/opendxp_migrate.py audit ./pimcore
```

Dry-run/apply with your own `--config` needs `PyYAML`, installed inside the
container only:

```bash
docker run --rm -v "$PWD":/work -w /work python:3.12-alpine sh -c '
  pip install --quiet pyyaml &&
  python3 tools/opendxp-migration-toolkit/opendxp_migrate.py rename ./pimcore \
    --config tools/opendxp-migration-toolkit/config/default.yaml --dry-run'
```

The preflight's PHP version check shows `[SKIP]` in a pure Python container
(no `php` available); check PHP separately, e.g. `docker compose exec php php -v`.

## Workflow

Recommended order in the target project (typically the app folder, e.g.
`./pimcore`). Each step supports `audit`/`--dry-run` first, then `--apply`.

### 0. Preflight (before `composer update`)

Reports the blockers the rename/patch scripts deliberately do not cover: PHP
version, composer packages (remaining `pimcore/*`, Symfony 6.x), bootstrap files,
`type: annotation`, `enable_authenticator_manager`, `ROLE_PIMCORE_*`,
`symfony/templating`, bundle classes, removed APIs (`pimcore_cache()`,
`formatLocalized()`), and whether you passed the **app directory** (e.g. `./pimcore`)
rather than the repository root.

```bash
python3 tools/opendxp-migration-toolkit/opendxp_preflight.py ./pimcore
```

Exits `1` as soon as a `FAIL` occurs (CI-friendly), otherwise `0`. Minimum PHP
version via `--min-php` (default `8.3`).

#### Project layout (app path vs. repository root)

Before PHP/composer checks, preflight validates **which directory you passed** and
whether a future **`pimcore/` → `opendxp/` folder rename** would affect files
outside the app tree. These findings are **WARN** only — they never fail the run.

| Check | Level | When | Meaning |
|---|---|---|---|
| `project root` | WARN | You passed the **repository root** (e.g. `.`) and a `./pimcore/` or `./opendxp/` child looks like the app | Pass `./pimcore` (or `./opendxp`) instead — the migrate scripts expect the app directory |
| `project root` | OK | Path contains `composer.json` and `bin/console` (or `public/index.php`) | Correct app directory |
| `app folder name` | WARN | App folder is still named `pimcore/` | **Optional** — OpenDXP does not require renaming to `opendxp/`. Keep using `./pimcore` for all toolkit commands until you decide otherwise |
| `app folder name` | OK | Folder is `opendxp/` or another custom name | — |
| `parent path references` | WARN | Files **outside** the app (e.g. `docker-compose.yaml`, `.gitmodules`, `deployment/*`) contain the string `pimcore/` | Use `opendxp_migrate_root.py` from the **repository root** to audit or apply a rename (see [Optional: app root rename](#optional-app-root-rename-parent-repository)) |

Example — wrong path (repository root):

```bash
python3 tools/opendxp-migration-toolkit/opendxp_preflight.py .
# [WARN] project root: not an app directory — pass ./pimcore ...
```

Example — correct path, legacy folder name:

```bash
python3 tools/opendxp-migration-toolkit/opendxp_preflight.py ./pimcore
# [ OK ] project root: valid app directory
# [WARN] app folder name: still `pimcore/` — OpenDXP does not require renaming ...
# [WARN] parent path references: N file(s) outside the app reference `pimcore/` ...
```

### Optional: app root rename (parent repository)

Only if you want to rename `pimcore/` → `opendxp/` at the **repository** level.
OpenDXP does not require this — preflight only **warns**. Run from the repository
root (where `docker-compose.yaml` lives), not from inside the app folder. The app
tree itself is handled by the migrate scripts in the steps below.

```bash
python3 tools/opendxp-migration-toolkit/opendxp_migrate_root.py . audit
python3 tools/opendxp-migration-toolkit/opendxp_migrate_root.py . rename --dry-run
python3 tools/opendxp-migration-toolkit/opendxp_migrate_root.py . rename --apply
```

After `--apply`, pass `./opendxp` (or your `--target-dir`) to preflight and the
migrate scripts. Update submodule paths (e.g. in `.gitmodules`) if needed. Lines
with external Pimcore URLs are skipped for automatic patching — review those
manually (see [Deliberately not automated](#deliberately-not-automated)).

### 1. Templates / CSS / code

```bash
python3 tools/opendxp-migration-toolkit/opendxp_migrate.py audit  ./pimcore
python3 tools/opendxp-migration-toolkit/opendxp_migrate.py rename ./pimcore --dry-run
python3 tools/opendxp-migration-toolkit/opendxp_migrate.py rename ./pimcore --apply
```

### 2. Classes, var/config, src/Resources, config/

```bash
python3 tools/opendxp-migration-toolkit/opendxp_migrate_definitions.py audit ./pimcore
python3 tools/opendxp-migration-toolkit/opendxp_migrate_definitions.py patch ./pimcore --dry-run
python3 tools/opendxp-migration-toolkit/opendxp_migrate_definitions.py patch ./pimcore --apply
```

Then in the project:

```bash
bin/console opendxp:deployment:classes-rebuild -c -v
bin/console opendxp:cache:clear
```

### 3. Database leftovers

The toolkit deliberately ships **without a DB driver**: `opendxp_migrate_db.py`
produces reviewable SQL on stdout that you apply yourself — nothing is changed
implicitly.

```bash
# generate and review
python3 tools/opendxp-migration-toolkit/opendxp_migrate_db.py emit-sql > migrate.sql

# apply (example MariaDB/MySQL in Docker; back up first!)
docker compose exec -T db mysql -upimcore -ppimcore pimcore < migrate.sql
```

| Table | Content | Default |
|---|---|---|
| `settings_store` | `id` `BUNDLE_INSTALLED__Pimcore*` → `*OpenDxp*` | always |
| `settings_store` | `scope` `pimcore` / `pimcore_*` → `opendxp` / `opendxp_*` | always |
| `migration_versions` | delete old Pimcore CoreBundle migration log | only with `--with-migration-cleanup` |

- The SQL runs inside `START TRANSACTION; … COMMIT;` and contains `SELECT`
  counters (before/after) for cross-checking.
- For `migration_versions`, `%` wildcards are used
  (`Pimcore%CoreBundle%Migrations%`) to avoid backslash escaping in MySQL `LIKE`;
  adjust the pattern via `--migration-like`.
- The `migration_versions` cleanup is not required for the admin login. Only use
  it once it is clear how the OpenDXP migrations are baselined (see OpenDXP
  Upgrade Notes).

### 4. Version files (`var/versions/`)

The serialized version snapshots contain class names like
`Pimcore\Model\DataObject\...`. Do **not** patch these with text tools/sed,
because PHP serialization stores byte lengths. Instead use the official OpenDXP
command `app:migrate-version-files` (OpenDXP docs "Version Migration"): `Pimcore`
and `OpenDxp` are both exactly 7 characters, so a
`str_replace('Pimcore\\', 'OpenDxp\\', …)` stays length-correct; binary `.bin`
files are skipped.

Place the command at `src/Command/MigrateVersionFilesCommand.php` and enable the
`App\Command\` block in `config/services.yaml`, then:

```bash
# back up var/versions/, then:
bin/console app:migrate-version-files --dry-run
bin/console app:migrate-version-files
```

## Scan scope

| Script | Paths |
|---|---|
| `opendxp_migrate_root.py` | Parent repo: `docker-compose.yaml`, `.gitmodules`, `README.md`, `deployment/**` (not the app folder or `tools/**`) |
| `opendxp_migrate.py` | `templates/`, `public/static/css/`, `src/`, `config/`, `bin/`, `public/index.php` |
| `opendxp_migrate_definitions.py` | `var/classes/`, `var/config/`, `src/Resources/`, `config/` |

`opendxp_migrate_root.py` scope is configurable via `--config` (see `config/root.yaml`). Excluded by
default for the migrate scripts: `vendor/**`, `var/**` resp. `var/cache/**`,
`node_modules/**`, `src/Migrations/**` (intentional Pimcore references),
generated routes (`**/fos_js_routes.js`) and third-party (`**/ckeditor-plugins/**`).

## Rules

Paths and rules are configurable in `config/default.yaml` and
`config/definitions.yaml`. Rules whose `from`/`to` contain special characters such
as `\` or `:` must be quoted in YAML (e.g. `from: '\\Pimcore::'`).

### CSS classes

| Pimcore | OpenDXP |
|---|---|
| `pimcore_area_*` | `opendxp_area_*` |
| `pimcore_tag_*` | `opendxp_editable_*` |
| `pimcore_wysiwyg` | `opendxp_editable_wysiwyg` |

OpenDXP renders editables as `opendxp_editable_*`, **not** `opendxp_tag_*`.

### Classes / var/config

| Pimcore | OpenDXP | Where |
|---|---|---|
| `Pimcore\Model\` | `OpenDxp\Model\` | `definition_*.php`, field collections, … |
| `Pimcore\Bundle\` | `OpenDxp\Bundle\` | config exports |
| `\Pimcore::` | `\OpenDxp::` | generated `var/classes/DataObject/*` |
| `pimcore_root` | `opendxp_root` | layout root in class definitions |
| `/bundles/pimcoreadmin/` | `/bundles/opendxpadmin/` | class icons |
| `/bundles/pimcore/` | `/bundles/opendxp/` | bundle asset paths |
| `pimcore_icon_*` | `opendxp_icon_*` | admin icon classes (perspectives etc.) |
| `pimcore.layout.*` | `opendxp.layout.*` | admin layout references, portal dashboards (`.psf`) |
| `pimcore.document/object` | `opendxp.document/object` | editmode JS in `src/Resources` |
| `config/pimcore/` | `config/opendxp/` | folder + path strings |
| `src/Resources/config/pimcore/` | `src/Resources/config/opendxp/` | bundle routing etc. |
| `/bundles/app/pimcore/` | `/bundles/app/opendxp/` | app assets in JS |

**Folder renames** (`rename`/`patch --apply` step):
`src/Resources/config/pimcore/` → `opendxp/`, `config/pimcore/` → `config/opendxp/`,
`src/Resources/public/pimcore/` → `opendxp/`.

### Rule groups (excerpt)

| Group | Effect | Scope |
|---|---|---|
| `twig` | `Pimcore\ → OpenDxp\`, `pimcore_ → opendxp_` | `**/*.twig` |
| `php` | `Pimcore\ → OpenDxp\`, `PIMCORE_ → OPENDXP_` | `**/*.php` |
| `yaml` | `Pimcore\`, `@Pimcore`, `pimcore.`, `pimcore:`, `pimcore_` | `**/*.yaml`, `**/*.yml` |
| `bundle-classes` | class name suffixes (`PimcoreXxxBundle`, `PimcoreKernel`) | `bundles.php`, `Kernel.php`, `App.php` |
| `bootstrap` | `Pimcore\`, `PIMCORE_` | `bin/console`, `public/index.php` |

### Bootstrap files (`bin/console`, `public/index.php`)

`public/index.php` is covered by the `php` group. `bin/console` has **no** `.php`
extension and is therefore not matched by `**/*.php` — that is what the
`bootstrap` group is for. The patch is a pure rename and covers the critical
references (`OpenDxp\Bootstrap`, `OpenDxp\Console\Application`, `OPENDXP_CONSOLE`),
but may leave legacy bits behind (e.g. a `Symfony\Component\Debug\Debug` import).
Since these files are rarely customized per project, adopting the OpenDXP skeleton
files is usually cleaner when in doubt.

## Manual steps

These points require manual work or a case-by-case decision; the preflight reports
most of them:

- [ ] `composer.json`: `pimcore/pimcore` → `open-dxp/opendxp`, map bundles to
      `open-dxp/*` or remove them, Symfony to `^7.4`, `autoload.psr-4` DataObject
      namespace.
- [ ] `config/packages/security.yaml`: remove `enable_authenticator_manager`,
      `ROLE_PIMCORE_*` → `ROLE_OPENDXP_*`, adjust provider/firewall names.
- [ ] Routing: `type: annotation` → `type: attribute` (Symfony 7).
- [ ] Refactor `symfony/templating` subclasses (e.g. custom helpers) — removed in
      OpenDXP.
- [ ] `src/Kernel.php`: no duplicate registration of the admin bundle (OpenDXP
      core registers it itself).
- [ ] Twig cache: the `pimcore_cache()`/`opendxp_cache()` **function** is removed.
      The `opendxpcache` **tag** only accepts a **string literal key** (no dynamic
      key, no `.start()/.end()` API). For dynamic keys, remove the caching (content
      still renders correctly) or cache at the controller level.
- [ ] Carbon `formatLocalized()` (strftime style) is removed in Carbon 3. Replace
      with `->locale('de')->translatedFormat('D, d.m.Y …')` (PHP `date()` tokens;
      escape literal letters with `\`, e.g. `\U\h\r`).
- [ ] Password BC: set `opendxp.security.password.salt: 'pimcore'` so existing
      logins keep working.
- [ ] `editmode.css`: check for remaining `pimcore_*` editor classes.
- [ ] `config/packages/test/config.yaml`: `PIMCORE_TEST_DB_DSN`.
- [ ] Content strings containing "Pimcore" (e.g. `robots.php`, `web2print.php`,
      external URLs).

## Deliberately not automated

- Generated assets/routes (`fos_js_routes.js`)
- Project-specific classes (e.g. `peditmode`)
- Database/service **names** still containing `pimcore` (e.g. MySQL user/database in
  `docker-compose.yaml`) — path strings are patched by `opendxp_migrate_root.py`,
  credentials and DSNs need a manual decision
- External Pimcore URLs and content strings with "Pimcore" in the name (manual review)

## Exit codes

| Command | Meaning |
|---|---|
| `preflight` | `0` = no `FAIL`, `1` = at least one `FAIL`, `2` = wrong invocation |
| `migrate_root audit` | `0` = clean, `1` = findings, `2` = wrong invocation |
| `migrate_root rename` | `0` = completed, `1` = layout/validation error, `2` = wrong invocation |
| `audit` | `0` = clean, `1` = findings |
| `rename` / `patch` | `0` = completed |
| `migrate_db emit-sql` | `0` = SQL emitted |

## Reference

[OpenDXP Upgrade Notes](https://docs.opendxp.io/docs/core-framework/Installation_and_Upgrade/Upgrade_Notes/)

## License

MIT — see [`LICENSE`](LICENSE).

# OpenDXP Migration Toolkit

Kleines, wiederverwendbares Hilfswerkzeug für Pimcore v11 → OpenDXP v1 Migrationen.

Zwei Skripte:

| Skript | Ziel |
|---|---|
| `opendxp_migrate.py` | Templates, CSS, PHP/YAML in `src/` & `config/` |
| `opendxp_migrate_definitions.py` | Klassen, `var/config/`, `src/Resources/`, `config/` |

Kein Voll-Migrator — bewusst nur für wiederkehrende, gut prüfbare Muster.

## Einbindung in ein Projekt

### Option A: Git Submodule (empfohlen)

```bash
git submodule add git@gitlab.example.com:your-org/opendxp-migration-toolkit.git tools/opendxp-migration-toolkit
git submodule update --init --recursive
```

### Option B: Separates Clone

```bash
git clone git@gitlab.example.com:your-org/opendxp-migration-toolkit.git ~/tools/opendxp-migration-toolkit
```

## Voraussetzungen

- Python 3.9+
- Optional: `PyYAML` nur wenn eine eigene `--config` genutzt wird

```bash
pip install pyyaml
```

Ohne `--config` arbeitet das Skript mit eingebauten Defaults.

## Nutzung

Im Zielprojekt (typisch der Symfony/OpenDXP-App-Ordner, z. B. `./pimcore`):

### 1) Templates / CSS / Code

```bash
python3 tools/opendxp-migration-toolkit/opendxp_migrate.py audit ./pimcore
python3 tools/opendxp-migration-toolkit/opendxp_migrate.py rename ./pimcore --dry-run
python3 tools/opendxp-migration-toolkit/opendxp_migrate.py rename ./pimcore --apply
```

Config: `config/default.yaml`

### 2) Klassen, var/config, src/Resources, config/

```bash
python3 tools/opendxp-migration-toolkit/opendxp_migrate_definitions.py audit ./pimcore
python3 tools/opendxp-migration-toolkit/opendxp_migrate_definitions.py patch ./pimcore --dry-run
python3 tools/opendxp-migration-toolkit/opendxp_migrate_definitions.py patch ./pimcore --apply
```

Config: `config/definitions.yaml`

Danach im Projekt:

```bash
bin/console opendxp:deployment:classes-rebuild -c -v
bin/console opendxp:cache:clear
```

## Was standardmäßig gescannt wird

**Skript 1:** `templates/`, `public/static/css/`, `src/`, `config/`

**Skript 2:** `var/classes/`, `var/config/`, `src/Resources/`, `config/`

Ausgeschlossen u. a.:
- `vendor/**`, `var/cache/**` (Skript 2)
- `var/**` (Skript 1)
- `src/Migrations/**` (bewusste Pimcore-Referenzen in Migrations)
- `**/fos_js_routes.js` (generiert)
- `**/ckeditor-plugins/**` (Third-Party)

Pfade und Regeln sind in `config/default.yaml` bzw. `config/definitions.yaml` anpassbar.

## Wichtige Rename-Regeln (CSS)

| Alt (Pimcore) | Neu (OpenDXP) |
|---|---|
| `pimcore_area_*` | `opendxp_area_*` |
| `pimcore_tag_*` | `opendxp_editable_*` |
| `pimcore_wysiwyg` | `opendxp_editable_wysiwyg` |

Hinweis: OpenDXP rendert Editables als `opendxp_editable_*`, **nicht** `opendxp_tag_*`.

## Wichtige Patch-Regeln (Klassen / var/config)

| Alt (Pimcore) | Neu (OpenDXP) | Wo |
|---|---|---|
| `Pimcore\Model\` | `OpenDxp\Model\` | `definition_*.php`, Fieldcollections, … |
| `Pimcore\Bundle\` | `OpenDxp\Bundle\` | Config-Exporte |
| `\Pimcore::` | `\OpenDxp::` | generierte `var/classes/DataObject/*` |
| `pimcore_root` | `opendxp_root` | Layout-Root in Klassendefinitionen |
| `/bundles/pimcoreadmin/` | `/bundles/opendxpadmin/` | Klassen-Icons |
| `/bundles/pimcore/` | `/bundles/opendxp/` | Bundle-Asset-Pfade |
| `pimcore_icon_*` | `opendxp_icon_*` | Admin-Icon-Klassen (Perspectives etc.) |
| `pimcore.layout.portlets.*` | `opendxp.layout.portlets.*` | Portal-Dashboards (`.psf`) |
| `pimcore.layout.*` | `opendxp.layout.*` | übrige Admin-Layout-Referenzen |
| `pimcore.document/object` | `opendxp.document/object` | Editmode-JS in `src/Resources` |
| `config/pimcore/` | `config/opendxp/` | Ordner + Pfad-Strings |
| `src/Resources/config/pimcore/` | `src/Resources/config/opendxp/` | Bundle-Routing etc. |
| `/bundles/app/pimcore/` | `/bundles/app/opendxp/` | App-Assets in JS |

**Ordner-Umbenennung** (beide Skripte, Schritt `rename`/`patch --apply`):

- `src/Resources/config/pimcore/` → `opendxp/`
- `config/pimcore/` → `config/opendxp/`
- `src/Resources/public/pimcore/` → `opendxp/`

### Was sonst noch relevant ist (nicht in diesem Skript)

- **Settings Store / DB**: `pimcore_*`-Scopes → `opendxp_*` (eigene Doctrine-Migration)
- **Commands / Messenger**: `pimcore:` → `opendxp:` (oft schon via Composer/Skeleton)
- **Copyright-URLs** (`pimcore.com`, `pimcore.org`) — werden nicht gepatcht
- **Nutzer-Inhalte**: Pfade wie `/Pimcore-Schulung` in `robots.php`

## Bewusst nicht automatisiert

- Datenbank / Settings Store (eigene Doctrine-Migration)
- Generierte Assets/Routes (`fos_js_routes.js`)
- Projekteigene Klassen (z. B. `peditmode`)
- Ordnername `pimcore/` (nur Struktur, kein Muss)
- Inhalts-Strings mit „Pimcore“ im Namen (robots, externe URLs) — manual review, kein Auto-Patch

Referenz: [OpenDXP Upgrade Notes](https://docs.opendxp.io/docs/core-framework/Installation_and_Upgrade/Upgrade_Notes/)

## Exit-Codes

- `audit`: `0` = sauber, `1` = Funde
- `rename`: `0` = durchgelaufen

## Lizenz

MIT

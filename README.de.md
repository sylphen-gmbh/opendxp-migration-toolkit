# OpenDXP Migration Toolkit

> 🇬🇧 English version: [`README.md`](README.md) · 🇩🇪 Du liest die deutsche Version.

Wiederverwendbares Hilfswerkzeug für Pimcore v11 → OpenDXP v1 Migrationen.

Es ist **kein** Voll-Migrator, sondern automatisiert die wiederkehrenden, gut
prüfbaren Umbenennungen (`Pimcore` → `OpenDxp`, `pimcore_*` → `opendxp_*`, …) und
weist über einen Preflight auf die Dinge hin, die manuell entschieden werden müssen.

## Skripte

| Skript | Aufgabe | Config |
|---|---|---|
| `opendxp_preflight.py` | Read-only-Checks vor der Migration (Umgebung, Projekt-Layout, bekannte Stolpersteine) | – |
| `opendxp_migrate_root.py` | Optionale App-Root-Umbenennung im Parent-Repo (`pimcore/` → `opendxp/`) und Pfad-Patches | optional via `--config` (`config/root.yaml`) |
| `opendxp_migrate.py` | Text-Ersetzungen in Templates, CSS, PHP/YAML, Bootstrap-Dateien | `config/default.yaml` |
| `opendxp_migrate_definitions.py` | Klassen, `var/config/`, `src/Resources/`, `config/` | `config/definitions.yaml` |
| `opendxp_migrate_db.py` | SQL-Emitter für DB-Reste (`settings_store`, optional `migration_versions`) | – |

## Einbindung

Als Git-Submodule (empfohlen) oder separates Clone:

```bash
git submodule add git@github.com:sylphen-gmbh/opendxp-migration-toolkit.git tools/opendxp-migration-toolkit
git submodule update --init --recursive
```

## Voraussetzungen

- Python 3.9+
- `PyYAML` nur, wenn eine eigene `--config` genutzt wird (ohne `--config` greifen die
  eingebauten Defaults):

```bash
pip install pyyaml
```

## Ausführen im Wegwerf-Container (ohne Host-Installation)

Soll auf dem Host kein Python installiert werden, läuft das Toolkit in einem
kurzlebigen Container. Das Repo wird nur eingehängt, der Container via `--rm`
verworfen — es bleibt nichts auf dem Host. Aufruf aus dem Repo-Root (dort, wo
`tools/` und der App-Ordner liegen):

```bash
# Read-only (nur Python-Standardbibliothek, kein PyYAML nötig)
docker run --rm -v "$PWD":/work -w /work python:3.12-alpine \
  python3 tools/opendxp-migration-toolkit/opendxp_preflight.py ./pimcore

docker run --rm -v "$PWD":/work -w /work python:3.12-alpine \
  python3 tools/opendxp-migration-toolkit/opendxp_migrate.py audit ./pimcore
```

Dry-Run/Apply mit eigener `--config` benötigt `PyYAML`, das nur im Container
installiert wird:

```bash
docker run --rm -v "$PWD":/work -w /work python:3.12-alpine sh -c '
  pip install --quiet pyyaml &&
  python3 tools/opendxp-migration-toolkit/opendxp_migrate.py rename ./pimcore \
    --config tools/opendxp-migration-toolkit/config/default.yaml --dry-run'
```

Der PHP-Versions-Check des Preflights zeigt im reinen Python-Container `[SKIP]`
(kein `php` vorhanden); PHP separat prüfen, z. B. `docker compose exec php php -v`.

## Ablauf

Empfohlene Reihenfolge im Zielprojekt (typisch der App-Ordner, z. B. `./pimcore`).
Jeder Schritt unterstützt zuerst `audit`/`--dry-run`, dann `--apply`.

### 0. Preflight (vor `composer update`)

Meldet die Blocker, die die Rename-/Patch-Skripte bewusst nicht abdecken: PHP-Version,
composer-Pakete (verbliebene `pimcore/*`, Symfony 6.x), Bootstrap-Dateien,
`type: annotation`, `enable_authenticator_manager`, `ROLE_PIMCORE_*`,
`symfony/templating`, Bundle-Klassen, entfernte APIs (`pimcore_cache()`,
`formatLocalized()`), und ob das **App-Verzeichnis** (z. B. `./pimcore`) übergeben
wurde — nicht das Repository-Root.

```bash
python3 tools/opendxp-migration-toolkit/opendxp_preflight.py ./pimcore
```

Exit `1`, sobald ein `FAIL` vorliegt (CI-tauglich), sonst `0`. Mindest-PHP-Version
über `--min-php` (Default `8.3`).

#### Projekt-Layout (App-Pfad vs. Repository-Root)

Vor den PHP-/Composer-Checks prüft der Preflight, **welches Verzeichnis übergeben
wurde** und ob eine spätere **`pimcore/` → `opendxp/`-Ordner-Umbenennung** Dateien
außerhalb des App-Baums betreffen würde. Diese Funde sind nur **WARN** — sie
führen nicht zum Abbruch.

| Check | Level | Wann | Bedeutung |
|---|---|---|---|
| `project root` | WARN | **Repository-Root** übergeben (z. B. `.`) und `./pimcore/` oder `./opendxp/` sieht wie die App aus | Stattdessen `./pimcore` (oder `./opendxp`) übergeben — die Migrate-Skripte erwarten das App-Verzeichnis |
| `project root` | OK | Pfad enthält `composer.json` und `bin/console` (oder `public/index.php`) | Korrektes App-Verzeichnis |
| `app folder name` | WARN | App-Ordner heißt noch `pimcore/` | **Optional** — OpenDXP verlangt keine Umbenennung nach `opendxp/`. Alle Toolkit-Befehle weiter mit `./pimcore` aufrufen, bis ihr euch entscheidet |
| `app folder name` | OK | Ordner heißt `opendxp/` oder individuell | — |
| `parent path references` | WARN | Dateien **außerhalb** der App (z. B. `docker-compose.yaml`, `.gitmodules`, `deployment/*`) enthalten `pimcore/` | `opendxp_migrate_root.py` vom **Repository-Root** aus für Audit/Rename nutzen (siehe [Optional: App-Root-Umbenennung](#optional-app-root-umbenennung-parent-repository)) |

Beispiel — falscher Pfad (Repository-Root):

```bash
python3 tools/opendxp-migration-toolkit/opendxp_preflight.py .
# [WARN] project root: not an app directory — pass ./pimcore ...
```

Beispiel — korrekter Pfad, Legacy-Ordnername:

```bash
python3 tools/opendxp-migration-toolkit/opendxp_preflight.py ./pimcore
# [ OK ] project root: valid app directory
# [WARN] app folder name: still `pimcore/` — OpenDXP does not require renaming ...
# [WARN] parent path references: N file(s) outside the app reference `pimcore/` ...
```

### Optional: App-Root-Umbenennung (Parent-Repository)

Nur wenn ihr `pimcore/` → `opendxp/` auf **Repository-Ebene** umbenennen wollt.
OpenDXP verlangt das nicht — der Preflight **warnt** nur. Vom Repository-Root aus
(dort wo `docker-compose.yaml` liegt) aufrufen, nicht aus dem App-Ordner. Den
App-Baum selbst bearbeiten die Migrate-Skripte in den folgenden Schritten.

```bash
python3 tools/opendxp-migration-toolkit/opendxp_migrate_root.py . audit
python3 tools/opendxp-migration-toolkit/opendxp_migrate_root.py . rename --dry-run
python3 tools/opendxp-migration-toolkit/opendxp_migrate_root.py . rename --apply
```

Nach `--apply` Preflight und Migrate-Skripte mit `./opendxp` (oder eurem
`--target-dir`) aufrufen. Submodule-Pfade (z. B. in `.gitmodules`) ggf. anpassen.
Zeilen mit externen Pimcore-URLs werden beim automatischen Patchen übersprungen —
manuell prüfen (siehe [Bewusst nicht automatisiert](#bewusst-nicht-automatisiert)).

### 1. Templates / CSS / Code

```bash
python3 tools/opendxp-migration-toolkit/opendxp_migrate.py audit  ./pimcore
python3 tools/opendxp-migration-toolkit/opendxp_migrate.py rename ./pimcore --dry-run
python3 tools/opendxp-migration-toolkit/opendxp_migrate.py rename ./pimcore --apply
```

### 2. Klassen, var/config, src/Resources, config/

```bash
python3 tools/opendxp-migration-toolkit/opendxp_migrate_definitions.py audit ./pimcore
python3 tools/opendxp-migration-toolkit/opendxp_migrate_definitions.py patch ./pimcore --dry-run
python3 tools/opendxp-migration-toolkit/opendxp_migrate_definitions.py patch ./pimcore --apply
```

Danach im Projekt:

```bash
bin/console opendxp:deployment:classes-rebuild -c -v
bin/console opendxp:cache:clear
```

### 3. Datenbank-Reste

Das Toolkit bleibt bewusst **ohne DB-Treiber**: `opendxp_migrate_db.py` erzeugt
reviewbares SQL auf stdout, das selbst eingespielt wird — nichts wird implizit
geändert.

```bash
# erzeugen und ansehen
python3 tools/opendxp-migration-toolkit/opendxp_migrate_db.py emit-sql > migrate.sql

# einspielen (Beispiel MariaDB/MySQL im Docker; vorher Backup!)
docker compose exec -T db mysql -upimcore -ppimcore pimcore < migrate.sql
```

| Tabelle | Inhalt | Standard |
|---|---|---|
| `settings_store` | `id` `BUNDLE_INSTALLED__Pimcore*` → `*OpenDxp*` | immer |
| `settings_store` | `scope` `pimcore` / `pimcore_*` → `opendxp` / `opendxp_*` | immer |
| `migration_versions` | alten Pimcore-CoreBundle-Migrationslog löschen | nur mit `--with-migration-cleanup` |

- Das SQL läuft in `START TRANSACTION; … COMMIT;` und enthält `SELECT`-Zähler
  (vorher/nachher) zum Gegenchecken.
- Für `migration_versions` werden `%`-Wildcards genutzt
  (`Pimcore%CoreBundle%Migrations%`), um Backslash-Escaping in MySQL-`LIKE` zu
  vermeiden; Muster per `--migration-like` anpassbar.
- Der `migration_versions`-Cleanup ist für den Admin-Login nicht nötig. Erst
  einsetzen, wenn klar ist, wie die OpenDXP-Migrationen ge-baselined werden
  (siehe OpenDXP Upgrade Notes).

### 4. Versions-Dateien (`var/versions/`)

Die serialisierten Versions-Snapshots enthalten Klassennamen wie
`Pimcore\Model\DataObject\...`. Diese **nicht** mit Text-Tools/sed patchen, da
PHP-Serialisierung Byte-Längen mitspeichert. Stattdessen das offizielle
OpenDXP-Command `app:migrate-version-files` (OpenDXP-Doku „Version Migration")
nutzen: `Pimcore` und `OpenDxp` sind beide exakt 7 Zeichen, daher bleibt ein
`str_replace('Pimcore\\', 'OpenDxp\\', …)` längen-korrekt; binäre `.bin`-Dateien
werden übersprungen.

Command unter `src/Command/MigrateVersionFilesCommand.php` ablegen und den
`App\Command\`-Block in `config/services.yaml` aktivieren, dann:

```bash
# Backup von var/versions/ anlegen, dann:
bin/console app:migrate-version-files --dry-run
bin/console app:migrate-version-files
```

## Scan-Umfang

| Skript | Pfade |
|---|---|
| `opendxp_migrate_root.py` | Parent-Repo: `docker-compose.yaml`, `.gitmodules`, `README.md`, `deployment/**` (nicht App-Ordner oder `tools/**`) |
| `opendxp_migrate.py` | `templates/`, `public/static/css/`, `src/`, `config/`, `bin/`, `public/index.php` |
| `opendxp_migrate_definitions.py` | `var/classes/`, `var/config/`, `src/Resources/`, `config/` |

Der Scan-Umfang von `opendxp_migrate_root.py` ist per `--config` konfigurierbar (siehe `config/root.yaml`).
Standardmäßig ausgeschlossen für die Migrate-Skripte: `vendor/**`, `var/**` bzw. `var/cache/**`,
`node_modules/**`, `src/Migrations/**` (bewusste Pimcore-Referenzen),
generierte Routes (`**/fos_js_routes.js`) und Third-Party (`**/ckeditor-plugins/**`).

## Regeln

Pfade und Regeln sind in `config/default.yaml` und `config/definitions.yaml`
anpassbar. Regeln, deren `from`/`to` Sonderzeichen wie `\` oder `:` enthalten,
müssen in YAML gequotet werden (z. B. `from: '\\Pimcore::'`).

### CSS-Klassen

| Pimcore | OpenDXP |
|---|---|
| `pimcore_area_*` | `opendxp_area_*` |
| `pimcore_tag_*` | `opendxp_editable_*` |
| `pimcore_wysiwyg` | `opendxp_editable_wysiwyg` |

OpenDXP rendert Editables als `opendxp_editable_*`, **nicht** `opendxp_tag_*`.

### Klassen / var/config

| Pimcore | OpenDXP | Wo |
|---|---|---|
| `Pimcore\Model\` | `OpenDxp\Model\` | `definition_*.php`, Fieldcollections, … |
| `Pimcore\Bundle\` | `OpenDxp\Bundle\` | Config-Exporte |
| `\Pimcore::` | `\OpenDxp::` | generierte `var/classes/DataObject/*` |
| `pimcore_root` | `opendxp_root` | Layout-Root in Klassendefinitionen |
| `/bundles/pimcoreadmin/` | `/bundles/opendxpadmin/` | Klassen-Icons |
| `/bundles/pimcore/` | `/bundles/opendxp/` | Bundle-Asset-Pfade |
| `pimcore_icon_*` | `opendxp_icon_*` | Admin-Icon-Klassen (Perspectives etc.) |
| `pimcore.layout.*` | `opendxp.layout.*` | Admin-Layout-Referenzen, Portal-Dashboards (`.psf`) |
| `pimcore.document/object` | `opendxp.document/object` | Editmode-JS in `src/Resources` |
| `config/pimcore/` | `config/opendxp/` | Ordner + Pfad-Strings |
| `src/Resources/config/pimcore/` | `src/Resources/config/opendxp/` | Bundle-Routing etc. |
| `/bundles/app/pimcore/` | `/bundles/app/opendxp/` | App-Assets in JS |

**Ordner-Umbenennungen** (Schritt `rename`/`patch --apply`):
`src/Resources/config/pimcore/` → `opendxp/`, `config/pimcore/` → `config/opendxp/`,
`src/Resources/public/pimcore/` → `opendxp/`.

### Regelgruppen (Auszug)

| Gruppe | Wirkung | Geltungsbereich |
|---|---|---|
| `twig` | `Pimcore\ → OpenDxp\`, `pimcore_ → opendxp_` | `**/*.twig` |
| `php` | `Pimcore\ → OpenDxp\`, `PIMCORE_ → OPENDXP_` | `**/*.php` |
| `yaml` | `Pimcore\`, `@Pimcore`, `pimcore.`, `pimcore:`, `pimcore_` | `**/*.yaml`, `**/*.yml` |
| `bundle-classes` | Klassennamen-Suffixe (`PimcoreXxxBundle`, `PimcoreKernel`) | `bundles.php`, `Kernel.php`, `App.php` |
| `bootstrap` | `Pimcore\`, `PIMCORE_` | `bin/console`, `public/index.php` |

### Bootstrap-Dateien (`bin/console`, `public/index.php`)

`public/index.php` wird von der `php`-Gruppe erfasst. `bin/console` hat **keine**
`.php`-Endung und wird daher nicht von `**/*.php` getroffen — dafür existiert die
Gruppe `bootstrap`. Der Patch ist ein reiner Rename und deckt die kritischen
Referenzen ab (`OpenDxp\Bootstrap`, `OpenDxp\Console\Application`, `OPENDXP_CONSOLE`),
kann aber Altlasten stehen lassen (z. B. einen `Symfony\Component\Debug\Debug`-Import).
Da diese Dateien selten projektspezifisch angepasst sind, ist im Zweifel das
Übernehmen der OpenDXP-Skeleton-Dateien sauberer.

## Manuelle Schritte

Diese Punkte erfordern Hand-Arbeit oder eine Einzelfall-Entscheidung; der Preflight
meldet die meisten davon:

- [ ] `composer.json`: `pimcore/pimcore` → `open-dxp/opendxp`, Bundles auf `open-dxp/*`
      mappen oder entfernen, Symfony auf `^7.4`, `autoload.psr-4` DataObject-Namespace.
- [ ] `config/packages/security.yaml`: `enable_authenticator_manager` entfernen,
      `ROLE_PIMCORE_*` → `ROLE_OPENDXP_*`, Provider-/Firewall-Namen anpassen.
- [ ] Routing: `type: annotation` → `type: attribute` (Symfony 7).
- [ ] `symfony/templating`-Erben (z. B. eigene Helper) refaktorieren — in OpenDXP entfernt.
- [ ] `src/Kernel.php`: keine doppelte Registrierung des Admin-Bundles
      (OpenDXP-Core registriert es selbst).
- [ ] Twig-Cache: die `pimcore_cache()`/`opendxp_cache()`-**Funktion** ist entfernt.
      Der `opendxpcache`-**Tag** akzeptiert nur einen **String-Literal-Key**
      (kein dynamischer Key, kein `.start()/.end()`-API). Bei dynamischen Keys das
      Caching entfernen (Inhalt rendert weiterhin korrekt) oder auf Controller-Ebene cachen.
- [ ] Carbon `formatLocalized()` (strftime-Stil) ist in Carbon 3 entfernt. Ersetzen
      durch `->locale('de')->translatedFormat('D, d.m.Y …')` (PHP-`date()`-Tokens;
      literale Buchstaben mit `\` escapen, z. B. `\U\h\r`).
- [ ] Passwort-BC: `opendxp.security.password.salt: 'pimcore'` setzen, damit bestehende
      Logins weiter funktionieren.
- [ ] `editmode.css`: verbliebene `pimcore_*`-Editor-Klassen prüfen.
- [ ] `config/packages/test/config.yaml`: `PIMCORE_TEST_DB_DSN`.
- [ ] Inhalts-Strings mit „Pimcore" (z. B. `robots.php`, `web2print.php`, externe URLs).

## Bewusst nicht automatisiert

- Generierte Assets/Routes (`fos_js_routes.js`)
- Projekteigene Klassen (z. B. `peditmode`)
- Datenbank-/Service-**Namen**, die noch `pimcore` enthalten (z. B. MySQL-User/DB in
  `docker-compose.yaml`) — Pfad-Strings patcht `opendxp_migrate_root.py`,
  Credentials und DSNs manuell entscheiden
- Externe Pimcore-URLs und Inhalts-Strings mit „Pimcore" im Namen (manuelle Sichtung)

## Exit-Codes

| Befehl | Bedeutung |
|---|---|
| `preflight` | `0` = kein `FAIL`, `1` = mindestens ein `FAIL`, `2` = falscher Aufruf |
| `migrate_root audit` | `0` = sauber, `1` = Funde, `2` = falscher Aufruf |
| `migrate_root rename` | `0` = durchgelaufen, `1` = Layout-/Validierungsfehler, `2` = falscher Aufruf |
| `audit` | `0` = sauber, `1` = Funde |
| `rename` / `patch` | `0` = durchgelaufen |
| `migrate_db emit-sql` | `0` = SQL ausgegeben |

## Referenz

[OpenDXP Upgrade Notes](https://docs.opendxp.io/docs/core-framework/Installation_and_Upgrade/Upgrade_Notes/)

## Lizenz

MIT — siehe [`LICENSE`](LICENSE).

# Publishing & branching workflow (maintainers)

This repo lives in two places:

- **GitLab** (`gitlab.sylphen.com`, remote `origin`) — internal working repo. May
  contain private branches that are never published.
- **GitHub** (`sylphen-gmbh/opendxp-migration-toolkit`, remote `github`) — public
  repo. **`main` is owned by GitHub**: pull requests are merged there, so it must
  never be force-overwritten from GitLab.

Branch names are identical on both sides (`main`). Only selected refs are pushed
to GitHub.

## What goes where

| Ref | Lives on | Pushed to GitHub? |
|---|---|---|
| `main` | GitHub (authoritative) → mirrored back to GitLab | merges happen on GitHub |
| `public/*` | local / GitLab → GitHub | yes (for collaboration / PRs) |
| `internal/*`, `wip/*`, `feature/*`, … | GitLab only | **no** |
| tags (`v*`) | local / GitLab → GitHub | yes (releases) |

Two safety nets enforce this:

- **Push whitelist** — `remote.github.push` only maps `main` and `public/*`, so a
  bare `git push github` cannot leak internal branches.
- **`pre-push` hook** (`.githooks/pre-push`) — rejects any push to GitHub that is
  not `main`, `public/*` or a tag.

## One-time setup per clone

```bash
git remote add github https://github.com/sylphen-gmbh/opendxp-migration-toolkit.git
git config --add remote.github.push refs/heads/main:refs/heads/main
git config --add remote.github.push 'refs/heads/public/*:refs/heads/public/*'
git config core.hooksPath .githooks      # activates the pre-push guard
```

## Daily workflow

### Publish a change for contribution

```bash
git checkout -b public/new-rule
# ... work, commit ...
git push github public/new-rule
```

Open a PR `public/new-rule -> main` on GitHub, collaborate, and **merge with the
GitHub button** (real "Merged" status).

### Bring merged `main` back into GitLab

`main` must always fast-forward from GitHub — never commit to `main` directly.

```bash
git fetch github
git checkout main
git merge --ff-only github/main
git push origin main
```

If `--ff-only` fails, `main` diverged (someone committed to `main` outside of
GitHub) — investigate instead of forcing.

### Releases / tags

Push tags individually; never use `--tags` (which would push all tags):

```bash
git push github v1.2.0
```

### Internal work

Just push to GitLab; it never reaches GitHub:

```bash
git push origin internal/experiment
```

## Accepting external pull requests

External contributors fork on GitHub and open PRs against `main`. Review and
**merge them on GitHub**, then run the "bring `main` back" steps above so GitLab
stays in sync.

## Automated publishing (optional, via GitLab CI)

`.gitlab-ci.yml` contains a `publish-to-github` job that pushes `public/*`
branches and tags to GitHub automatically (never `main`, never `--force`). It
needs a `GITHUB_TOKEN` CI/CD variable (Protected + Masked) with `repo` scope.

## Why not GitLab's built-in push mirror?

The built-in push mirror is one-way and overwrites the target, which would clobber
PRs merged on GitHub. Because we want real GitHub merges, we use selective manual
(or CI) pushes plus a fast-forward pull-back of `main` instead.

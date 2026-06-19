# Publishing (maintainers)

Public collaboration happens on **GitHub** (`sylphen-gmbh/opendxp-migration-toolkit`).
Day-to-day work may live on **internal GitLab** (`origin`).

**`main` is owned by GitHub** — merge pull requests there, then fast-forward GitLab
`main` from `github/main`. GitLab CI never force-pushes `main` to GitHub.

Only `public/*` branches and `v*` tags are published to GitHub (plus manual
`git push github main` when needed). Branches like `internal/*` stay on GitLab.

For the full maintainer runbook (branching both ways, sync, releases, CI/CD,
troubleshooting), see the **GitLab project Wiki** (internal — not on GitHub).

External contributors: [`CONTRIBUTING.md`](CONTRIBUTING.md).

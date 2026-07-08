# Repo Hygiene A Safe Cleanup Plan

## Scope

Repo Hygiene A is a repository hygiene and label-safety task only. It is not a new strategy phase, does not generate new signals, does not rerun strategy searches, does not change candidate results, does not change official promotion gates, and does not approve paper trading.

## Generated/raw artifact folders

The following folders are generated, raw, local, or run-scoped research artifacts and should not be committed going forward:

- `data/raw/`: local raw OHLCV CSV inputs. Raw Databento-derived data may have licensing or redistribution restrictions and should not be public unless explicitly allowed by the data license and project owner.
- `outputs/`: legacy compatibility CSV/JSON outputs from research phases and audits.
- `reports/`: generated markdown reports from phases/audits, except explicitly chosen documentation-style reports.
- `artifacts/`: run-scoped manifests, specs, reports, CSVs, and other generated phase/audit outputs.
- `charts/`: generated images/visualizations.
- `trade_logs/`: generated simulated trade logs.

These files can be large, repetitive, machine-generated, sensitive from a data-licensing perspective, or misleading when separated from the exact code/data revision that produced them.

## Current task cleanup rule

Do not delete, untrack, or rewrite existing data, outputs, reports, artifacts, charts, or trade logs in Repo Hygiene A. `.gitignore` protects future additions but does not remove files that are already tracked in git history.

## Future safe cleanup commands, not executed in this task

After confirming which tracked artifacts should leave the repository, a future cleanup branch can remove them from the git index while leaving local working files in place:

```bash
git rm -r --cached outputs reports artifacts charts trade_logs
git rm -r --cached data/raw
```

Then review with:

```bash
git status --short
git diff --cached --stat
```

Only commit such cleanup after confirming no required source code, tests, tiny fixtures, or hand-authored documentation are included in the removal.

## Large artifact storage options

For large artifacts that must be retained outside normal source control, consider:

- Git LFS for selected binary or large files when versioning inside the repo is truly needed.
- GitHub releases or release assets for reproducible research bundles.
- Private object storage or a private archive for raw/licensed data and large generated outputs.

Raw Databento-derived data needs an explicit license/redistribution review before publication.

## Recommended future repo structure

- Commit source code, tests, scripts, docs, and small deterministic configuration files.
- Commit only tiny synthetic fixtures needed for tests.
- Ignore generated outputs, reports, artifacts, charts, trade logs, caches, virtual environments, and local raw data.
- Archive important generated research bundles separately with a manifest that records code revision, command, input data identity, assumptions, and checksums.
- Keep strategy labels separate from paper-trading approval. Legacy paper/watchlist/review labels are research/review language only unless a separate explicit approval process changes project policy.

## Guardrails

Official promotion gates remain unchanged. Paper trading is not approved. No live trading, broker adapters, order routing, API-key storage, webhooks, automated execution, or LLM-driven trade decisions are added by this plan.

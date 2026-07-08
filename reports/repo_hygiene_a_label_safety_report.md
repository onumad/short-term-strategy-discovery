# Repo Hygiene A + Label Safety A Report

## What changed

- `requirements.txt` was inspected and is already normalized to one dependency per line with the same dependency constraints.
- `.gitignore` now includes explicit generated/local research artifact ignores and Python/cache ignores.
- `README.md` now includes a short repo-hygiene and label-safety note.
- `repo_hygiene_a_plan.md` documents safe future artifact cleanup without deleting or untracking anything now.
- `src/short_term_edge/label_safety.py` adds deterministic label safety helpers.
- `tests/test_label_safety.py` and `tests/test_repo_hygiene_a.py` add focused safety/hygiene tests.

## Why requirements.txt was fixed/confirmed

Dependency constraints should be one per non-empty line so `pip install -r requirements.txt`, review diffs, and future dependency audits remain deterministic and readable. The file currently contains exactly:

- `pandas>=2.2`
- `numpy>=2.0`
- `matplotlib>=3.9`
- `databento>=0.80`
- `pyarrow>=15`
- `joblib>=1.4`
- `tqdm>=4.66`

No dependencies were added and no packages were installed.

## What .gitignore now protects

Generated/local research artifacts are ignored going forward:

- `data/raw/`
- `outputs/`
- `reports/`
- `artifacts/`
- `charts/`
- `trade_logs/`

Python/local cache protection includes:

- `.venv/`
- `__pycache__/`
- `*.pyc`
- `*.py[cod]`
- `.pytest_cache/`
- `.mypy_cache/`
- `.ruff_cache/`
- `.ipynb_checkpoints/`

## What was not deleted

No data, outputs, reports, artifacts, charts, trade logs, files, or git-tracked paths were deleted or untracked in this task. `.gitignore` does not remove already tracked files from git history.

## Safe future cleanup

A future cleanup branch can remove tracked generated artifacts from the git index while preserving local files with commands like these, after review. These commands were not run in this task:

```bash
git rm -r --cached outputs reports artifacts charts trade_logs
git rm -r --cached data/raw
```

Review with `git status --short` and `git diff --cached --stat` before committing any future cleanup. Large artifacts may belong in Git LFS, releases, or private archival storage. Raw Databento-derived data may have licensing/redistribution concerns and should not be public unless explicitly allowed.

## Label safety rules

- Labels never imply paper-trading approval.
- Missing `paper_trading_approved` defaults to `false`.
- Explicit false-like `paper_trading_approved` values are preserved as false.
- Explicit true-like `paper_trading_approved` values raise because current project outputs must remain false.
- `candidate_for_paper_review` means review packet language only, not paper-trading approval.
- Legacy `paper_test_candidate` is treated as legacy/research language, not approval.
- `watchlist_needs_more_history` is treated as research/watchlist language only, not paper-trading approval.
- Unknown labels do not imply approval.

## Guardrail confirmations

- Research/simulation only.
- Official gates unchanged.
- Paper trading not approved.
- No strategy signals generated.
- No strategy searches run.
- No phase scripts rerun.
- No candidate results changed.
- No promotions made.
- No live trading, broker adapters, order routing, API-key storage, webhooks, automated execution, or LLM-driven trade decisions added.

## Tests run

- `./.venv/Scripts/python.exe -m unittest tests.test_label_safety -v`
  - Result: passed, 7 tests.
- `./.venv/Scripts/python.exe -m unittest tests.test_repo_hygiene_a -v`
  - Result: passed, 5 tests.
- `./.venv/Scripts/python.exe -m unittest discover -s tests -v`
  - Result: passed, 385 tests in 42.029s.

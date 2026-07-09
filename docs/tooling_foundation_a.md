# Tooling Foundation A

Tooling Foundation A establishes a reproducible Python 3.11 environment and a
single verification interface without changing strategy logic, session rules,
promotion gates, or the authority of ML and LLM outputs.

## Dependency policy

- `requirements.txt` and `requirements-dev.txt` declare supported direct
  dependencies for intentional upgrades.
- `requirements.lock.txt` and `requirements-dev.lock.txt` pin the complete
  environments used for reproducible research and development/CI.
- CI upgrades to the recorded pip version before installing the development
  lock because Databento's certificate integration requires a recent pip.
- Dependency upgrades require `pip check`, quick verification, the canonical
  full suite, and a refreshed lock file.

The milestone adds these bounded capabilities:

- scikit-learn for future pipelines, metrics, logistic models, and calibration;
- SciPy for vetted statistical primitives;
- Pandera for explicit dataframe boundary schemas;
- DuckDB for read-only analysis of derived Arrow/Parquet research artifacts;
- Ruff and Hypothesis for fast feedback and property-based tests.

These libraries do not silently replace historical implementations. Frozen
Baseline B remains the NumPy implementation recorded in its release bundle.

## Research-use constraints

- Scikit-learn estimators must receive explicit chronological folds. Default
  shuffled or stratified classification cross-validation is not causal proof.
- Calibration mappings may fit only the partitions allowed by the Framework G
  calibration policy. Existing consumed holdouts remain unavailable for fit or
  threshold selection.
- SciPy's ordinary resampling routines do not replace the project's
  session-aware weekly/monthly block bootstrap.
- Pandera schemas should validate strictly and must not coerce missing coverage
  into zero, inactive, or negative outcomes.
- DuckDB is for derived local research artifacts. Canonical raw inputs remain
  local CSV files loaded through the existing timestamp/session path.
- Faster parameter search is not evidence. Optuna and broad automated sweeps
  remain deferred until the confirmatory-data process can control selection
  bias.

## Verification profiles

Run from either Windows or a POSIX environment using that platform's virtual
environment Python:

```text
python scripts/verify_project.py --profile quick
python scripts/verify_project.py --profile full
python scripts/verify_project.py --profile release
```

All profiles check Python and core locked versions, compile source/tests/scripts,
parse tracked JSON, scan tracked text for private-key markers, and lint the new
foundation files.

- `quick`: 40 hermetic tests covering schemas, artifacts, label safety, feature
  construction, and Framework G policy contracts. This is the CI profile.
- `full`: the canonical `unittest` discovery suite, including tests that use
  ignored local research outputs.
- `release`: full verification plus a clean Git worktree, local raw-data
  presence, hash/size validation for both frozen manifests, research-only flag
  validation, safe artifact paths, and structural reload of all Baseline B
  models.

Release verification validates historical provenance; it does not require an
older frozen release's source revision to equal the current `HEAD`.

## CI and hooks

`.github/workflows/ci.yml` runs the locked quick profile on Windows and does not
require licensed local market data. `.pre-commit-config.yaml` runs Ruff on the
new foundation files and the quick verifier through a platform-aware project
Python launcher.

Neither CI nor the hooks create research releases, mutate generated registries,
or authorize paper, shadow, or live execution.

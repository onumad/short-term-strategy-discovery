# Databento Recent Download: MGC And MNQ

Date downloaded: 2026-07-03

## Summary

Downloaded recent Databento 1-minute continuous futures data for MGC and MNQ into:

```text
C:\Users\ulzii\Documents\Short Term Strategy Discovery\data\raw
```

Requested Databento window:

```text
start = 2026-04-03T00:00:00-04:00
end   = 2026-07-03T00:00:00-04:00
```

The `end` timestamp is exclusive, so the latest included bars are from `2026-07-02T23:59:00-04:00`.

## Files

| File | Symbol | Rows | First timestamp | Last timestamp | SHA-256 |
| --- | --- | ---: | --- | --- | --- |
| `mgc_1m_databento_20260403_20260703.csv` | MGC | 87,665 | `2026-04-05T18:00:00-04:00` | `2026-07-02T23:59:00-04:00` | `399A4C668A1C7EC6ECD5DFCEBFC9E76B6AB9C10677828BB790E90F9BFE777C56` |
| `mnq_1m_databento_20260403_20260703.csv` | MNQ | 88,755 | `2026-04-03T00:00:00-04:00` | `2026-07-02T23:59:00-04:00` | `8D64FA44048EBAB287236B99CD08706C1A02259694D8D194BEFB3221548758C0` |

Both files use the lab CSV schema:

```text
timestamp,symbol,open,high,low,close,volume
```

## Commands Used

```powershell
python -m futures_prop_strategy_lab download-databento --symbol MGC.v.0 --lab-symbol MGC --start '2026-04-03T00:00:00-04:00' --end '2026-07-03T00:00:00-04:00' --output 'C:\Users\ulzii\Documents\Short Term Strategy Discovery\data\raw\mgc_1m_databento_20260403_20260703.csv'
python -m futures_prop_strategy_lab download-databento --symbol MNQ.v.0 --lab-symbol MNQ --start '2026-04-03T00:00:00-04:00' --end '2026-07-03T00:00:00-04:00' --output 'C:\Users\ulzii\Documents\Short Term Strategy Discovery\data\raw\mnq_1m_databento_20260403_20260703.csv'
```

## Validation

Focused offline OHLCV audit passed for both files after configuring these expected CME holiday closures:

- Good Friday 2026: `2026-04-03T09:15:00` through `2026-04-05T18:00:00`
- Juneteenth 2026 early close: `2026-06-19T13:00:00` through `2026-06-21T18:00:00`

Audit result:

| Symbol | Passed | Issue count | Unexplained gaps | Gap classifications |
| --- | --- | ---: | ---: | --- |
| MGC | true | 0 | 0 | `configured_closure=1`, `expected_weekend_closure=11` |
| MNQ | true | 0 | 0 | `configured_closure=2`, `expected_weekend_closure=11` |

## Notes

- This is research data only, not paper-trading or live-trading approval.
- No API key was written to project files.
- Plain date strings were not used for the final download because Databento interprets them at UTC midnight; explicit Eastern timestamps were used to preserve the intended local research window.

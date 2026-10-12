# Historical Data Integrity Incident — 2026-10-12

## Finding
All six historical market CSVs fail their companion provenance SHA-256 verification:
`R_100`, `1HZ100V`, `R_75`, `1HZ75V`, `R_50`, `1HZ50V`.

GitHub history shows each CSV and its companion JSON were introduced in the same initial baseline commit (`aa58fc641f`, 2026-10-08) and have no later file-specific commits. The mismatch therefore predates the recent release merges; the precise underlying cause cannot be proven using repository content alone.

## Remediation
- Preserve the original CSV and JSON bytes. Do **not** overwrite recorded hashes with hashes of unverified bytes.
- When companion hashes are missing or unequal, set file integrity to `FILE_INTEGRITY_FAILED`, source class to `UNVERIFIED_SOURCE`, source authentication to `SOURCE_AUTHENTICITY_UNVERIFIED`, and authoritative-research eligibility to `False`.
- Update regression tests to assert the actual file-versus-companion hash relationship rather than trusting legacy reports.
- Run per-market checks in GitHub Actions on future pull requests.
- Treat historical datasets as **exploratory only** until original acquisition artifacts, signatures or independently reproducible broker captures establish a new valid provenance chain. Verify hashes for such newly acquired data without retroactively rewriting the old evidence.

## Separate findings from offline SHADOW reconciliation
- V1.8.3 stored session: 210 committed, 156 resolved, 54 pending (8 pending with quotes); strict Cohort C under current validator = 0.
- V1.8.3.1 acceptance session: 258 committed, 204 resolved, 54 pending (8 pending with quotes); strict Cohort C under current validator = 28.
- The `total_quarantined=46` field describes only unquoted pending records; it must not be presented as all unresolved predictions.

## Scientific limitation
Neither passing tests nor correctly quarantined historical files prove any profitable Deriv strategy. No purchase execution is authorized; `LIVE_EXECUTION_DISABLED = True` and `NO_TRADE` remain required.

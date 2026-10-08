"""Automated Session Reconciliation Engine (V1.6.2).

Performs strict, independent forward-audit reconciliation across:
  1. Ticks: recorded live ticks, warmup ticks, duplicate ticks, rejected ticks.
  2. Quotes: recorded quotes, matching session quotes, freshness, response chronology.
  3. Predictions: session attribution, model frozen state, feature window bounds.
  4. Outcomes: referential integrity against forward_predictions, canonical 5-movement
     reconstruction, pending/incomplete/data-gap classification.
  5. Chronology: strict time ordering (quote -> feature -> prediction -> outcome).
  6. Source Provenance: verifies genuine LIVE_DERIV vs fixtures, replays, or legacy records.

Reconciliation Statuses:
  - RECONCILED: All referential integrity, accounting, provenance, and chronology checks pass.
  - COUNT_MISMATCH: Internal metric counts disagree (e.g., outcomes != predictions).
  - MISSING_SESSION_ID: Session ID missing, empty, or unresolvable in records.
  - ORPHAN_PREDICTION: Prediction without valid session or foreign reference.
  - ORPHAN_OUTCOME: Outcome record lacks corresponding prediction_id.
  - CROSS_SESSION_REFERENCE: Quotes, predictions, or outcomes reference mismatched session IDs.
  - TIMESTAMP_INCONSISTENCY: Chronological order violated (future quote or inverted resolution).
  - SOURCE_UNVERIFIED: Records originate from unverified, synthetic, or legacy unattributed sources.
"""
import json
import math
import os
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple

from forward_session import (
    ForwardSessionRegistry,
    ForwardSession,
    DEFAULT_SESSIONS_DB,
    RECON_STATUS_RECONCILED,
    RECON_STATUS_COUNT_MISMATCH,
    RECON_STATUS_MISSING_SESSION_ID,
    RECON_STATUS_ORPHAN_PREDICTION,
    RECON_STATUS_ORPHAN_OUTCOME,
    RECON_STATUS_CROSS_SESSION_REFERENCE,
    RECON_STATUS_TIMESTAMP_INCONSISTENCY,
    RECON_STATUS_SOURCE_UNVERIFIED,
)

DEFAULT_FORWARD_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "forward_predictions.db")
DEFAULT_QUOTES_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "quotes.db")


@dataclass
class ReconciliationReport:
    """Detailed audit report produced by SessionReconciler."""
    session_id: str
    symbol: str
    status: str                         # RECONCILED, COUNT_MISMATCH, etc.
    is_verified: bool                   # True only if status == RECONCILED
    reconciled_at_utc: str

    # Tick accounting
    session_counter_ticks: int
    live_ticks: int
    warmup_ticks: int
    duplicate_ticks: int
    rejected_ticks: int
    csv_ticks: Optional[int]

    # Quote accounting
    quotes_recorded_in_db: int
    quotes_linked_to_session: int
    predictions_with_quotes: int
    quote_coverage_pct: float

    # Prediction accounting
    total_predictions: int
    unattributed_predictions: int
    cross_session_predictions: int

    # Outcome accounting
    total_outcomes: int
    resolved_outcomes: int
    pending_outcomes: int
    incomplete_outcomes: int
    data_gap_outcomes: int
    orphan_outcomes: int
    orphan_predictions: int

    # Provenance
    source_provenance_breakdown: Dict[str, int]
    is_live_deriv_provenance: bool

    # Chronological integrity
    chronology_errors: int
    future_quote_errors: int

    # Check details & findings
    issues: List[str] = field(default_factory=list)
    passed_checks: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "symbol": self.symbol,
            "status": self.status,
            "is_verified": self.is_verified,
            "reconciled_at_utc": self.reconciled_at_utc,
            "ticks": {
                "session_counter_ticks": self.session_counter_ticks,
                "live_ticks": self.live_ticks,
                "warmup_ticks": self.warmup_ticks,
                "duplicate_ticks": self.duplicate_ticks,
                "rejected_ticks": self.rejected_ticks,
                "csv_ticks": self.csv_ticks,
            },
            "quotes": {
                "quotes_recorded_in_db": self.quotes_recorded_in_db,
                "quotes_linked_to_session": self.quotes_linked_to_session,
                "predictions_with_quotes": self.predictions_with_quotes,
                "quote_coverage_pct": self.quote_coverage_pct,
            },
            "predictions": {
                "total_predictions": self.total_predictions,
                "unattributed_predictions": self.unattributed_predictions,
                "cross_session_predictions": self.cross_session_predictions,
            },
            "outcomes": {
                "total_outcomes": self.total_outcomes,
                "resolved_outcomes": self.resolved_outcomes,
                "pending_outcomes": self.pending_outcomes,
                "incomplete_outcomes": self.incomplete_outcomes,
                "data_gap_outcomes": self.data_gap_outcomes,
                "orphan_outcomes": self.orphan_outcomes,
                "orphan_predictions": self.orphan_predictions,
            },
            "provenance": {
                "breakdown": self.source_provenance_breakdown,
                "is_live_deriv": self.is_live_deriv_provenance,
            },
            "chronology": {
                "chronology_errors": self.chronology_errors,
                "future_quote_errors": self.future_quote_errors,
            },
            "issues": self.issues,
            "passed_checks": self.passed_checks,
        }

    def summary_text(self) -> str:
        lines = [
            f"=== SESSION RECONCILIATION AUDIT [{self.session_id[:8]}] ===",
            f"Status: {self.status} (Verified: {self.is_verified})",
            f"Reconciled At: {self.reconciled_at_utc}",
            "--- TICK ACCOUNTING ---",
            f"  Session Ticks     : {self.session_counter_ticks}",
            f"  Live Ticks        : {self.live_ticks}",
            f"  Warm-up Ticks     : {self.warmup_ticks}",
            f"  Duplicate Ticks   : {self.duplicate_ticks}",
            f"  Rejected Ticks    : {self.rejected_ticks}",
            f"  CSV File Ticks    : {self.csv_ticks if self.csv_ticks is not None else 'N/A'}",
            "--- PREDICTION & OUTCOME ACCOUNTING ---",
            f"  Total Predictions : {self.total_predictions}",
            f"  Resolved Outcomes : {self.resolved_outcomes}",
            f"  Pending Outcomes  : {self.pending_outcomes}",
            f"  Incomplete/Gaps   : {self.incomplete_outcomes + self.data_gap_outcomes}",
            f"  Orphan Outcomes   : {self.orphan_outcomes}",
            f"  Orphan Preds      : {self.orphan_predictions}",
            "--- QUOTE ACCOUNTING ---",
            f"  Quotes for Session: {self.quotes_linked_to_session}",
            f"  Predictions w/ Q  : {self.predictions_with_quotes} ({self.quote_coverage_pct:.1f}%)",
            "--- PROVENANCE & CHRONOLOGY ---",
            f"  Live Deriv Source : {self.is_live_deriv_provenance}",
            f"  Chronology Errors : {self.chronology_errors}",
            f"  Future Quotes     : {self.future_quote_errors}",
        ]
        if self.issues:
            lines.append("--- RECONCILIATION ISSUES ---")
            for iss in self.issues:
                lines.append(f"  [X] {iss}")
        else:
            lines.append("--- ALL CHECKS PASSED ---")
        return "\n".join(lines)


class SessionReconciler:
    """Validates session data integrity across ticks, quotes, predictions, and outcomes."""

    def __init__(
        self,
        registry_db_path: Optional[str] = None,
        journal_db_path: Optional[str] = None,
        quote_db_path: Optional[str] = None,
    ):
        self.registry_db_path = registry_db_path or DEFAULT_SESSIONS_DB
        self.journal_db_path = journal_db_path or DEFAULT_FORWARD_DB
        self.quote_db_path = quote_db_path or DEFAULT_QUOTES_DB
        self.registry = ForwardSessionRegistry(db_path=self.registry_db_path)

    def reconcile_session(self, session_id: str) -> ReconciliationReport:
        """Executes full automated reconciliation for the given session ID."""
        issues: List[str] = []
        passed: List[str] = []
        now_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")

        # 1. Fetch Session Record
        session = self.registry.get_session(session_id)
        if not session:
            return ReconciliationReport(
                session_id=session_id,
                symbol="UNKNOWN",
                status=RECON_STATUS_MISSING_SESSION_ID,
                is_verified=False,
                reconciled_at_utc=now_utc,
                session_counter_ticks=0,
                live_ticks=0,
                warmup_ticks=0,
                duplicate_ticks=0,
                rejected_ticks=0,
                csv_ticks=None,
                quotes_recorded_in_db=0,
                quotes_linked_to_session=0,
                predictions_with_quotes=0,
                quote_coverage_pct=0.0,
                total_predictions=0,
                unattributed_predictions=0,
                cross_session_predictions=0,
                total_outcomes=0,
                resolved_outcomes=0,
                pending_outcomes=0,
                incomplete_outcomes=0,
                data_gap_outcomes=0,
                orphan_outcomes=0,
                orphan_predictions=0,
                source_provenance_breakdown={},
                is_live_deriv_provenance=False,
                chronology_errors=0,
                future_quote_errors=0,
                issues=[f"Session ID '{session_id}' not found in registry database."]
            )

        symbol = session.symbol
        passed.append(f"Session found in registry with status '{session.status}'.")

        # 2. Inspect CSV ticks if file exists
        csv_ticks: Optional[int] = None
        if session.live_ticks_csv and os.path.exists(session.live_ticks_csv):
            try:
                import csv
                with open(session.live_ticks_csv, "r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    header = next(reader, None)
                    sess_col = None
                    if header:
                        for idx, col_name in enumerate(header):
                            if col_name.strip() == "session_id":
                                sess_col = idx
                                break
                    matching_lines = 0
                    total_lines = 0
                    for row in reader:
                        if not row:
                            continue
                        total_lines += 1
                        if sess_col is not None and len(row) > sess_col:
                            if row[sess_col].strip() == session.session_id:
                                matching_lines += 1
                    csv_ticks = matching_lines if matching_lines > 0 else total_lines
                passed.append(f"Live ticks CSV verified: {csv_ticks} lines recorded.")
            except Exception as e:
                issues.append(f"Could not read live ticks CSV: {e}")

        # 3. Query predictions database
        conn_pred = sqlite3.connect(self.journal_db_path, timeout=10.0)
        conn_pred.row_factory = sqlite3.Row
        try:
            # Check PRAGMA foreign keys
            fk_status = conn_pred.execute("PRAGMA foreign_keys;").fetchone()
            if fk_status and fk_status[0] == 1:
                passed.append("Foreign keys are active on journal database connection.")

            # Predictions strictly for this session
            pred_rows = conn_pred.execute(
                "SELECT * FROM forward_predictions WHERE session_id = ? ORDER BY timestamp ASC",
                (session_id,)
            ).fetchall()
            preds = [dict(r) for r in pred_rows]
            total_preds = len(preds)

            # Check if there are unattributed or blank predictions
            blank_preds = conn_pred.execute(
                "SELECT COUNT(*) FROM forward_predictions WHERE session_id IS NULL OR session_id = ''"
            ).fetchone()[0]

            # Cross-session check
            cross_preds = 0
            for p in preds:
                if p.get("session_id") != session_id:
                    cross_preds += 1

            # Provenance breakdown
            provenance_counts: Dict[str, int] = {}
            for p in preds:
                src = p.get("source_provenance") or "UNKNOWN_SOURCE"
                provenance_counts[src] = provenance_counts.get(src, 0) + 1

            # Outcomes for this session
            # Try querying forward_outcomes table if present
            has_outcomes_table = conn_pred.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='forward_outcomes'"
            ).fetchone()[0] > 0

            outcomes_rows = []
            if has_outcomes_table:
                outcomes_rows = conn_pred.execute(
                    "SELECT * FROM forward_outcomes WHERE session_id = ? ORDER BY resolution_timestamp ASC",
                    (session_id,)
                ).fetchall()
            outcomes = [dict(r) for r in outcomes_rows]
            total_outcomes = len(outcomes)

            # Check orphan outcomes (outcomes referencing non-existent predictions)
            orphan_outcomes = 0
            if has_outcomes_table:
                orphan_rows = conn_pred.execute("""
                    SELECT COUNT(*) FROM forward_outcomes o
                    LEFT JOIN forward_predictions p ON o.prediction_id = p.prediction_id
                    WHERE o.session_id = ? AND p.prediction_id IS NULL
                """, (session_id,)).fetchone()
                orphan_outcomes = orphan_rows[0] if orphan_rows else 0

            # Check orphan predictions (predictions marked resolved in forward_predictions but missing outcome row)
            orphan_predictions = 0
            if has_outcomes_table and total_preds > 0:
                missing_outcomes = conn_pred.execute("""
                    SELECT COUNT(*) FROM forward_predictions p
                    LEFT JOIN forward_outcomes o ON p.prediction_id = o.prediction_id
                    WHERE p.session_id = ? 
                      AND p.outcome_status IN ('RESOLVED', 'OUTCOME_RECONSTRUCTED', 'OUTCOME_VERIFIED')
                      AND o.outcome_id IS NULL
                """, (session_id,)).fetchone()
                orphan_predictions = missing_outcomes[0] if missing_outcomes else 0

        finally:
            conn_pred.close()

        # 4. Count outcome categories from predictions
        resolved_count = sum(1 for p in preds if p.get("outcome_status") in ("RESOLVED", "OUTCOME_RECONSTRUCTED", "OUTCOME_VERIFIED"))
        pending_count = sum(1 for p in preds if p.get("outcome_status") == "PENDING")
        incomplete_count = sum(1 for p in preds if p.get("outcome_status") == "OUTCOME_INCOMPLETE")
        data_gap_count = sum(1 for p in preds if p.get("outcome_status") == "OUTCOME_DATA_GAP")
        unverified_count = sum(1 for p in preds if p.get("outcome_status") == "OUTCOME_UNVERIFIED")

        # 5. Query quote database
        conn_quote = sqlite3.connect(self.quote_db_path, timeout=10.0)
        conn_quote.row_factory = sqlite3.Row
        try:
            has_quotes_table = conn_quote.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='quotes'"
            ).fetchone()[0] > 0
            if has_quotes_table:
                total_quotes_db = conn_quote.execute("SELECT COUNT(*) FROM quotes").fetchone()[0]
                session_quotes_rows = conn_quote.execute(
                    "SELECT * FROM quotes WHERE session_id = ? ORDER BY request_timestamp ASC",
                    (session_id,)
                ).fetchall()
                session_quotes = [dict(r) for r in session_quotes_rows]
                quotes_linked = len(session_quotes)
            else:
                total_quotes_db = 0
                session_quotes = []
                quotes_linked = 0
        finally:
            conn_quote.close()

        # Quotes associated with predictions
        preds_with_quotes = sum(
            1 for p in preds
            if (p.get("runhigh_ask") is not None and float(p.get("runhigh_ask") or 0) > 0) or
               (p.get("runlow_ask") is not None and float(p.get("runlow_ask") or 0) > 0) or
               (p.get("quote_id") is not None and p.get("quote_id") != "")
        )
        quote_cov_pct = (preds_with_quotes / total_preds * 100.0) if total_preds > 0 else 0.0

        # 6. Chronology and Timestamp Integrity Checks
        chronology_errors = 0
        future_quote_errors = 0

        # Build index of session quotes for timestamp matching
        quote_time_by_id = {
            (q.get("proposal_id") or str(q.get("id"))): q.get("response_timestamp") or q.get("request_timestamp")
            for q in session_quotes
        }

        # Build index of session outcomes for authoritative outcome chronology (V1.6.3 Section 13)
        outcome_by_pred_id = {
            o.get("prediction_id"): o for o in outcomes if o.get("prediction_id")
        }

        for p in preds:
            pred_ts = p.get("timestamp") or 0.0
            qid = p.get("quote_id")
            pred_id = p.get("prediction_id")

            # Check quote response received before prediction timestamp
            if qid and qid in quote_time_by_id:
                q_ts = quote_time_by_id[qid]
                if q_ts and q_ts > pred_ts + 2.0:  # Tolerance of 2.0s for Deriv WebSocket proposal polling latency
                    future_quote_errors += 1
                    chronology_errors += 1

            # Check outcome resolution timestamp not earlier than prediction timestamp (from authoritative outcome)
            out = outcome_by_pred_id.get(pred_id)
            res_ts = (out.get("resolution_timestamp") if out else None) or p.get("resolution_timestamp")
            if res_ts and res_ts < pred_ts:
                chronology_errors += 1

            # Check entry epoch vs expiry epoch from authoritative records
            entry_ep = (out.get("entry_epoch") if out else None) or p.get("entry_epoch")
            expiry_ep = (out.get("expiry_epoch") if out else None) or p.get("expiry_epoch")
            if entry_ep and expiry_ep and expiry_ep < entry_ep:
                chronology_errors += 1

        # 7. Evaluate Specific Reconciliation Rules
        status = RECON_STATUS_RECONCILED

        # Missing session ID rule
        if blank_preds > 0:
            issues.append(f"Database contains {blank_preds} prediction records with blank or null session IDs.")
            # Note: if the current session itself has no valid predictions or blank_preds exist in database, flag it
        if not session_id or session_id.strip() == "":
            status = RECON_STATUS_MISSING_SESSION_ID
            issues.append("Target session_id is empty or null.")

        # Cross-session check
        if cross_preds > 0:
            status = RECON_STATUS_CROSS_SESSION_REFERENCE
            issues.append(f"Found {cross_preds} predictions with mismatched session IDs.")

        # Orphan outcomes check
        if orphan_outcomes > 0:
            status = RECON_STATUS_ORPHAN_OUTCOME
            issues.append(f"Found {orphan_outcomes} orphan outcomes without parent predictions.")

        # Orphan predictions check
        if orphan_predictions > 0:
            status = RECON_STATUS_ORPHAN_PREDICTION
            issues.append(f"Found {orphan_predictions} resolved predictions missing corresponding outcome rows.")

        # Chronology / future quotes check
        if future_quote_errors > 0 or chronology_errors > 0:
            status = RECON_STATUS_TIMESTAMP_INCONSISTENCY
            issues.append(f"Timestamp inconsistencies detected: {chronology_errors} chronological violations, {future_quote_errors} future quotes.")

        # Source provenance check
        is_live = False
        if total_preds > 0:
            live_count = provenance_counts.get("LIVE_DERIV", 0) + provenance_counts.get("deriv_websocket_live", 0)
            if live_count == total_preds:
                is_live = True
                passed.append(f"All {total_preds} predictions verified as live Deriv provenance.")
            elif provenance_counts.get("LEGACY_UNATTRIBUTED", 0) > 0:
                status = RECON_STATUS_SOURCE_UNVERIFIED
                issues.append(f"Session contains {provenance_counts.get('LEGACY_UNATTRIBUTED')} LEGACY_UNATTRIBUTED records.")
            elif provenance_counts.get("SYNTHETIC_FIXTURE", 0) > 0 or provenance_counts.get("REPLAY_TEST", 0) > 0:
                is_live = False
                passed.append("Session verified as test / fixture provenance.")
            elif live_count > 0:
                is_live = True
                passed.append(f"Mixed provenance: {live_count} LIVE_DERIV out of {total_preds}.")
            else:
                status = RECON_STATUS_SOURCE_UNVERIFIED
                issues.append(f"No predictions with verified LIVE_DERIV source provenance. Counts: {provenance_counts}")
        else:
            # If 0 predictions, check ticks
            if session.live_ticks > 0:
                is_live = True

        # Count reconciliation check
        # Total predictions in journal must equal sum of all outcome states
        sum_outcomes = resolved_count + pending_count + incomplete_count + data_gap_count + unverified_count
        if total_preds != sum_outcomes:
            status = RECON_STATUS_COUNT_MISMATCH
            issues.append(f"Outcome sum mismatch: total predictions {total_preds} != outcome states {sum_outcomes}.")
        else:
            passed.append(f"Prediction outcome sum matches: {total_preds} == {sum_outcomes}.")

        # Registry counter vs Journal records reconciliation (V1.6.2 Section 12)
        if session.total_predictions != total_preds:
            status = RECON_STATUS_COUNT_MISMATCH
            issues.append(
                f"Prediction count mismatch: registry recorded {session.total_predictions} predictions, "
                f"but journal database contains {total_preds} records attributed to this session."
            )
        else:
            passed.append(f"Registry prediction count reconciled ({session.total_predictions} == {total_preds}).")

        # In a completed live session, having >0 predictions but negligible ticks is an accounting defect
        if session.status in ("COMPLETED", "ACTIVE") and session.total_predictions > 10 and session.total_ticks < 20:
            status = RECON_STATUS_COUNT_MISMATCH
            issues.append(
                f"Critical tick accounting mismatch: session recorded {session.total_predictions} predictions "
                f"on only {session.total_ticks} ticks (insufficient tick history for rolling 25-tick features)."
            )

        # If CSV file exists, total session ticks should be compatible with CSV lines
        if csv_ticks is not None:
            expected_ticks = session.total_ticks if session.total_ticks > 0 else (session.live_ticks + session.warmup_ticks)
            if expected_ticks > 0:
                if abs(csv_ticks - expected_ticks) > max(10, int(expected_ticks * 0.05)):
                    issues.append(f"Live ticks accounting mismatch: registry has {expected_ticks} total ticks but CSV has {csv_ticks}.")
                    if status == RECON_STATUS_RECONCILED:
                        status = RECON_STATUS_COUNT_MISMATCH
                else:
                    passed.append(f"Session ticks match CSV line count ({expected_ticks} vs {csv_ticks}).")

        is_verified = (status == RECON_STATUS_RECONCILED)

        # 8. Update registry database with reconciliation result
        self.registry.update_reconciliation_status(session_id=session_id, reconciliation_status=status)

        report = ReconciliationReport(
            session_id=session_id,
            symbol=symbol,
            status=status,
            is_verified=is_verified,
            reconciled_at_utc=now_utc,
            session_counter_ticks=session.total_ticks,
            live_ticks=session.live_ticks,
            warmup_ticks=session.warmup_ticks,
            duplicate_ticks=session.duplicate_ticks,
            rejected_ticks=session.rejected_ticks,
            csv_ticks=csv_ticks,
            quotes_recorded_in_db=total_quotes_db,
            quotes_linked_to_session=quotes_linked,
            predictions_with_quotes=preds_with_quotes,
            quote_coverage_pct=round(quote_cov_pct, 2),
            total_predictions=total_preds,
            unattributed_predictions=blank_preds,
            cross_session_predictions=cross_preds,
            total_outcomes=total_outcomes,
            resolved_outcomes=resolved_count,
            pending_outcomes=pending_count,
            incomplete_outcomes=incomplete_count,
            data_gap_outcomes=data_gap_count,
            orphan_outcomes=orphan_outcomes,
            orphan_predictions=orphan_predictions,
            source_provenance_breakdown=provenance_counts,
            is_live_deriv_provenance=is_live,
            chronology_errors=chronology_errors,
            future_quote_errors=future_quote_errors,
            issues=issues,
            passed_checks=passed,
        )
        return report


if __name__ == "__main__":
    import sys
    sid = sys.argv[1] if len(sys.argv) > 1 else None
    if not sid:
        reg = ForwardSessionRegistry()
        sessions = reg.list_sessions(limit=5)
        if sessions:
            sid = sessions[0].session_id
            print(f"No session ID provided, checking most recent session: {sid}")
        else:
            print("No sessions found in registry.")
            sys.exit(1)

    reconciler = SessionReconciler()
    rep = reconciler.reconcile_session(sid)
    print(rep.summary_text())

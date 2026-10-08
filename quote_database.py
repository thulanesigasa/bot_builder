"""Persistent Historical Proposal Quote Database for Deriv RUNHIGH / RUNLOW (V1.5.1).

Stores genuinely observed proposal quotes in a high-performance, indexed SQLite database.
Enforces strict timestamp synchronization, lookahead bias prevention, quote freshness bounds,
and full data provenance.

Architecture:
- Table: quotes (Indexed by market_symbol, contract_type, response_timestamp)
- Strict Lookahead Protection: response_timestamp <= decision_timestamp
- Configurable Freshness Window: decision_timestamp - response_timestamp <= max_freshness_seconds
- Guaranteed Fallback: Returns None / QUOTE_UNAVAILABLE when valid quotes are missing.
"""
import argparse
import csv
import json
import os
import sqlite3
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple

from quote_recorder import ProposalRecord


DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "quotes.db")


class QuoteDatabase:
    """Manages SQLite storage, lookahead-free querying, and validation of recorded quotes."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS quotes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_timestamp REAL NOT NULL,
                    response_timestamp REAL NOT NULL,
                    market_symbol TEXT NOT NULL,
                    contract_type TEXT NOT NULL,
                    contract_duration INTEGER NOT NULL DEFAULT 5,
                    duration_unit TEXT NOT NULL DEFAULT 't',
                    stake REAL NOT NULL,
                    total_payout REAL NOT NULL,
                    potential_net_profit REAL NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'USD',
                    proposal_id TEXT,
                    quote_source TEXT NOT NULL,
                    quote_latency_ms REAL NOT NULL,
                    collection_status TEXT NOT NULL,
                    api_response_metadata TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_quotes_lookup
                ON quotes (market_symbol, contract_type, response_timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_quotes_epoch
                ON quotes (response_timestamp)
            """)
            conn.commit()

    def store_quote(self, record: Any) -> int:
        """Stores a single ProposalRecord or dictionary into the database."""
        d = asdict(record) if hasattr(record, "__dataclass_fields__") else dict(record)
        created_at = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cur = conn.execute("""
                INSERT INTO quotes (
                    request_timestamp, response_timestamp, market_symbol, contract_type,
                    contract_duration, duration_unit, stake, total_payout,
                    potential_net_profit, currency, proposal_id, quote_source,
                    quote_latency_ms, collection_status, api_response_metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                float(d.get("request_timestamp", 0.0)),
                float(d.get("response_timestamp", 0.0)),
                str(d.get("market_symbol", "R_75")),
                str(d.get("contract_type", "RUNHIGH")).upper(),
                int(d.get("contract_duration", 5)),
                str(d.get("duration_unit", "t")),
                float(d.get("stake", 2.0)),
                float(d.get("total_payout", 0.0)),
                float(d.get("potential_net_profit", 0.0)),
                str(d.get("currency", "USD")),
                str(d.get("proposal_id", "NONE")),
                str(d.get("quote_source", "live_proposal")),
                float(d.get("quote_latency_ms", 0.0)),
                str(d.get("collection_status", "QUOTE_AVAILABLE")),
                str(d.get("api_response_metadata", "")),
                created_at
            ))
            conn.commit()
            return cur.lastrowid or 0

    def store_quotes_batch(self, records: List[Any]) -> int:
        """Stores multiple quotes in a single transaction."""
        if not records:
            return 0
        created_at = datetime.now(timezone.utc).isoformat()
        rows = []
        for r in records:
            d = asdict(r) if hasattr(r, "__dataclass_fields__") else dict(r)
            rows.append((
                float(d.get("request_timestamp", 0.0)),
                float(d.get("response_timestamp", 0.0)),
                str(d.get("market_symbol", "R_75")),
                str(d.get("contract_type", "RUNHIGH")).upper(),
                int(d.get("contract_duration", 5)),
                str(d.get("duration_unit", "t")),
                float(d.get("stake", 2.0)),
                float(d.get("total_payout", 0.0)),
                float(d.get("potential_net_profit", 0.0)),
                str(d.get("currency", "USD")),
                str(d.get("proposal_id", "NONE")),
                str(d.get("quote_source", "live_proposal")),
                float(d.get("quote_latency_ms", 0.0)),
                str(d.get("collection_status", "QUOTE_AVAILABLE")),
                str(d.get("api_response_metadata", "")),
                created_at
            ))
        with self._get_connection() as conn:
            conn.executemany("""
                INSERT INTO quotes (
                    request_timestamp, response_timestamp, market_symbol, contract_type,
                    contract_duration, duration_unit, stake, total_payout,
                    potential_net_profit, currency, proposal_id, quote_source,
                    quote_latency_ms, collection_status, api_response_metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)
            conn.commit()
        return len(rows)

    def get_latest_quote_before(
        self,
        symbol: str,
        contract_type: str,
        timestamp: float,
        max_freshness_seconds: float = 60.0
    ) -> Optional[ProposalRecord]:
        """Retrieves the most recent genuinely observed quote strictly at or before timestamp.
        
        Guarantees:
        1. Lookahead protection: response_timestamp <= timestamp.
        2. Freshness check: timestamp - response_timestamp <= max_freshness_seconds.
        3. Only valid quotes (collection_status == 'QUOTE_AVAILABLE' and total_payout > 0).
        4. If no quote satisfies criteria, returns None (QUOTE_UNAVAILABLE).
        """
        c_type = contract_type.upper()
        if c_type in ("UP", "RISE"):
            c_type = "RUNHIGH"
        elif c_type in ("DOWN", "FALL"):
            c_type = "RUNLOW"

        min_time = timestamp - max_freshness_seconds
        with self._get_connection() as conn:
            cur = conn.execute("""
                SELECT * FROM quotes
                WHERE market_symbol = ?
                  AND contract_type = ?
                  AND response_timestamp <= ?
                  AND response_timestamp >= ?
                  AND collection_status = 'QUOTE_AVAILABLE'
                  AND total_payout > 0
                ORDER BY response_timestamp DESC
                LIMIT 1
            """, (symbol, c_type, float(timestamp), float(min_time)))
            row = cur.fetchone()
            if row is None:
                return None

            return ProposalRecord(
                request_timestamp=row["request_timestamp"],
                response_timestamp=row["response_timestamp"],
                market_symbol=row["market_symbol"],
                contract_type=row["contract_type"],
                contract_duration=row["contract_duration"],
                duration_unit=row["duration_unit"],
                stake=row["stake"],
                total_payout=row["total_payout"],
                potential_net_profit=row["potential_net_profit"],
                currency=row["currency"],
                proposal_id=row["proposal_id"],
                quote_source=row["quote_source"],
                quote_latency_ms=row["quote_latency_ms"],
                collection_status=row["collection_status"],
                api_response_metadata=row["api_response_metadata"]
            )

    def inspect_quotes(self, symbol: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """Returns the most recent quotes for inspection."""
        with self._get_connection() as conn:
            if symbol:
                cur = conn.execute("""
                    SELECT * FROM quotes WHERE market_symbol = ?
                    ORDER BY response_timestamp DESC LIMIT ?
                """, (symbol, limit))
            else:
                cur = conn.execute("""
                    SELECT * FROM quotes
                    ORDER BY response_timestamp DESC LIMIT ?
                """, (limit,))
            return [dict(r) for r in cur.fetchall()]

    def validate_quote_records(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Validates all stored quotes against data integrity, timestamp sanity, and payout rules."""
        with self._get_connection() as conn:
            where_clause = "WHERE market_symbol = ?" if symbol else ""
            params = (symbol,) if symbol else ()
            cur = conn.execute(f"SELECT * FROM quotes {where_clause}", params)
            rows = cur.fetchall()

        total = len(rows)
        if total == 0:
            return {
                "total_records": 0,
                "valid_records": 0,
                "anomalies_detected": 0,
                "issues": ["No quote records found in database."]
            }

        issues: List[str] = []
        now = time.time() + 300.0  # 5 min clock skew tolerance

        for r in rows:
            qid = r["id"]
            if r["response_timestamp"] < r["request_timestamp"]:
                issues.append(f"Record {qid}: Response timestamp before request timestamp")
            if r["response_timestamp"] > now:
                issues.append(f"Record {qid}: Future timestamp detected")
            if r["collection_status"] == "QUOTE_AVAILABLE":
                if r["stake"] <= 0:
                    issues.append(f"Record {qid}: Non-positive stake {r['stake']}")
                if r["total_payout"] <= 0:
                    issues.append(f"Record {qid}: Non-positive payout {r['total_payout']}")
                if r["total_payout"] < r["stake"]:
                    issues.append(f"Record {qid}: Payout {r['total_payout']} less than stake {r['stake']}")
            if r["quote_latency_ms"] < 0:
                issues.append(f"Record {qid}: Negative latency {r['quote_latency_ms']}")

        valid_count = total - len(issues)
        return {
            "total_records": total,
            "valid_records": valid_count,
            "anomalies_detected": len(issues),
            "status": "VALID" if len(issues) == 0 else "ANOMALIES_DETECTED",
            "issues": issues[:25]
        }

    def export_quote_history(self, output_csv: str, symbol: Optional[str] = None) -> int:
        """Exports quote records to a CSV file."""
        os.makedirs(os.path.dirname(os.path.abspath(output_csv)), exist_ok=True)
        with self._get_connection() as conn:
            where_clause = "WHERE market_symbol = ?" if symbol else ""
            params = (symbol,) if symbol else ()
            cur = conn.execute(f"SELECT * FROM quotes {where_clause} ORDER BY response_timestamp ASC", params)
            rows = cur.fetchall()

        if not rows:
            return 0

        fieldnames = [c for c in rows[0].keys() if c != "id"]
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in rows:
                d = dict(r)
                d.pop("id", None)
                writer.writerow(d)

        return len(rows)

    def report_quote_coverage(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Reports quote inventory coverage, timestamp spans, and direction counts."""
        with self._get_connection() as conn:
            where_clause = "WHERE market_symbol = ?" if symbol else ""
            params = (symbol,) if symbol else ()

            cur = conn.execute(f"""
                SELECT
                    COUNT(*) as total_count,
                    SUM(CASE WHEN collection_status = 'QUOTE_AVAILABLE' THEN 1 ELSE 0 END) as available_count,
                    SUM(CASE WHEN contract_type = 'RUNHIGH' AND collection_status = 'QUOTE_AVAILABLE' THEN 1 ELSE 0 END) as runhigh_count,
                    SUM(CASE WHEN contract_type = 'RUNLOW' AND collection_status = 'QUOTE_AVAILABLE' THEN 1 ELSE 0 END) as runlow_count,
                    MIN(response_timestamp) as min_ts,
                    MAX(response_timestamp) as max_ts,
                    AVG(quote_latency_ms) as avg_latency
                FROM quotes
                {where_clause}
            """, params)
            res = cur.fetchone()

        if not res or res["total_count"] == 0:
            return {
                "symbol": symbol or "ALL",
                "total_quotes": 0,
                "available_quotes": 0,
                "runhigh_quotes": 0,
                "runlow_quotes": 0,
                "earliest_timestamp": None,
                "latest_timestamp": None,
                "earliest_iso": "N/A",
                "latest_iso": "N/A",
                "time_span_hours": 0.0,
                "avg_latency_ms": 0.0,
                "status": "EMPTY"
            }

        min_ts = res["min_ts"] or 0.0
        max_ts = res["max_ts"] or 0.0
        span_hrs = (max_ts - min_ts) / 3600.0 if max_ts > min_ts else 0.0

        return {
            "symbol": symbol or "ALL",
            "total_quotes": int(res["total_count"]),
            "available_quotes": int(res["available_count"] or 0),
            "runhigh_quotes": int(res["runhigh_count"] or 0),
            "runlow_quotes": int(res["runlow_count"] or 0),
            "earliest_timestamp": min_ts,
            "latest_timestamp": max_ts,
            "earliest_iso": datetime.fromtimestamp(min_ts, timezone.utc).isoformat() if min_ts > 0 else "N/A",
            "latest_iso": datetime.fromtimestamp(max_ts, timezone.utc).isoformat() if max_ts > 0 else "N/A",
            "time_span_hours": round(span_hrs, 2),
            "avg_latency_ms": round(res["avg_latency"] or 0.0, 2),
            "status": "ACTIVE"
        }


def main():
    parser = argparse.ArgumentParser(description="Deriv Historical Quote Database Manager")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="Path to SQLite quotes database")
    parser.add_argument("--symbol", default=None, help="Filter by symbol (e.g. R_75)")
    parser.add_argument("--inspect", action="store_true", help="Inspect recent quotes")
    parser.add_argument("--validate", action="store_true", help="Validate quote records")
    parser.add_argument("--coverage", action="store_true", help="Print quote coverage report")
    parser.add_argument("--export", default=None, help="Export quotes to CSV path")
    args = parser.parse_args()

    db = QuoteDatabase(db_path=args.db)

    if args.validate:
        res = db.validate_quote_records(symbol=args.symbol)
        print("=== QUOTE DATABASE VALIDATION ===")
        print(f"Status:   {res['status']}")
        print(f"Total:    {res['total_records']}")
        print(f"Valid:    {res['valid_records']}")
        print(f"Issues:   {res['anomalies_detected']}")
        if res.get("issues"):
            print("Issue samples:")
            for iss in res["issues"]:
                print(f"  - {iss}")

    elif args.coverage or (not args.inspect and not args.export and not args.validate):
        cov = db.report_quote_coverage(symbol=args.symbol)
        print("=== QUOTE DATABASE COVERAGE REPORT ===")
        print(f"Symbol:           {cov['symbol']}")
        print(f"Status:           {cov['status']}")
        print(f"Total Quotes:     {cov['total_quotes']}")
        print(f"Available Quotes: {cov['available_quotes']} (RUNHIGH: {cov['runhigh_quotes']}, RUNLOW: {cov['runlow_quotes']})")
        print(f"Earliest Quote:   {cov['earliest_iso']}")
        print(f"Latest Quote:     {cov['latest_iso']}")
        print(f"Timespan:         {cov['time_span_hours']} hours")
        print(f"Avg Latency:      {cov['avg_latency_ms']} ms")

    if args.inspect:
        quotes = db.inspect_quotes(symbol=args.symbol, limit=10)
        print("\n=== RECENT QUOTES (Last 10) ===")
        for q in quotes:
            print(f"[{q['contract_type']}] TS: {q['response_timestamp']} | Stake: ${q['stake']:.2f} -> Payout: ${q['total_payout']:.2f} | Status: {q['collection_status']}")

    if args.export:
        n = db.export_quote_history(args.export, symbol=args.symbol)
        print(f"\nExported {n} quote records to {args.export}")


if __name__ == "__main__":
    main()

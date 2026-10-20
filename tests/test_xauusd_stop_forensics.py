"""Regression evidence and guardrails for the MT5 Jan 2 -> Jan 4 weekend stop."""
from pathlib import Path
import re

# Exact figures recorded by the user-provided 2026-10-20 V4 MT5 Journal.
CASES = [
    {"variant":"ADAPTIVE", "starting":50.0,"expected_stop_loss":34.8782,"closed":-37.42,"actual_pnl":-87.42},
    {"variant":"THEORETICAL","starting":50.0,"expected_stop_loss":81.3825,"closed":-153.98,"actual_pnl":-203.98},
]

def test_weekend_overrun_evidence_reconciles():
    for x in CASES:
        assert abs(x["starting"]+x["actual_pnl"]-x["closed"])<1e-6
        assert abs(x["actual_pnl"])>x["expected_stop_loss"]
        assert abs(x["actual_pnl"])-x["expected_stop_loss"]>0

def test_stop_trace_records_first_quote_and_gap_without_changing_exit():
    src=Path("mt5/XAUUSD_Hybrid_Research.mq5").read_text()
    for term in ("EXECUTION_TRACE","first_exit_quote=","loss_overshoot=",
                 "intended_stop_pnl=","entry_stop_estimate=",
                 "tick_gap_seconds=","lastObservedTickAt"):
        assert term in src
    assert 'CloseVirtual(b,label,price,"STOP (first available quote)")' in src
    assert "double change=Pnl(b,price);" in src
    assert "b.lastObservedTickAt=TimeCurrent();" in src
    stripped=re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"',"",src)
    assert not re.search(r'\b(OrderSend|OrderSendAsync|CTrade|MqlTradeRequest)\b',stripped)

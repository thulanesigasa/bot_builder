"""Static safeguards for the XAUUSD virtual-position research EA.

These tests do not replace compilation in MetaEditor or MT5 Strategy Tester.
"""
from pathlib import Path
import re

SOURCE = Path("mt5/XAUUSD_Hybrid_Research.mq5")

def test_research_ea_exists_with_required_timeframes():
    source = SOURCE.read_text(encoding="utf-8")
    assert "#property strict" in source
    for token in ("PERIOD_H1", "PERIOD_M15", "PERIOD_M5",
                  "iMA(", "iRSI(", "iATR(", "CopyBuffer(", "CopyRates("):
        assert token in source

def test_no_order_submission_or_trade_library():
    code=SOURCE.read_text(encoding="utf-8")
    code=re.sub(r"//[^\n]*|/\*[\s\S]*?\*/|\"(?:\\.|[^\"\\])*\"", "", code)
    forbidden=[r"\bOrderSend\s*\(",r"\bOrderSendAsync\s*\(",
               r"\bCTrade\b",r"\bMqlTradeRequest\b",
               r"\bPositionOpen\s*\(",r"\bBuy\s*\(",r"\bSell\s*\("]
    assert not any(re.search(p,code) for p in forbidden)

def test_two_virtual_books_are_separate():
    code=SOURCE.read_text(encoding="utf-8")
    assert "VirtualBook baseline,recovery,adaptive,theoretical,weekendFlat;" in code
    assert 'OpenVirtual(baseline,"BASELINE"' in code
    assert 'OpenVirtual(recovery,"RECOVERY_1_5"' in code
    assert "MathPow(InpRecoveryMultiplier,b.recoveryLosses)" in code

def test_minimum_lot_cannot_override_risk_budget():
    code=SOURCE.read_text(encoding="utf-8")
    assert "lots<minLot || perLotLoss*lots>budget+1e-8" in code
    assert "LOT_INFEASIBLE" in code
    assert "InpHypotheticalUSD!=50.0" in code
    assert "InpRecoveryMultiplier>1.5" in code
    assert "InpMaxRecoveryIncreases>3" in code

def test_uses_executable_side_of_spread_and_daily_lock():
    code=SOURCE.read_text(encoding="utf-8")
    assert "tick.bid:tick.ask" in code
    assert "tick.ask:tick.bid" in code
    assert 'Audit(label,"RISK_LOCK"' in code

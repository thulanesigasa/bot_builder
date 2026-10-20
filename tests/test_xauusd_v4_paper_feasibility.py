from pathlib import Path
import re

def test_two_adaptive_paper_books():
    s=Path("mt5/XAUUSD_Hybrid_Research.mq5").read_text()
    assert "VirtualBook baseline,recovery,adaptive,theoretical;" in s
    assert 'OpenAdaptiveBook(adaptive,"ADAPTIVE"' in s
    assert 'OpenAdaptiveBook(theoretical,"THEORETICAL"' in s
    assert "int byRisk=" in s and "int byMargin=" in s
    assert "MathMin(byRisk,byMargin)" in s
    assert "XAU_V4_COMPARISON" in s
    assert "NO_FEASIBLE_LEG" in s
    clean=re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"',"",s)
    assert not re.search(r'\b(OrderSend|OrderSendAsync|CTrade|MqlTradeRequest)\b',clean)

def test_baseline_guards_still_present():
    s=Path("mt5/XAUUSD_Hybrid_Research.mq5").read_text()
    assert 'label=="ADAPTIVE" || label=="THEORETICAL"' in s
    assert "LOT_INFEASIBLE" in s
    assert "InpHypotheticalUSD!=50.0" in s

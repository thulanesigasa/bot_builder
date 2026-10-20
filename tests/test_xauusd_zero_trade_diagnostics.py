from pathlib import Path
def test_gold_diagnostics_present():
    source=Path("mt5/XAUUSD_Hybrid_Research.mq5").read_text()
    for text in ("XAU_DIAG SYMBOL=", "XAU_DIAG SUMMARY", "signalsGenerated++",
                 "spreadBlocks++", "noSignalBars++",
                 "baseline_virtual_opens=", "recovery_virtual_opens=",
                 "LOT_INFEASIBLE"):
        assert text in source
def test_research_keeps_no_order_submission():
    import re
    source=Path("mt5/XAUUSD_Hybrid_Research.mq5").read_text()
    stripped=re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"',"",source)
    assert not re.search(r'\b(OrderSend|OrderSendAsync|CTrade)\s*\(',stripped)

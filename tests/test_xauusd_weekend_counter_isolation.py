from pathlib import Path
import re

def test_weekend_clip_counter_isolated():
    s=Path("mt5/XAUUSD_Hybrid_Research.mq5").read_text()
    assert 'if(label=="WEEKEND_FLAT") weekendFlatClipped++;' in s
    assert "else adaptiveClippedOpens++;" in s
    assert "weekend_opens=%I64d weekend_clipped=%I64d" in s
    assert "weekendFlatOpens,weekendFlatClipped,weekendFlatCloses" in s
    clean=re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"',"",s)
    assert not re.search(r'\b(OrderSend|OrderSendAsync|CTrade|MqlTradeRequest)\b',clean)

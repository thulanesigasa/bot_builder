from pathlib import Path
import re

def test_friday_flat_is_independent_virtual_variant():
    s=Path("mt5/XAUUSD_Hybrid_Research.mq5").read_text()
    assert "VirtualBook baseline,recovery,adaptive,theoretical,weekendFlat;" in s
    assert "InpFridayFlatHourServer=20" in s
    assert "weekendFlatStage" in s
    assert "WeekendEntryBlocked(TimeCurrent())" in s
    assert "FlattenWeekendControl(t);" in s
    assert 'OpenAdaptiveBook(weekendFlat,"WEEKEND_FLAT"' in s
    assert "XAU_WEEKEND_COMPARE" in s
    assert "first_tick_after_cutoff=1" in s
    assert 'CloseVirtual(weekendFlat,"WEEKEND_FLAT",quote,"POLICY_FLAT_AT_AVAILABLE_TICK")' in s
    assert "weekendFlatCloses++" in s
    cleaned=re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"',"",s)
    assert not re.search(r'\b(OrderSend|OrderSendAsync|CTrade|MqlTradeRequest)\b',cleaned)

def test_policy_checks_day_and_hour_without_future_lookahead():
    s=Path("mt5/XAUUSD_Hybrid_Research.mq5").read_text()
    assert "d.day_of_week==6 || d.day_of_week==0" in s
    assert "d.day_of_week==5 && d.hour>=InpFridayFlatHourServer" in s
    assert "InpFridayFlatHourServer<0||InpFridayFlatHourServer>23" in s

from research.xauusd_adaptive_progression import AdaptiveState, allowable_positions, finish_cycle, evaluate_basket
from pathlib import Path
import re

def test_one_step_after_each_closed_cycle():
    s=AdaptiveState()
    assert allowable_positions(s)==7
    finish_cycle(s,1)
    assert allowable_positions(s)==8
    finish_cycle(s,1)
    assert allowable_positions(s)==9
    finish_cycle(s,-1)
    assert allowable_positions(s)==8
    finish_cycle(s,-1)
    assert allowable_positions(s)==7
    finish_cycle(s,-1)
    assert allowable_positions(s)==4
    finish_cycle(s,-1)
    assert allowable_positions(s)==3
    finish_cycle(s,-1)
    assert allowable_positions(s)==1

def test_stress_floor_and_margin_reject():
    s=AdaptiveState()
    assert not evaluate_basket(s,6.0,50.0,2.0)["permitted"]  # 7 x $6 > $35
    assert not evaluate_basket(s,1.0,5.0,2.0)["permitted"]
    assert evaluate_basket(s,1.0,50.0,2.0)["permitted"]
    finish_cycle(s,-36)
    assert s.halted is True
    assert allowable_positions(s)==0

def test_ea_has_three_virtual_books_and_no_orders():
    code=Path("mt5/XAUUSD_Hybrid_Research.mq5").read_text()
    assert "VirtualBook baseline,recovery,adaptive;" in code
    assert 'OpenAdaptive(direction,atr,t)' in code
    assert 'label=="ADAPTIVE"' in code
    assert "OrderCalcMargin(" in code  # estimating paper feasibility, NOT placing an order
    assert "OPEN_VIRTUAL_BASKET" in code
    clean=re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"',"",code)
    assert not re.search(r'\b(OrderSend|OrderSendAsync|CTrade|MqlTradeRequest)\b',clean)

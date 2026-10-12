"""Conservative scientific diagnostics must not authorize confirmation."""
import json
import sqlite3
from pathlib import Path
import pytest
from tools.pilot_variability_diagnostics import analyze

def test_missing_pilot_evidence_fails_closed(tmp_path):
    with pytest.raises(ValueError,match="Missing pilot artifact"):
        analyze(str(tmp_path))

def test_corrupt_strict_observation_fails_closed(tmp_path):
    (tmp_path/"session_1.db").touch()
    (tmp_path/"session_1_economics.json").write_text("[]",encoding="utf-8")
    with pytest.raises(Exception):
        analyze(str(tmp_path))

def test_pilot_analysis_declares_no_confirmation():
    source=Path("tools/pilot_variability_diagnostics.py").read_text()
    assert '"confirmation_ready":False' in source
    assert "NOT_ESTIMABLE" in source

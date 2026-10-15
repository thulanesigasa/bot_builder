import json
from pathlib import Path
import pytest
from tools.reconcile_scheduled_calibration import reconcile_ledger


def test_historical_calibration_is_incomplete_and_not_confirmatory():
    result = reconcile_ledger("reports/calibration_20261013_14_run_ledger.json")
    assert result["scheduled_attempts_observed"] == 4
    assert result["accepted_sessions"] == 1
    assert result["missing_accepted_slots"] == [1, 2, 3, 4, 5, 7, 8]
    assert result["complete"] is False
    assert result["confirmation_authorized"] is False


def test_duplicate_accepted_slot_cannot_be_hidden(tmp_path):
    source = json.loads(Path("reports/calibration_20261013_14_run_ledger.json").read_text())
    existing = next(x for x in source["observed_workflow_runs"] if x.get("accepted_slot") == 6)
    source["observed_workflow_runs"].append({**existing, "run_id": 999999999})
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(source))
    with pytest.raises(ValueError, match="DUPLICATE"):
        reconcile_ledger(path)


def test_expired_cron_is_retired():
    workflow = Path(".github/workflows/separated-calibration.yml").read_text()
    assert "workflow_dispatch:" in workflow
    assert "    - cron:" not in workflow
    assert "github.event_name == 'schedule'" in workflow

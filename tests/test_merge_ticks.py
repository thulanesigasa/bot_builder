"""Unit tests for merge_ticks.py ensuring deduplication, price integrity, and gap detection."""
import os
import json
import pytest
import pandas as pd
from merge_ticks import merge_symbol_ticks


def test_merge_new_ticks_appends_and_deduplicates(tmp_path):
    # Setup temporary data folder
    data_dir = str(tmp_path)
    incoming_csv = os.path.join(data_dir, "R_TEST_ticks.csv")
    master_csv = os.path.join(data_dir, "R_TEST_master.csv")

    # Initial incoming batch
    df1 = pd.DataFrame({
        "epoch": [1000, 1002, 1004],
        "price": [100.0, 100.5, 101.0]
    })
    df1.to_csv(incoming_csv, index=False)

    stats1 = merge_symbol_ticks(symbol="R_TEST", data_dir=data_dir)
    assert stats1["total_master_ticks"] == 3
    assert stats1["new_ticks_added"] == 3
    assert os.path.exists(master_csv)

    # Second batch with 1 overlap and 2 new ticks
    df2 = pd.DataFrame({
        "epoch": [1004, 1006, 1008],
        "price": [101.0, 101.5, 102.0]
    })
    df2.to_csv(incoming_csv, index=False)

    stats2 = merge_symbol_ticks(symbol="R_TEST", data_dir=data_dir)
    assert stats2["total_master_ticks"] == 5
    assert stats2["new_ticks_added"] == 2
    assert stats2["previous_master_ticks"] == 3

    # Verify content of master
    master_df = pd.read_csv(master_csv)
    assert list(master_df["epoch"]) == [1000, 1002, 1004, 1006, 1008]
    assert list(master_df["price"]) == [100.0, 100.5, 101.0, 101.5, 102.0]


def test_merge_conflicting_price_raises_error(tmp_path):
    data_dir = str(tmp_path)
    incoming_csv = os.path.join(data_dir, "R_TEST_ticks.csv")

    # Initial master batch
    df1 = pd.DataFrame({
        "epoch": [1000, 1002],
        "price": [100.0, 100.5]
    })
    df1.to_csv(incoming_csv, index=False)
    merge_symbol_ticks(symbol="R_TEST", data_dir=data_dir)

    # Conflicting price on epoch 1002
    df2 = pd.DataFrame({
        "epoch": [1002, 1004],
        "price": [999.99, 101.0]  # Conflict: was 100.5, now 999.99
    })
    df2.to_csv(incoming_csv, index=False)

    with pytest.raises(ValueError, match="price contradiction"):
        merge_symbol_ticks(symbol="R_TEST", data_dir=data_dir)


def test_merge_gap_detection(tmp_path):
    data_dir = str(tmp_path)
    incoming_csv = os.path.join(data_dir, "R_TEST_ticks.csv")

    # Series with a 30-second gap between 1004 and 1034
    df = pd.DataFrame({
        "epoch": [1000, 1002, 1004, 1034, 1036],
        "price": [100.0, 100.5, 101.0, 101.5, 102.0]
    })
    df.to_csv(incoming_csv, index=False)

    stats = merge_symbol_ticks(symbol="R_TEST", data_dir=data_dir)
    assert stats["gaps_over_10s_count"] == 1
    assert stats["max_gap_seconds"] == 30.0

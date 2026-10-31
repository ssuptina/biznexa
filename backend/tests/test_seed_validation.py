import pytest
from scripts.seed_synthetic import DATA_DIR, EXPECTED_COUNTS, TABLES, key_tuple, read_data


def source_data():
    if not (DATA_DIR / "customers.csv").exists():
        pytest.skip("Optional local CSV package is absent; Supabase is the runtime source.")
    return read_data()


def test_synthetic_source_counts_and_keys_match_declared_contract():
    data = source_data()
    for table, expected_count in EXPECTED_COUNTS.items():
        assert len(data[table]) == expected_count, table
        keys = [key_tuple(row, TABLES[table]) for row in data[table]]
        assert len(keys) == len(set(keys)), table


def test_inventory_source_invariants_hold():
    data = source_data()
    assert all(row["reserved_qty"] <= row["on_hand_qty"] for row in data["inventory_snapshots"])
    assert all(row["available_qty"] == row["on_hand_qty"] - row["reserved_qty"] for row in data["inventory_snapshots"])

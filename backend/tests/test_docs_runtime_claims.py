"""Guard docs/tests against claiming station-level runtime observations."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_scrape_cadence_documents_aggregate_price_observations():
    doc = (ROOT / "SCRAPE_CADENCE.md").read_text(encoding="utf-8")

    assert "aggregate docs/day" in doc
    assert "~1,500 rows/day" not in doc
    assert "100-200 rows" not in doc


def test_tracker_cadence_tests_do_not_simulate_station_level_runtime_writes():
    tests = (ROOT / "backend" / "tests" / "test_tracker_cadence.py").read_text(encoding="utf-8")

    assert "tracker.silent_scrape" in tests
    assert '"station_id":' not in tests
    assert "updates stations registry" not in tests

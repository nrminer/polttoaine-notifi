"""Smoke-check dashboard component imports in App.js."""
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_dashboard_components_are_rendered_or_not_imported():
    app_js = (ROOT / "frontend" / "src" / "App.js").read_text(encoding="utf-8")
    watched_components = {
        "RecommendationCard",
        "WeeklyCycleCard",
        "PriceDrivers",
        "SourceBreakdown",
    }

    for component in watched_components:
        imported = re.search(rf"\bimport\b[^\n]*\b{component}\b", app_js) is not None
        rendered = f"<{component}" in app_js
        assert rendered or not imported, f"{component} is imported in App.js but not rendered"

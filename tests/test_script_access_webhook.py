import importlib.util
from pathlib import Path


def _load_webhook():
    path = Path(__file__).parents[1] / "api" / "stripe-webhook.py"
    spec = importlib.util.spec_from_file_location("stripe_webhook", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_extracts_exact_tradingview_username():
    webhook = _load_webhook()
    session = {
        "custom_fields": [{
            "label": {"custom": "TradingView username (exact)"},
            "type": "text",
            "text": {"value": "  ChartRider_7  "},
        }]
    }
    assert webhook._extract_tradingview_username(session) == "ChartRider_7"


def test_ignores_unrelated_checkout_field():
    webhook = _load_webhook()
    session = {
        "custom_fields": [{
            "label": {"custom": "Company"},
            "type": "text",
            "text": {"value": "OptionRiders"},
        }]
    }
    assert webhook._extract_tradingview_username(session) == ""

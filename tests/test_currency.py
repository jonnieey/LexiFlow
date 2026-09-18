import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from lexiflow.utils import currency
from lexiflow.utils.currency import (
    convert,
    currency_symbol,
    display_currency_code,
    fetch_rate,
    format_money,
    get_rate,
)


def _config(**kwargs):
    defaults = {
        "display_currency": "USD",
        "conversion_rate": 0.0,
        "currency_segment": "",
        "currency_receive_country": "",
        "currency_send_country": "us",
        "invoice_currency": "USD",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_currency_symbol():
    assert currency_symbol("USD") == "$"
    assert currency_symbol("KES") == "KSh"
    assert currency_symbol("xyz") == "XYZ"
    assert currency_symbol("") == "$"


def test_convert():
    assert convert(10, 128.36) == pytest.approx(1283.6)
    assert convert(None, 2) == 0.0


def test_format_money_usd():
    assert format_money(12.5, _config()) == "$12.50"


def test_format_money_converted():
    config = _config(display_currency="KES")
    assert format_money(10, config, rate=128.36) == "1,283.60 KES"


def test_format_money_manual_rate():
    config = _config(display_currency="KES", conversion_rate=100.0)
    assert format_money(2, config) == "200.00 KES"


def test_format_money_without_currency():
    assert format_money(12.5, _config(), show_currency=False) == "12.50"
    config = _config(display_currency="KES")
    assert (
        format_money(10, config, rate=128.36, show_currency=False)
        == "1,283.60"
    )


def test_display_currency_code():
    assert display_currency_code(_config()) == "USD"
    assert (
        display_currency_code(_config(display_currency="KES"), 128.36)
        == "KES"
    )
    # No rate available -> falls back to USD
    assert (
        display_currency_code(_config(display_currency="KES"), None) == "USD"
    )


def test_fetch_rate_usd_short_circuits():
    assert fetch_rate("USD") == 1.0


def test_fetch_rate_parses_effective_exchange_rate():
    payload = {"effectiveExchangeRate": "128.36003"}
    response = MagicMock()
    response.__enter__ = lambda self: self
    response.__exit__ = lambda self, *args: False
    response.read = lambda: json.dumps(payload).encode()
    with patch("urllib.request.urlopen", return_value=response) as mock_open:
        rate = fetch_rate("KES")
    assert rate == 128.36003
    called_url = mock_open.call_args[0][0].full_url
    assert "receiveCurrency=KES" in called_url
    assert "receiveCountryIso2=ke" in called_url
    assert "segmentName=ke_airtel" in called_url


def test_fetch_rate_returns_none_on_failure():
    with patch("urllib.request.urlopen", side_effect=OSError("boom")):
        assert fetch_rate("KES") is None


def test_get_rate_manual_override():
    currency._CACHE.clear()
    config = _config(display_currency="KES", conversion_rate=99.5)
    assert get_rate(config) == 99.5


def test_get_rate_usd():
    assert get_rate(_config()) == 1.0


def test_get_rate_caches_live_value():
    currency._CACHE.clear()
    config = _config(display_currency="KES")
    with patch(
        "lexiflow.utils.currency.fetch_rate", return_value=128.36
    ) as mock_fetch:
        assert get_rate(config) == 128.36
        # Second call should be served from cache without fetching again
        assert get_rate(config) == 128.36
    mock_fetch.assert_called_once()

import json
import logging
import time
import urllib.parse
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

PRICING_URL = "https://app.sendwave.com/v2/pricing-public"

CURRENCY_SYMBOLS = {
    "USD": "$",
    "KES": "KSh",
    "UGX": "USh",
    "TZS": "TSh",
    "GHS": "GH₵",
    "NGN": "₦",
    "XAF": "FCFA",
    "XOF": "CFA",
    "BDT": "৳",
    "PKR": "₨",
    "LKR": "₨",
}

# Currency code -> (segmentName, receiveCountryIso2) for known corridors.
CORRIDORS = {
    "KES": ("ke_airtel", "ke"),
}

_CACHE: dict = {}
_CACHE_TTL = 600.0  # seconds


def currency_symbol(code: str) -> str:
    """Return a display symbol for a currency code."""
    if not code:
        return "$"
    return CURRENCY_SYMBOLS.get(code.upper(), code.upper())


def convert(usd: float, rate: float) -> float:
    """Convert a USD amount using the given rate."""
    if usd is None:
        return 0.0
    return float(usd) * float(rate)


def _corridor(currency: str, segment: str, receive_country: str):
    code = (currency or "").upper()
    if not code:
        return segment, receive_country
    default_segment, default_country = CORRIDORS.get(code, ("", ""))
    segment = segment or default_segment
    receive_country = receive_country or default_country
    if not receive_country:
        receive_country = code[:2].lower()
    return segment, receive_country


def fetch_rate(
    currency: str,
    segment_name: str = "",
    receive_country: str = "",
    send_country: str = "us",
    timeout: float = 5.0,
) -> Optional[float]:
    """Fetch the effective USD->currency exchange rate from Sendwave.

    Returns the effectiveExchangeRate as a float, or None on any failure.
    """
    code = (currency or "").upper()
    if not code or code == "USD":
        return 1.0

    segment, receive = _corridor(code, segment_name, receive_country)
    if not receive:
        logger.warning("No receive country for currency %s", code)
        return None

    params = {
        "amountType": "SEND",
        "receiveCurrency": code,
        "amount": "1",
        "sendCurrency": "USD",
        "sendCountryIso2": send_country or "us",
        "receiveCountryIso2": receive,
    }
    if segment:
        params["segmentName"] = segment

    url = f"{PRICING_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={
            "accept": "application/json, text/plain, */*",
            "user-agent": "Mozilla/5.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.load(response)
        rate = data.get("effectiveExchangeRate")
        return float(rate) if rate is not None else None
    except Exception as e:
        logger.warning("Failed to fetch rate for %s: %s", code, e)
        return None


def get_rate(config, force: bool = False) -> Optional[float]:
    """Resolve the conversion rate from config, with caching and fallback.

    Priority: manual config.conversion_rate, then a cached live rate,
    then a fresh live fetch.
    """
    if config is None:
        return None

    if getattr(config, "conversion_rate", 0.0) > 0:
        return float(config.conversion_rate)

    code = (getattr(config, "display_currency", "USD") or "").upper()
    if not code or code == "USD":
        return 1.0

    segment = getattr(config, "currency_segment", "") or ""
    receive = getattr(config, "currency_receive_country", "") or ""
    send = getattr(config, "currency_send_country", "us") or "us"
    cache_key = (code, segment, receive, send)

    now = time.time()
    cached = _CACHE.get(cache_key)
    if not force and cached is not None and (now - cached[1]) < _CACHE_TTL:
        return cached[0]

    rate = fetch_rate(
        code,
        segment_name=segment,
        receive_country=receive,
        send_country=send,
    )
    if rate is not None:
        _CACHE[cache_key] = (rate, now)
    return rate


def display_currency_code(config, rate: Optional[float] = None) -> str:
    """Return the currency code actually used for display.

    Falls back to USD when the requested currency has no available rate.
    """
    if config is None:
        return "USD"
    code = (getattr(config, "display_currency", "USD") or "USD").upper()
    if code == "USD" or rate is None:
        return "USD"
    return code


def format_money(
    usd: float,
    config,
    *,
    currency: Optional[str] = None,
    rate: Optional[float] = None,
    convert_rate: bool = True,
    show_currency: bool = True,
) -> str:
    """Format a USD amount for display.

    With ``show_currency`` the result includes the currency, e.g. "$123.45"
    or "15,852.34 KES". When False only the number is returned, so the
    currency can be shown once in a table header instead of every cell.
    """
    code = currency or (getattr(config, "display_currency", "USD") or "USD")
    code = code.upper()

    if code == "USD":
        value = float(usd or 0)
        return f"${value:.2f}" if show_currency else f"{value:,.2f}"

    if convert_rate:
        resolved = rate if rate is not None else get_rate(config)
        if resolved is None:
            value = float(usd or 0)
            return f"${value:.2f}" if show_currency else f"{value:,.2f}"
        value = convert(usd, resolved)
    else:
        value = float(usd or 0)

    if not show_currency:
        return f"{value:,.2f}"
    return f"{value:,.2f} {code}"

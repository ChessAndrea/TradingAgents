from yfinance.exceptions import YFRateLimitError

from tradingagents.dataflows import y_finance


def test_get_yfin_data_returns_message_on_rate_limit(monkeypatch):
    def raise_rate_limit(func):
        raise YFRateLimitError()

    monkeypatch.setattr(y_finance, "yf_retry", raise_rate_limit)

    result = y_finance.get_YFin_data_online(
        "510210.SS",
        "2026-05-01",
        "2026-05-19",
    )

    assert "Yahoo Finance rate limit reached" in result
    assert "510210.SS" in result


def test_get_indicators_returns_message_on_rate_limit(monkeypatch):
    def raise_rate_limit(*args, **kwargs):
        raise YFRateLimitError()

    monkeypatch.setattr(y_finance, "_get_stock_stats_bulk", raise_rate_limit)

    result = y_finance.get_stock_stats_indicators_window(
        "510210.SS",
        "rsi",
        "2026-05-19",
        30,
    )

    assert "Yahoo Finance rate limit reached" in result
    assert "510210.SS" in result

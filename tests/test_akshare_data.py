import pandas as pd

from tradingagents.dataflows import akshare_data
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.interface import route_to_vendor


def test_normalise_cn_symbol():
    assert akshare_data._normalise_cn_symbol("510210.SS") == "510210"
    assert akshare_data._normalise_cn_symbol("sh510210") == "510210"
    assert akshare_data._normalise_cn_symbol("510210") == "510210"


def test_akshare_proxy_env_bypasses_and_restores_proxy(monkeypatch):
    import requests

    original_merge = requests.sessions.Session.merge_environment_settings
    monkeypatch.setenv("HTTPS_PROXY", "http://broken-proxy:8080")
    monkeypatch.setenv("http_proxy", "http://lower-proxy:8080")

    with akshare_data._akshare_proxy_env():
        assert "HTTPS_PROXY" not in __import__("os").environ
        assert "http_proxy" not in __import__("os").environ
        assert requests.sessions.Session.merge_environment_settings is not original_merge

    assert __import__("os").environ["HTTPS_PROXY"] == "http://broken-proxy:8080"
    assert __import__("os").environ["http_proxy"] == "http://lower-proxy:8080"
    assert requests.sessions.Session.merge_environment_settings is original_merge


def test_akshare_proxy_env_can_preserve_proxy(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_AKSHARE_USE_PROXY", "true")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy:8080")

    with akshare_data._akshare_proxy_env():
        assert __import__("os").environ["HTTPS_PROXY"] == "http://proxy:8080"


def test_get_stock_data_formats_akshare_frame(monkeypatch):
    frame = pd.DataFrame(
        {
            "日期": ["2026-05-18", "2026-05-19"],
            "开盘": [1.035, 1.035],
            "收盘": [1.037, 1.044],
            "最高": [1.039, 1.045],
            "最低": [1.030, 1.031],
            "成交量": [3949871, 5165435],
            "成交额": [408647071.0, 535913174.0],
        }
    )

    class FakeAkshare:
        @staticmethod
        def fund_etf_hist_em(**kwargs):
            assert kwargs["symbol"] == "510210"
            return frame

    monkeypatch.setitem(__import__("sys").modules, "akshare", FakeAkshare)

    result = akshare_data.get_stock_data("510210.SS", "2026-05-18", "2026-05-19")

    assert "# AkShare ETF data for 510210.SS" in result
    assert "Date,Open,Close,High,Low,Volume" in result
    assert "2026-05-19" in result


def test_get_stock_data_falls_back_to_sina(monkeypatch):
    frame = pd.DataFrame(
        {
            "date": ["2026-05-18"],
            "open": [1.035],
            "high": [1.039],
            "low": [1.030],
            "close": [1.037],
            "volume": [394987060],
            "amount": [408647071],
        }
    )

    class FakeAkshare:
        @staticmethod
        def fund_etf_hist_em(**kwargs):
            raise ConnectionError("eastmoney failed")

        @staticmethod
        def fund_etf_hist_sina(**kwargs):
            assert kwargs["symbol"] == "sh510210"
            return frame

    monkeypatch.setitem(__import__("sys").modules, "akshare", FakeAkshare)

    result = akshare_data.get_stock_data("510210.SS", "2026-05-18", "2026-05-19")

    assert "# AkShare ETF data for 510210.SS" in result
    assert "2026-05-18" in result


def test_route_to_akshare_stock(monkeypatch):
    monkeypatch.setattr(akshare_data, "get_stock_data", lambda *args: "akshare-stock")
    from tradingagents.dataflows import interface

    monkeypatch.setitem(interface.VENDOR_METHODS["get_stock_data"], "akshare", akshare_data.get_stock_data)
    set_config({"data_vendors": {"core_stock_apis": "akshare"}})

    assert route_to_vendor("get_stock_data", "510210.SS", "2026-05-18", "2026-05-19") == "akshare-stock"

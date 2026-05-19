from datetime import datetime
from contextlib import contextmanager
import os
from typing import Annotated

import pandas as pd

_PROXY_ENV_VARS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


@contextmanager
def _akshare_proxy_env():
    """Bypass shell proxies for AkShare's China-market data requests by default."""
    if os.environ.get("TRADINGAGENTS_AKSHARE_USE_PROXY", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        yield
        return

    import requests

    saved = {key: os.environ.get(key) for key in _PROXY_ENV_VARS}
    original_merge_environment_settings = requests.sessions.Session.merge_environment_settings

    def merge_without_proxies(self, url, proxies, stream, verify, cert):
        settings = original_merge_environment_settings(self, url, proxies, stream, verify, cert)
        settings["proxies"] = {}
        return settings

    for key in _PROXY_ENV_VARS:
        os.environ.pop(key, None)
    requests.sessions.Session.merge_environment_settings = merge_without_proxies
    try:
        yield
    finally:
        requests.sessions.Session.merge_environment_settings = original_merge_environment_settings
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _normalise_cn_symbol(symbol: str) -> str:
    """Convert exchange-qualified tickers like 510210.SS to AkShare's 6-digit code."""
    cleaned = symbol.strip().upper()
    for suffix in (".SS", ".SH", ".SZ"):
        if cleaned.endswith(suffix):
            return cleaned[: -len(suffix)]
    if cleaned.startswith(("SH", "SZ")) and len(cleaned) == 8:
        return cleaned[2:]
    return cleaned


def _sina_symbol(symbol: str) -> str:
    cleaned = symbol.strip().upper()
    code = _normalise_cn_symbol(cleaned)
    if cleaned.endswith(".SZ") or cleaned.startswith("SZ"):
        return f"sz{code}"
    return f"sh{code}"


def _normalise_akshare_frame(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])

    data = raw.rename(
        columns={
            "日期": "Date",
            "开盘": "Open",
            "最高": "High",
            "最低": "Low",
            "收盘": "Close",
            "成交量": "Volume",
            "成交额": "Amount",
            "涨跌幅": "Pct Change",
            "换手率": "Turnover",
            "date": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
            "amount": "Amount",
        }
    )
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    for col in ["Open", "High", "Low", "Close", "Volume", "Amount", "Pct Change", "Turnover"]:
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data.dropna(subset=["Date", "Close"])
    return data.sort_values("Date")


def _fetch_etf_daily(symbol: str, start_date: str, end_date: str | None = None) -> pd.DataFrame:
    try:
        import akshare as ak
    except ImportError as exc:
        raise RuntimeError(
            "AkShare is not installed. Install it with `pip install akshare` "
            "or choose another data vendor."
        ) from exc

    code = _normalise_cn_symbol(symbol)
    start = datetime.strptime(start_date, "%Y-%m-%d").strftime("%Y%m%d")
    end = (
        datetime.strptime(end_date, "%Y-%m-%d").strftime("%Y%m%d")
        if end_date
        else datetime.now().strftime("%Y%m%d")
    )
    with _akshare_proxy_env():
        try:
            raw = ak.fund_etf_hist_em(
                symbol=code,
                period="daily",
                start_date=start,
                end_date=end,
                adjust="",
            )
            data = _normalise_akshare_frame(raw)
        except Exception:
            raw = ak.fund_etf_hist_sina(symbol=_sina_symbol(symbol))
            data = _normalise_akshare_frame(raw)

    if data.empty:
        return data

    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date) if end_date else pd.Timestamp.today()
    return data[(data["Date"] >= start_dt) & (data["Date"] <= end_dt)].sort_values("Date")


def get_stock_data(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Retrieve China ETF OHLCV data from AkShare."""
    data = _fetch_etf_daily(symbol, start_date, end_date)
    if data.empty:
        return f"No AkShare ETF data found for symbol '{symbol}' between {start_date} and {end_date}"

    output = data.copy()
    output["Date"] = output["Date"].dt.strftime("%Y-%m-%d")
    for col in ["Open", "High", "Low", "Close"]:
        output[col] = output[col].round(3)

    header = f"# AkShare ETF data for {symbol.upper()} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(output)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + output.to_csv(index=False)


def get_indicator(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to calculate"],
    curr_date: Annotated[str, "current date in YYYY-mm-dd format"],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:
    """Calculate stockstats-compatible indicators from AkShare ETF OHLCV data."""
    from dateutil.relativedelta import relativedelta
    from stockstats import wrap

    descriptions = {
        "close_50_sma": "50 SMA: A medium-term trend indicator.",
        "close_200_sma": "200 SMA: A long-term trend benchmark.",
        "close_10_ema": "10 EMA: A responsive short-term average.",
        "macd": "MACD: Computes momentum via differences of EMAs.",
        "macds": "MACD Signal: An EMA smoothing of the MACD line.",
        "macdh": "MACD Histogram: Shows the gap between the MACD line and its signal.",
        "rsi": "RSI: Measures momentum to flag overbought/oversold conditions.",
        "boll": "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands.",
        "boll_ub": "Bollinger Upper Band: Typically 2 standard deviations above the middle line.",
        "boll_lb": "Bollinger Lower Band: Typically 2 standard deviations below the middle line.",
        "atr": "ATR: Averages true range to measure volatility.",
        "vwma": "VWMA: A moving average weighted by volume.",
        "mfi": "MFI: Money Flow Index measures buying and selling pressure using price and volume.",
    }
    if indicator not in descriptions:
        raise ValueError(
            f"Indicator {indicator} is not supported. Please choose from: {list(descriptions.keys())}"
        )

    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before = curr_date_dt - relativedelta(days=look_back_days)
    fetch_start = (curr_date_dt - relativedelta(days=max(look_back_days + 260, 320))).strftime("%Y-%m-%d")
    data = _fetch_etf_daily(symbol, fetch_start, curr_date)
    if data.empty:
        return f"No AkShare ETF data found for symbol '{symbol}' through {curr_date}"

    df = data[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
    stats = wrap(df)
    stats["Date"] = stats["Date"].dt.strftime("%Y-%m-%d")
    stats[indicator]

    lines = []
    for _, row in stats.iterrows():
        row_date = datetime.strptime(row["Date"], "%Y-%m-%d")
        if before <= row_date <= curr_date_dt:
            value = row[indicator]
            lines.append(f"{row['Date']}: {'N/A' if pd.isna(value) else value}")

    return (
        f"## {indicator} values from {before.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
        + "\n".join(lines)
        + "\n\n"
        + descriptions[indicator]
    )

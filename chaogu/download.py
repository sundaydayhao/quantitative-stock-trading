from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


CSV_COLUMNS = ["timestamp", "symbol", "open", "high", "low", "close", "volume"]


def download_history(
    provider: str,
    symbol: str,
    start: str,
    end: str,
    out: str | Path,
    adjust: str = "qfq",
    period: str = "daily",
) -> dict[str, Any]:
    provider = provider.lower()
    if provider == "akshare":
        rows = _download_akshare(symbol=symbol, start=start, end=end, adjust=adjust, period=period)
    elif provider == "xtquant":
        rows = _download_xtquant(symbol=symbol, start=start, end=end, adjust=adjust, period=period)
    else:
        raise ValueError(f"unsupported data provider: {provider}")

    output = Path(out)
    _write_bars_csv(output, rows)
    return {
        "provider": provider,
        "symbol": symbol,
        "start": _date_yyyymmdd(start),
        "end": _date_yyyymmdd(end),
        "adjust": adjust,
        "period": period,
        "rows": len(rows),
        "output": str(output),
    }


def _download_akshare(symbol: str, start: str, end: str, adjust: str, period: str) -> list[dict[str, Any]]:
    try:
        import akshare as ak  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("akshare is not installed. Install it with: python3 -m pip install akshare") from exc

    ak_period = _akshare_period(period)
    ak_adjust = _akshare_adjust(adjust)
    df = ak.stock_zh_a_hist(
        symbol=_akshare_symbol(symbol),
        period=ak_period,
        start_date=_date_yyyymmdd(start),
        end_date=_date_yyyymmdd(end),
        adjust=ak_adjust,
    )

    rows: list[dict[str, Any]] = []
    for item in df.to_dict("records"):
        rows.append(
            {
                "timestamp": str(item["日期"]),
                "symbol": symbol,
                "open": float(item["开盘"]),
                "high": float(item["最高"]),
                "low": float(item["最低"]),
                "close": float(item["收盘"]),
                "volume": float(item["成交量"]) * 100.0,
            }
        )
    return rows


def _download_xtquant(symbol: str, start: str, end: str, adjust: str, period: str) -> list[dict[str, Any]]:
    try:
        from xtquant import xtdata  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "xtquant is not installed or not on PYTHONPATH. "
            "Download/configure xtquant from the Xuntou user center first."
        ) from exc

    xt_period = _xtquant_period(period)
    dividend_type = _xtquant_dividend_type(adjust)
    start_time = _date_yyyymmdd(start)
    end_time = _date_yyyymmdd(end)
    fields = ["open", "high", "low", "close", "volume"]

    xtdata.download_history_data(symbol, xt_period, start_time=start_time, end_time=end_time)
    data = xtdata.get_market_data(
        field_list=fields,
        stock_list=[symbol],
        period=xt_period,
        start_time=start_time,
        end_time=end_time,
        count=-1,
        dividend_type=dividend_type,
        fill_data=False,
    )

    close_frame = data["close"]
    rows: list[dict[str, Any]] = []
    for timestamp in list(close_frame.columns):
        rows.append(
            {
                "timestamp": _xtquant_timestamp(timestamp),
                "symbol": symbol,
                "open": _xtquant_value(data["open"], symbol, timestamp),
                "high": _xtquant_value(data["high"], symbol, timestamp),
                "low": _xtquant_value(data["low"], symbol, timestamp),
                "close": _xtquant_value(data["close"], symbol, timestamp),
                "volume": _xtquant_value(data["volume"], symbol, timestamp),
            }
        )
    return rows


def _write_bars_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    materialized = list(rows)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in materialized:
            writer.writerow({column: row[column] for column in CSV_COLUMNS})


def _akshare_symbol(symbol: str) -> str:
    value = symbol.strip().upper()
    if "." in value:
        return value.split(".", 1)[0]
    if value.startswith(("SH", "SZ", "BJ")):
        return value[2:]
    return value


def _akshare_period(period: str) -> str:
    normalized = period.lower()
    mapping = {"1d": "daily", "d": "daily", "day": "daily", "daily": "daily", "1w": "weekly", "weekly": "weekly"}
    if normalized in mapping:
        return mapping[normalized]
    if normalized in {"1m", "5m", "15m", "30m", "60m"}:
        raise ValueError("akshare stock_zh_a_hist only supports daily, weekly, and monthly periods")
    if normalized in {"1mon", "mon", "monthly"}:
        return "monthly"
    raise ValueError(f"unsupported akshare period: {period}")


def _akshare_adjust(adjust: str) -> str:
    normalized = adjust.lower()
    if normalized in {"", "none", "raw"}:
        return ""
    if normalized in {"qfq", "front"}:
        return "qfq"
    if normalized in {"hfq", "back"}:
        return "hfq"
    raise ValueError(f"unsupported akshare adjust: {adjust}")


def _xtquant_period(period: str) -> str:
    normalized = period.lower()
    mapping = {
        "d": "1d",
        "day": "1d",
        "daily": "1d",
        "1d": "1d",
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "1w": "1w",
        "weekly": "1w",
        "1mon": "1mon",
        "monthly": "1mon",
    }
    if normalized not in mapping:
        raise ValueError(f"unsupported xtquant period: {period}")
    return mapping[normalized]


def _xtquant_dividend_type(adjust: str) -> str:
    normalized = adjust.lower()
    if normalized in {"", "none", "raw"}:
        return "none"
    if normalized in {"qfq", "front"}:
        return "front"
    if normalized in {"hfq", "back"}:
        return "back"
    if normalized in {"front_ratio", "back_ratio"}:
        return normalized
    raise ValueError(f"unsupported xtquant adjust: {adjust}")


def _date_yyyymmdd(value: str) -> str:
    compact = value.strip().replace("-", "")
    if len(compact) != 8 or not compact.isdigit():
        raise ValueError(f"date must be YYYYMMDD or YYYY-MM-DD: {value}")
    datetime.strptime(compact, "%Y%m%d")
    return compact


def _xtquant_timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    text = str(value)
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    if len(text) >= 13 and text[:13].isdigit():
        return datetime.fromtimestamp(int(text[:13]) / 1000, tz=timezone.utc).date().isoformat()
    return text


def _xtquant_value(frame: Any, symbol: str, timestamp: Any) -> float:
    return float(frame.loc[symbol, timestamp])

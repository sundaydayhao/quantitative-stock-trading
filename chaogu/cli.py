from __future__ import annotations

import argparse
import json
from pathlib import Path

from .backtest import run_backtest
from .config import config_to_dict, load_config
from .download import download_history
from .paper import run_paper_once, watch_paper
from .screener import screen_stocks
from .webapp import run_server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="chaogu", description="Personal quantitative trading toolkit.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backtest = subparsers.add_parser("backtest", help="run a historical backtest")
    backtest.add_argument("--config", default="config.example.json", help="path to JSON config")
    backtest.add_argument("--out", default="runs/backtest", help="output directory")

    paper = subparsers.add_parser("paper", help="run paper execution on unprocessed CSV bars")
    paper.add_argument("--config", default="config.example.json", help="path to JSON config")
    paper.add_argument("--state", default="runs/paper_state.json", help="paper state file")
    paper.add_argument("--watch", action="store_true", help="poll market_data_csv forever")

    validate = subparsers.add_parser("validate", help="validate config and print normalized paths")
    validate.add_argument("--config", default="config.example.json", help="path to JSON config")

    download = subparsers.add_parser("download", help="download historical bars to chaogu CSV format")
    download.add_argument("--provider", choices=["akshare", "xtquant"], default="akshare", help="data provider")
    download.add_argument("--symbol", required=True, help="stock code, for example 000001.SZ or 600000.SH")
    download.add_argument("--start", required=True, help="start date, YYYYMMDD or YYYY-MM-DD")
    download.add_argument("--end", required=True, help="end date, YYYYMMDD or YYYY-MM-DD")
    download.add_argument("--out", required=True, help="output CSV path")
    download.add_argument("--adjust", default="qfq", help="adjustment: none/raw, qfq/front, hfq/back")
    download.add_argument("--period", default="daily", help="bar period, default daily")

    web = subparsers.add_parser("web", help="start the local HTML control console")
    web.add_argument("--host", default="127.0.0.1", help="bind host")
    web.add_argument("--port", type=int, default=8765, help="bind port")

    screen = subparsers.add_parser("screen", help="screen stocks from local chaogu CSV files")
    screen.add_argument("--pattern", default="data/*.csv", help="glob pattern for local CSV files")
    screen.add_argument("--lookback", type=int, default=20, help="return lookback bars")
    screen.add_argument("--short-window", type=int, default=5, help="short moving average window")
    screen.add_argument("--long-window", type=int, default=20, help="long moving average window")
    screen.add_argument("--min-return-pct", type=float, default=0.0, help="minimum lookback return, e.g. 0.05")
    screen.add_argument("--min-avg-volume", type=float, default=0.0, help="minimum average volume")
    screen.add_argument("--no-uptrend", action="store_true", help="do not require short MA > long MA")
    screen.add_argument("--limit", type=int, default=50, help="maximum candidates")

    args = parser.parse_args(argv)

    if args.command == "backtest":
        cfg = load_config(args.config)
        result = run_backtest(cfg, Path(args.out))
        print(json.dumps(result.summary, ensure_ascii=False, indent=2))
        return 0

    if args.command == "paper":
        cfg = load_config(args.config)
        if args.watch:
            watch_paper(cfg, Path(args.state))
            return 0
        report = run_paper_once(cfg, Path(args.state))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate":
        cfg = load_config(args.config)
        print(json.dumps(config_to_dict(cfg), ensure_ascii=False, indent=2))
        return 0

    if args.command == "download":
        report = download_history(
            provider=args.provider,
            symbol=args.symbol,
            start=args.start,
            end=args.end,
            out=Path(args.out),
            adjust=args.adjust,
            period=args.period,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "web":
        run_server(args.host, args.port)
        return 0

    if args.command == "screen":
        files = sorted(Path(".").glob(args.pattern))
        result = screen_stocks(
            files=files,
            lookback=args.lookback,
            short_window=args.short_window,
            long_window=args.long_window,
            min_return_pct=args.min_return_pct,
            min_avg_volume=args.min_avg_volume,
            require_uptrend=not args.no_uptrend,
            limit=args.limit,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

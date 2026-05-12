from __future__ import annotations

import json
import os
import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from .backtest import run_backtest
from .config import config_to_dict, load_config
from .download import download_history
from .ledger import cash_ledger_from_fills
from .paper import run_paper_once
from .screener import screen_stocks


ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs"
DATA_DIR = ROOT / "data"
RUN_DIR = ROOT / "runs" / "web"
UI_PATH = ROOT / "ui" / "strategy-config.html"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Job:
    id: str
    kind: str
    status: str = "queued"
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    logs: list[str] = field(default_factory=list)
    stop_event: threading.Event = field(default_factory=threading.Event, repr=False)

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": self.result,
            "error": self.error,
            "logs": self.logs[-100:],
        }


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def start(self, kind: str, target: Callable[[Job], dict[str, Any] | None]) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind)
        with self._lock:
            self._jobs[job.id] = job

        thread = threading.Thread(target=self._run, args=(job, target), daemon=True)
        thread.start()
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)

    def stop(self, job_id: str) -> Job | None:
        job = self.get(job_id)
        if job is not None:
            job.stop_event.set()
            job.logs.append(f"{_now()} stop requested")
        return job

    def _run(self, job: Job, target: Callable[[Job], dict[str, Any] | None]) -> None:
        job.status = "running"
        job.started_at = _now()
        job.logs.append(f"{job.started_at} started {job.kind}")
        try:
            result = target(job)
            if job.stop_event.is_set() and job.status == "running":
                job.status = "stopped"
            elif job.status == "running":
                job.status = "completed"
            if result is not None:
                job.result = result
        except Exception as exc:  # noqa: BLE001 - errors are surfaced through the API.
            job.status = "failed"
            job.error = str(exc)
            job.logs.append(f"{_now()} failed: {exc}")
        finally:
            job.finished_at = _now()


JOBS = JobStore()


class LocalThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    try:
        server = LocalThreadingHTTPServer((host, port), ChaoguHandler)
    except OSError as exc:
        if exc.errno == 98:
            raise SystemExit(
                f"{host}:{port} is already in use. Open http://{host}:{port}/ if the server is already running, "
                f"or start with another port, for example: python3 -m chaogu web --port {port + 1}"
            ) from exc
        raise
    print(f"chaogu web console: http://{host}:{server.server_port}/")
    server.serve_forever()


class ChaoguHandler(BaseHTTPRequestHandler):
    server_version = "ChaoguWeb/0.1"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._send_file(UI_PATH, "text/html; charset=utf-8")
            return

        if parsed.path == "/api/health":
            self._send_json({"ok": True, "time": _now()})
            return

        if parsed.path == "/api/configs":
            self._send_json({"configs": _list_configs()})
            return

        if parsed.path == "/api/data-files":
            self._send_json({"files": _list_data_files()})
            return

        if parsed.path == "/api/jobs":
            self._send_json({"jobs": [job.public_dict() for job in JOBS.list()]})
            return

        match = re.fullmatch(r"/api/jobs/([a-f0-9]{12})", parsed.path)
        if match:
            job = JOBS.get(match.group(1))
            if job is None:
                self._send_error(HTTPStatus.NOT_FOUND, "job not found")
                return
            self._send_json({"job": job.public_dict()})
            return

        if parsed.path.startswith("/runs/"):
            self._send_run_file(parsed.path)
            return

        self._send_error(HTTPStatus.NOT_FOUND, "not found")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            payload = self._read_json()
            if parsed.path == "/api/configs/save":
                self._send_json(_api_save_config(payload))
                return

            if parsed.path == "/api/download":
                job = JOBS.start("download", lambda item: _job_download(item, payload))
                self._send_json({"job": job.public_dict()}, status=HTTPStatus.ACCEPTED)
                return

            if parsed.path == "/api/backtest":
                job = JOBS.start("backtest", lambda item: _job_backtest(item, payload))
                self._send_json({"job": job.public_dict()}, status=HTTPStatus.ACCEPTED)
                return

            if parsed.path == "/api/screen":
                job = JOBS.start("screen", lambda item: _job_screen(item, payload))
                self._send_json({"job": job.public_dict()}, status=HTTPStatus.ACCEPTED)
                return

            if parsed.path == "/api/live/start":
                job = JOBS.start("live", lambda item: _job_live(item, payload))
                self._send_json({"job": job.public_dict()}, status=HTTPStatus.ACCEPTED)
                return

            match = re.fullmatch(r"/api/jobs/([a-f0-9]{12})/stop", parsed.path)
            if match:
                job = JOBS.stop(match.group(1))
                if job is None:
                    self._send_error(HTTPStatus.NOT_FOUND, "job not found")
                    return
                self._send_json({"job": job.public_dict()})
                return

            self._send_error(HTTPStatus.NOT_FOUND, "not found")
        except ValueError as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # noqa: BLE001 - API boundary.
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("request body must be a JSON object")
        return data

    def _send_json(self, data: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        raw = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message}, status=status)

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self._send_error(HTTPStatus.NOT_FOUND, "file not found")
            return
        raw = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_run_file(self, url_path: str) -> None:
        path = _resolve_project_path(url_path.lstrip("/"))
        if not path.exists() or not path.is_file():
            self._send_error(HTTPStatus.NOT_FOUND, "file not found")
            return
        content_type = "application/json; charset=utf-8" if path.suffix == ".json" else "text/csv; charset=utf-8"
        self._send_file(path, content_type)


def _api_save_config(payload: dict[str, Any]) -> dict[str, Any]:
    config = _require_dict(payload, "config")
    name = _safe_config_name(str(payload.get("name") or _default_config_name(config)))
    path = CONFIG_DIR / name
    prepared = _prepare_config_for_path(config, path)
    _validate_config_payload(prepared, path)
    _write_json(path, prepared)
    cfg = load_config(path)
    return {"path": _rel(path), "config": prepared, "normalized": config_to_dict(cfg)}


def _job_download(job: Job, payload: dict[str, Any]) -> dict[str, Any]:
    out = _resolve_project_path(str(payload["out"]))
    if not out.is_relative_to(DATA_DIR):
        raise ValueError("download output must be under data/")
    job.logs.append(f"{_now()} downloading {payload['symbol']} to {_rel(out)}")
    report = download_history(
        provider=str(payload.get("provider", "akshare")),
        symbol=str(payload["symbol"]),
        start=str(payload["start"]),
        end=str(payload["end"]),
        out=out,
        adjust=str(payload.get("adjust", "qfq")),
        period=str(payload.get("period", "daily")),
    )
    job.logs.append(f"{_now()} wrote {report['rows']} rows")
    return report


def _job_backtest(job: Job, payload: dict[str, Any]) -> dict[str, Any]:
    config_path = _save_payload_config(payload)
    cfg = load_config(config_path)
    out_dir = RUN_DIR / "backtest" / f"{config_path.stem}-{job.id}"
    job.logs.append(f"{_now()} running backtest with {_rel(config_path)}")
    result = run_backtest(cfg, out_dir)
    fills = [fill.to_dict() for fill in result.fills]
    job.logs.append(f"{_now()} completed backtest: {result.summary['total_return_pct']}%")
    return {
        "config_path": _rel(config_path),
        "out_dir": _rel(out_dir),
        "summary": result.summary,
        "fills": fills,
        "cash_ledger": cash_ledger_from_fills(fills),
        "equity_curve": result.equity_curve,
        "summary_url": f"/{_rel(out_dir / 'summary.json')}",
        "equity_curve_url": f"/{_rel(out_dir / 'equity_curve.csv')}",
        "fills_url": f"/{_rel(out_dir / 'fills.csv')}",
    }


def _job_screen(job: Job, payload: dict[str, Any]) -> dict[str, Any]:
    pattern = str(payload.get("pattern") or "data/*.csv")
    files = _resolve_screen_files(pattern)
    job.logs.append(f"{_now()} screening {len(files)} data files")
    result = screen_stocks(
        files=files,
        lookback=int(payload.get("lookback") or 20),
        short_window=int(payload.get("short_window") or 5),
        long_window=int(payload.get("long_window") or 20),
        min_return_pct=float(payload.get("min_return_pct") or 0.0),
        min_avg_volume=float(payload.get("min_avg_volume") or 0.0),
        require_uptrend=bool(payload.get("require_uptrend", True)),
        limit=int(payload.get("limit") or 50),
    )
    output = RUN_DIR / "screen" / f"screen-{job.id}.json"
    _write_json(output, result)
    job.logs.append(f"{_now()} selected {len(result['candidates'])} candidates")
    return {
        **result,
        "files": [_rel(path) for path in files],
        "output_url": f"/{_rel(output)}",
    }


def _job_live(job: Job, payload: dict[str, Any]) -> dict[str, Any]:
    config_path = _save_payload_config(payload)
    cfg = load_config(config_path)
    if cfg.execution.broker == "live":
        raise RuntimeError(
            "真实券商下单适配器尚未实现。请先实现 chaogu.broker.LiveBrokerAdapter，"
            "或把 execution.broker 设为 paper 做模拟实盘轮询。"
        )

    state_path = _resolve_project_path(str(payload.get("state_path") or f"runs/web/live/{config_path.stem}.state.json"))
    if not state_path.is_relative_to(ROOT / "runs"):
        raise ValueError("state_path must be under runs/")

    max_cycles = int(payload.get("max_cycles") or 0)
    cycles = 0
    last_report: dict[str, Any] | None = None
    reports: list[dict[str, Any]] = []
    job.logs.append(f"{_now()} started paper live loop with {_rel(config_path)}")
    while not job.stop_event.is_set():
        last_report = run_paper_once(cfg, state_path)
        cycles += 1
        reports.append(
            {
                "timestamp": _now(),
                "cash": last_report["cash"],
                "equity": last_report["equity"],
                "processed_bars": last_report["processed_bars"],
                "new_bars": last_report["new_bars"],
                "new_fills": len(last_report["new_fills"]),
            }
        )
        job.result = {
            "config_path": _rel(config_path),
            "state_path": _rel(state_path),
            "cycles": cycles,
            "reports": reports,
            "last_report": last_report,
        }
        job.logs.append(
            f"{_now()} cycle {cycles}: bars={last_report['processed_bars']} "
            f"new_bars={last_report['new_bars']} fills={len(last_report['new_fills'])}"
        )
        if max_cycles > 0 and cycles >= max_cycles:
            break
        job.stop_event.wait(cfg.execution.poll_seconds)

    status = "stopped" if job.stop_event.is_set() else "completed"
    job.status = status
    return {
        "config_path": _rel(config_path),
        "state_path": _rel(state_path),
        "cycles": cycles,
        "reports": reports,
        "last_report": last_report,
    }


def _save_payload_config(payload: dict[str, Any]) -> Path:
    config = _require_dict(payload, "config")
    name = _safe_config_name(str(payload.get("name") or _default_config_name(config)))
    path = CONFIG_DIR / name
    prepared = _prepare_config_for_path(config, path)
    _validate_config_payload(prepared, path)
    _write_json(path, prepared)
    return path


def _validate_config_payload(config: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.parent / f".validate-{uuid.uuid4().hex}.json"
    try:
        _write_json(temp_path, config)
        load_config(temp_path)
    finally:
        temp_path.unlink(missing_ok=True)


def _list_configs() -> list[dict[str, Any]]:
    paths = [ROOT / "config.example.json", *sorted(CONFIG_DIR.glob("*.json"))]
    items = []
    for path in paths:
        if not path.exists():
            continue
        try:
            cfg = load_config(path)
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["market_data_csv"] = _project_path_for_ui(path.parent, str(raw["market_data_csv"]))
            items.append({"name": path.name, "path": _rel(path), "config": raw, "normalized": config_to_dict(cfg)})
        except Exception as exc:  # noqa: BLE001 - surfaced as metadata.
            items.append({"name": path.name, "path": _rel(path), "error": str(exc)})
    return items


def _list_data_files() -> list[dict[str, Any]]:
    if not DATA_DIR.exists():
        return []
    return [
        {"name": path.name, "path": _rel(path), "size": path.stat().st_size}
        for path in sorted(DATA_DIR.glob("*.csv"))
        if path.is_file()
    ]


def _resolve_screen_files(pattern: str) -> list[Path]:
    if pattern.startswith("/"):
        raise ValueError("screen pattern must be relative to project directory")
    paths = sorted(ROOT.glob(pattern))
    files = [path.resolve() for path in paths if path.is_file() and path.suffix.lower() == ".csv"]
    for path in files:
        if not path.is_relative_to(ROOT):
            raise ValueError("screen files must stay inside project directory")
    return files


def _require_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _prepare_config_for_path(config: dict[str, Any], path: Path) -> dict[str, Any]:
    prepared = json.loads(json.dumps(config))
    if "market_data_csv" in prepared:
        resolved = _resolve_market_data_path(path.parent, str(prepared["market_data_csv"]))
        prepared["market_data_csv"] = os.path.relpath(resolved, start=path.parent)
    return prepared


def _resolve_market_data_path(base_dir: Path, value: str) -> Path:
    raw = Path(value)
    if raw.is_absolute():
        resolved = raw.resolve()
    elif value.startswith(("data/", "runs/")):
        resolved = (ROOT / raw).resolve()
    else:
        resolved = (base_dir / raw).resolve()
    if not resolved.is_relative_to(ROOT):
        raise ValueError("market_data_csv must stay inside project directory")
    return resolved


def _project_path_for_ui(base_dir: Path, value: str) -> str:
    resolved = _resolve_market_data_path(base_dir, value)
    return _rel(resolved)


def _safe_config_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    if not name:
        name = "strategy.json"
    if not name.endswith(".json"):
        name += ".json"
    if name in {".json", "..json"} or name.startswith("."):
        raise ValueError("invalid config name")
    return name


def _default_config_name(config: dict[str, Any]) -> str:
    symbol = str(config.get("symbol") or "strategy").replace(".", "_")
    strategy = str((config.get("strategy") or {}).get("name") or "strategy")
    return f"{symbol}_{strategy}.json"


def _resolve_project_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    resolved = path.resolve()
    if not resolved.is_relative_to(ROOT):
        raise ValueError("path must stay inside project directory")
    return resolved


def _rel(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))

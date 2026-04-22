from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st


DRY_RUN_MODE = "dry-run"
RUNNER_MODULE = "src.crawling.run_daily"
RECENT_LOG_SESSION_KEY = "crawling_run_recent_log"
CRAWLING_RUN_MODES: tuple[str, ...] = (
    DRY_RUN_MODE,
    "all",
    "snapshots",
    "kr",
    "us",
    "backfill",
    "backtest",
)
RUN_MODE_LABELS: dict[str, str] = {
    DRY_RUN_MODE: "Dry Run",
    "all": "전체 파이프라인",
    "snapshots": "시장 스냅샷",
    "kr": "KR 스크래퍼",
    "us": "US 스크래퍼",
    "backfill": "5일 수익률 백필",
    "backtest": "조기신호 백테스트",
}


@dataclass(frozen=True)
class CrawlingRunResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    started_at: datetime
    finished_at: datetime
    log_path: Path | None = None


@dataclass(frozen=True)
class CrawlingBackgroundRun:
    command: list[str]
    pid: int
    process: Any
    stdout_path: Path
    stderr_path: Path
    started_at: datetime


@dataclass(frozen=True)
class CrawlingParameterSpec:
    key: str
    env_name: str
    default: int | float


CRAWLING_PARAMETER_SPECS: tuple[CrawlingParameterSpec, ...] = (
    CrawlingParameterSpec("kr_surge_threshold", "CRAWL_KR_SURGE_THRESHOLD", 15.0),
    CrawlingParameterSpec("kr_drop_threshold", "CRAWL_KR_DROP_THRESHOLD", -15.0),
    CrawlingParameterSpec("kr_drop_secondary_threshold", "CRAWL_KR_DROP_SECONDARY_THRESHOLD", -6.0),
    CrawlingParameterSpec("kr_volume_threshold", "CRAWL_KR_VOLUME_THRESHOLD", 500),
    CrawlingParameterSpec("kr_fluctuation_threshold", "CRAWL_KR_FLUCTUATION_THRESHOLD", 6.0),
    CrawlingParameterSpec("us_surge_threshold_large", "CRAWL_US_SURGE_THRESHOLD_LARGE", 8.0),
    CrawlingParameterSpec("us_surge_threshold_small", "CRAWL_US_SURGE_THRESHOLD_SMALL", 15.0),
    CrawlingParameterSpec("us_drop_threshold_large", "CRAWL_US_DROP_THRESHOLD_LARGE", -8.0),
    CrawlingParameterSpec("us_drop_threshold_small", "CRAWL_US_DROP_THRESHOLD_SMALL", -15.0),
    CrawlingParameterSpec("us_market_cap_threshold", "CRAWL_US_MARKET_CAP_THRESHOLD", 2_000_000_000),
    CrawlingParameterSpec("us_volume_threshold", "CRAWL_US_VOLUME_THRESHOLD", 100_000_000),
    CrawlingParameterSpec("us_volatility_threshold", "CRAWL_US_VOLATILITY_THRESHOLD", 5.0),
    CrawlingParameterSpec("early_signal_rvol_min", "CRAWL_EARLY_SIGNAL_RVOL_MIN", 3.0),
    CrawlingParameterSpec("early_signal_change_min", "CRAWL_EARLY_SIGNAL_CHANGE_MIN", 3.0),
    CrawlingParameterSpec("early_signal_change_max", "CRAWL_EARLY_SIGNAL_CHANGE_MAX", 10.0),
    CrawlingParameterSpec("early_signal_streak_min", "CRAWL_EARLY_SIGNAL_STREAK_MIN", 3),
    CrawlingParameterSpec("early_signal_ratio_52w_min", "CRAWL_EARLY_SIGNAL_RATIO_52W_MIN", 0.95),
)

CRAWLING_PARAMETER_UI: dict[str, dict[str, Any]] = {
    "kr_surge_threshold": {"group": "KR", "label": "KR 급등 기준 (%)", "widget": "slider", "min_value": 5.0, "max_value": 30.0, "step": 0.5},
    "kr_drop_threshold": {"group": "KR", "label": "KR 낙폭과대 절대 기준 (%)", "widget": "slider", "min_value": -30.0, "max_value": -5.0, "step": 0.5},
    "kr_drop_secondary_threshold": {"group": "KR", "label": "KR 낙폭과대 복합 기준 (%)", "widget": "slider", "min_value": -15.0, "max_value": 0.0, "step": 0.5},
    "kr_volume_threshold": {"group": "KR", "label": "KR 거래대금 기준 (억 원)", "widget": "number_input", "min_value": 0, "max_value": 10_000, "step": 50},
    "kr_fluctuation_threshold": {"group": "KR", "label": "KR 변동폭 기준 (%)", "widget": "slider", "min_value": 1.0, "max_value": 15.0, "step": 0.5},
    "us_surge_threshold_large": {"group": "US", "label": "US 대형주 급등 기준 (%)", "widget": "slider", "min_value": 3.0, "max_value": 20.0, "step": 0.5},
    "us_surge_threshold_small": {"group": "US", "label": "US 소형주 급등 기준 (%)", "widget": "slider", "min_value": 5.0, "max_value": 30.0, "step": 0.5},
    "us_drop_threshold_large": {"group": "US", "label": "US 대형주 낙폭과대 기준 (%)", "widget": "slider", "min_value": -25.0, "max_value": -3.0, "step": 0.5},
    "us_drop_threshold_small": {"group": "US", "label": "US 소형주 낙폭과대 기준 (%)", "widget": "slider", "min_value": -30.0, "max_value": -5.0, "step": 0.5},
    "us_market_cap_threshold": {"group": "US", "label": "US 대형주 구분 시가총액", "widget": "number_input", "min_value": 0, "max_value": 20_000_000_000, "step": 100_000_000},
    "us_volume_threshold": {"group": "US", "label": "US 거래대금 기준", "widget": "number_input", "min_value": 0, "max_value": 2_000_000_000, "step": 10_000_000},
    "us_volatility_threshold": {"group": "US", "label": "US 변동폭 기준 (%)", "widget": "slider", "min_value": 1.0, "max_value": 15.0, "step": 0.5},
    "early_signal_rvol_min": {"group": "조기신호", "label": "RVOL 최소", "widget": "slider", "min_value": 1.0, "max_value": 10.0, "step": 0.1},
    "early_signal_change_min": {"group": "조기신호", "label": "등락률 최소 (%)", "widget": "slider", "min_value": 1.0, "max_value": 10.0, "step": 0.1},
    "early_signal_change_max": {"group": "조기신호", "label": "등락률 최대 (%)", "widget": "slider", "min_value": 5.0, "max_value": 20.0, "step": 0.1},
    "early_signal_streak_min": {"group": "조기신호", "label": "연속 상승일 최소", "widget": "number_input", "min_value": 1, "max_value": 20, "step": 1},
    "early_signal_ratio_52w_min": {"group": "조기신호", "label": "52주 고가 비율 최소", "widget": "slider", "min_value": 0.8, "max_value": 1.0, "step": 0.01},
}


Runner = Callable[..., Any]


def format_run_mode(mode: str) -> str:
    return RUN_MODE_LABELS.get(mode, mode)


def build_crawling_command(
    mode: str,
    python_executable: str | None = None,
) -> list[str]:
    if mode not in CRAWLING_RUN_MODES:
        raise ValueError(f"Unsupported crawling run mode: {mode}")

    python = python_executable or sys.executable
    if mode == DRY_RUN_MODE:
        return [python, "-m", RUNNER_MODULE, "--dry-run"]
    return [python, "-m", RUNNER_MODULE, "--mode", mode]


def build_crawling_env(
    base_env: Mapping[str, str] | None = None,
    parameter_values: Mapping[str, int | float] | None = None,
) -> dict[str, str]:
    env = dict(base_env if base_env is not None else os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"

    if parameter_values:
        specs_by_key = {spec.key: spec for spec in CRAWLING_PARAMETER_SPECS}
        for key, value in parameter_values.items():
            spec = specs_by_key.get(key)
            if spec is None:
                raise ValueError(f"Unknown crawling parameter: {key}")
            env[spec.env_name] = str(value)

    return env


def render_crawling_parameter_inputs(
    *,
    st_api: Any = st,
) -> dict[str, int | float]:
    values: dict[str, int | float] = {}
    current_group: str | None = None

    for spec in CRAWLING_PARAMETER_SPECS:
        ui = CRAWLING_PARAMETER_UI[spec.key]
        group = str(ui["group"])
        if group != current_group:
            st_api.subheader(group)
            current_group = group

        widget_kwargs = {
            "label": str(ui["label"]),
            "min_value": ui["min_value"],
            "max_value": ui["max_value"],
            "value": spec.default,
            "step": ui["step"],
            "key": f"crawling_param_{spec.key}",
        }
        if ui["widget"] == "number_input":
            value = st_api.number_input(**widget_kwargs)
        else:
            value = st_api.slider(**widget_kwargs)

        values[spec.key] = int(value) if isinstance(spec.default, int) else float(value)

    return values


def default_crawling_log_dir(project_root: Path | str | None = None) -> Path:
    root = Path(project_root) if project_root is not None else Path(__file__).resolve().parents[2]
    return root / "logs" / "crawling"


def list_crawling_run_logs(log_dir: Path | str, *, limit: int = 5) -> list[Path]:
    target_dir = Path(log_dir)
    if not target_dir.exists():
        return []
    logs = [
        path
        for path in target_dir.glob("*.log")
        if path.name.endswith(("-crawling-run.log", "-stdout.log", "-stderr.log"))
    ]
    return sorted(logs, reverse=True)[:limit]


def read_log_tail(log_path: Path | str, *, lines: int = 80) -> str:
    text_lines = Path(log_path).read_text(encoding="utf-8").splitlines()
    return "\n".join(text_lines[-lines:])


def sync_crawling_recent_log_selection(
    recent_logs: list[Path],
    *,
    session_state: Any,
    preferred_log: Path | None = None,
    force: bool = False,
    key: str = RECENT_LOG_SESSION_KEY,
) -> Path | None:
    if not recent_logs:
        session_state.pop(key, None)
        return None

    preferred = preferred_log if preferred_log in recent_logs else recent_logs[0]
    current = session_state.get(key)
    if force or current not in recent_logs:
        session_state[key] = preferred
    return session_state[key]


def refresh_crawling_log_view(
    *,
    active: bool,
    enabled: bool = True,
    interval_seconds: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
    st_api: Any = st,
) -> bool:
    if not active or not enabled:
        return False

    sleep(max(interval_seconds, 0.0))
    st_api.rerun()
    return True


def write_crawling_run_log(
    result: CrawlingRunResult,
    *,
    log_dir: Path | str,
) -> Path:
    target_dir = Path(log_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    log_path = target_dir / f"{result.started_at.strftime('%Y%m%d-%H%M%S')}-crawling-run.log"
    content = "\n".join(
        [
            f"started_at: {result.started_at.isoformat(timespec='seconds')}",
            f"finished_at: {result.finished_at.isoformat(timespec='seconds')}",
            f"command: {' '.join(result.command)}",
            f"exit_code: {result.returncode}",
            "",
            "stdout:",
            result.stdout,
            "",
            "stderr:",
            result.stderr,
            "",
        ]
    )
    log_path.write_text(content, encoding="utf-8")
    return log_path


def run_crawling_command(
    mode: str,
    *,
    python_executable: str | None = None,
    project_root: Path | str | None = None,
    base_env: Mapping[str, str] | None = None,
    parameter_values: Mapping[str, int | float] | None = None,
    log_dir: Path | str | None = None,
    runner: Runner = subprocess.run,
) -> CrawlingRunResult:
    root = Path(project_root) if project_root is not None else Path(__file__).resolve().parents[2]
    command = build_crawling_command(mode, python_executable=python_executable)
    started_at = datetime.now()
    completed = runner(
        command,
        cwd=str(root),
        env=build_crawling_env(base_env, parameter_values=parameter_values),
        capture_output=True,
        text=True,
    )
    finished_at = datetime.now()

    result = CrawlingRunResult(
        command=command,
        returncode=int(completed.returncode),
        stdout=str(completed.stdout or ""),
        stderr=str(completed.stderr or ""),
        started_at=started_at,
        finished_at=finished_at,
    )
    if log_dir is not None:
        result = replace(result, log_path=write_crawling_run_log(result, log_dir=log_dir))
    return result


def start_crawling_background_run(
    mode: str,
    *,
    python_executable: str | None = None,
    project_root: Path | str | None = None,
    base_env: Mapping[str, str] | None = None,
    parameter_values: Mapping[str, int | float] | None = None,
    log_dir: Path | str | None = None,
    popen: Runner = subprocess.Popen,
) -> CrawlingBackgroundRun:
    if mode == DRY_RUN_MODE:
        raise ValueError("Dry run should use run_crawling_command")

    root = Path(project_root) if project_root is not None else Path(__file__).resolve().parents[2]
    target_log_dir = Path(log_dir) if log_dir is not None else default_crawling_log_dir(root)
    target_log_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now()
    stem = started_at.strftime("%Y%m%d-%H%M%S")
    stdout_path = target_log_dir / f"{stem}-stdout.log"
    stderr_path = target_log_dir / f"{stem}-stderr.log"
    command = build_crawling_command(mode, python_executable=python_executable)

    with stdout_path.open("w", encoding="utf-8") as stdout_file, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr_file:
        process = popen(
            command,
            cwd=str(root),
            env=build_crawling_env(base_env, parameter_values=parameter_values),
            stdout=stdout_file,
            stderr=stderr_file,
            text=True,
        )

    return CrawlingBackgroundRun(
        command=command,
        pid=int(process.pid),
        process=process,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        started_at=started_at,
    )


def poll_crawling_background_run(run: CrawlingBackgroundRun) -> dict[str, int | bool | None]:
    returncode = run.process.poll()
    return {
        "pid": run.pid,
        "running": returncode is None,
        "returncode": returncode,
    }


def is_crawling_background_run_active(run: CrawlingBackgroundRun | None) -> bool:
    if run is None:
        return False
    return run.process.poll() is None


def terminate_crawling_background_run(
    run: CrawlingBackgroundRun,
    *,
    timeout: int = 10,
) -> int | None:
    current_code = run.process.poll()
    if current_code is not None:
        return current_code
    run.process.terminate()
    try:
        return run.process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        run.process.kill()
        return run.process.wait(timeout=timeout)


def emit_background_completion_status(returncode: int | None, *, st_api: Any = st) -> None:
    message = f"종료 코드: {returncode}"
    if returncode == 0:
        st_api.success(message)
    else:
        st_api.error(message)


def render_crawling_run_tab() -> None:
    st.header("크롤링 실행")
    log_dir = default_crawling_log_dir()
    active_log_refresh_needed = False
    preferred_recent_log: Path | None = None
    force_recent_log_selection = False

    mode = st.selectbox(
        "실행 모드",
        list(CRAWLING_RUN_MODES),
        format_func=format_run_mode,
        key="crawling_run_mode",
    )
    parameter_values = render_crawling_parameter_inputs()

    existing_background_run = st.session_state.get("crawling_background_run")
    background_active = (
        is_crawling_background_run_active(existing_background_run)
        if isinstance(existing_background_run, CrawlingBackgroundRun)
        else False
    )

    if st.button(
        "실행",
        type="primary",
        key="crawling_run_execute",
        disabled=background_active,
    ):
        with st.spinner("크롤링 runner 확인 중..."):
            try:
                if mode == DRY_RUN_MODE:
                    result = run_crawling_command(
                        mode,
                        parameter_values=parameter_values,
                        log_dir=log_dir,
                    )
                    st.session_state["crawling_run_last_result"] = result
                else:
                    background_run = start_crawling_background_run(
                        mode,
                        parameter_values=parameter_values,
                        log_dir=log_dir,
                    )
                    st.session_state["crawling_background_run"] = background_run
                    result = None
            except Exception as exc:
                st.session_state["crawling_run_last_error"] = str(exc)
                st.error(f"실행 실패: {exc}")
            else:
                if result is None:
                    st.success("백그라운드 실행 시작")
                elif result.returncode == 0:
                    st.success("실행 완료")
                else:
                    st.error(f"실행 실패: exit code {result.returncode}")

    background_run = st.session_state.get("crawling_background_run")
    if isinstance(background_run, CrawlingBackgroundRun):
        status = poll_crawling_background_run(background_run)
        active_log_refresh_needed = bool(status["running"])
        preferred_recent_log = background_run.stdout_path
        force_recent_log_selection = bool(status["running"])
        st.metric("Background PID", status["pid"])
        if status["running"]:
            st.info("실행 중")
            if st.button("실행 중단", key="crawling_run_terminate"):
                returncode = terminate_crawling_background_run(background_run)
                st.success(f"중단 완료: {returncode}")
        else:
            emit_background_completion_status(status["returncode"])
        st.caption(str(background_run.stdout_path))
        if background_run.stdout_path.exists():
            st.text_area("background stdout", read_log_tail(background_run.stdout_path), height=180)
        if background_run.stderr_path.exists():
            stderr_tail = read_log_tail(background_run.stderr_path)
            if stderr_tail:
                st.text_area("background stderr", stderr_tail, height=140)

    result = st.session_state.get("crawling_run_last_result")
    if isinstance(result, CrawlingRunResult):
        st.metric("Exit Code", result.returncode)
        st.code(" ".join(result.command), language="powershell")
        if result.log_path is not None:
            preferred_recent_log = result.log_path
            force_recent_log_selection = True
            st.caption(str(result.log_path))
        if result.stdout:
            st.text_area("stdout", result.stdout, height=140)
        if result.stderr:
            st.text_area("stderr", result.stderr, height=140)

    recent_logs = list_crawling_run_logs(log_dir)
    if recent_logs:
        st.subheader("최근 실행 로그")
        sync_crawling_recent_log_selection(
            recent_logs,
            session_state=st.session_state,
            preferred_log=preferred_recent_log,
            force=force_recent_log_selection,
        )
        selected_log = st.selectbox(
            "로그 파일",
            recent_logs,
            format_func=lambda path: path.name,
            key=RECENT_LOG_SESSION_KEY,
        )
        st.text_area("최근 로그", read_log_tail(selected_log), height=220)

    refresh_crawling_log_view(active=active_log_refresh_needed)

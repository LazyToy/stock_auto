from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tomllib

from dashboard.components.crawling_run_tab import (
    CRAWLING_PARAMETER_SPECS,
    CrawlingBackgroundRun,
    CrawlingRunResult,
    DRY_RUN_MODE,
    build_crawling_command,
    build_crawling_env,
    emit_background_completion_status,
    format_run_mode,
    is_crawling_background_run_active,
    list_crawling_run_logs,
    poll_crawling_background_run,
    read_log_tail,
    refresh_crawling_log_view,
    render_crawling_parameter_inputs,
    run_crawling_command,
    start_crawling_background_run,
    sync_crawling_recent_log_selection,
    terminate_crawling_background_run,
    write_crawling_run_log,
)


def test_build_crawling_command_uses_package_runner_dry_run() -> None:
    command = build_crawling_command(DRY_RUN_MODE, python_executable="python-test")

    assert command == ["python-test", "-m", "src.crawling.run_daily", "--dry-run"]


def test_build_crawling_command_uses_runner_mode_for_non_dry_run() -> None:
    command = build_crawling_command("kr", python_executable="python-test")

    assert command == ["python-test", "-m", "src.crawling.run_daily", "--mode", "kr"]


def test_format_run_mode_uses_readable_labels() -> None:
    assert format_run_mode(DRY_RUN_MODE) == "Dry Run"
    assert format_run_mode("kr") == "KR 스크래퍼"
    assert format_run_mode("backtest") == "조기신호 백테스트"


def test_build_crawling_env_sets_utf8_and_preserves_existing_env() -> None:
    env = build_crawling_env({"EXISTING": "yes"})

    assert env["EXISTING"] == "yes"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["PYTHONUNBUFFERED"] == "1"


def test_crawling_parameter_specs_cover_phase4_env_names() -> None:
    env_names = {spec.env_name for spec in CRAWLING_PARAMETER_SPECS}

    assert env_names == {
        "CRAWL_KR_SURGE_THRESHOLD",
        "CRAWL_KR_DROP_THRESHOLD",
        "CRAWL_KR_DROP_SECONDARY_THRESHOLD",
        "CRAWL_KR_VOLUME_THRESHOLD",
        "CRAWL_KR_FLUCTUATION_THRESHOLD",
        "CRAWL_US_SURGE_THRESHOLD_LARGE",
        "CRAWL_US_SURGE_THRESHOLD_SMALL",
        "CRAWL_US_DROP_THRESHOLD_LARGE",
        "CRAWL_US_DROP_THRESHOLD_SMALL",
        "CRAWL_US_MARKET_CAP_THRESHOLD",
        "CRAWL_US_VOLUME_THRESHOLD",
        "CRAWL_US_VOLATILITY_THRESHOLD",
        "CRAWL_EARLY_SIGNAL_RVOL_MIN",
        "CRAWL_EARLY_SIGNAL_CHANGE_MIN",
        "CRAWL_EARLY_SIGNAL_CHANGE_MAX",
        "CRAWL_EARLY_SIGNAL_STREAK_MIN",
        "CRAWL_EARLY_SIGNAL_RATIO_52W_MIN",
    }


def test_render_crawling_parameter_inputs_uses_expected_widgets() -> None:
    class FakeStreamlit:
        def __init__(self) -> None:
            self.slider_calls = []
            self.number_input_calls = []
            self.subheaders = []

        def subheader(self, label):
            self.subheaders.append(label)

        def slider(self, **kwargs):
            self.slider_calls.append(kwargs)
            return kwargs["value"]

        def number_input(self, **kwargs):
            self.number_input_calls.append(kwargs)
            return kwargs["value"]

    fake_st = FakeStreamlit()

    values = render_crawling_parameter_inputs(st_api=fake_st)

    assert values["kr_surge_threshold"] == 15.0
    assert values["kr_volume_threshold"] == 500
    assert values["early_signal_streak_min"] == 3
    assert any(call["key"] == "crawling_param_kr_surge_threshold" for call in fake_st.slider_calls)
    assert any(call["key"] == "crawling_param_kr_volume_threshold" for call in fake_st.number_input_calls)
    assert any(call["key"] == "crawling_param_early_signal_streak_min" for call in fake_st.number_input_calls)


def test_build_crawling_env_maps_parameter_values_to_runner_env() -> None:
    env = build_crawling_env(
        {"BASE": "1"},
        parameter_values={
            "kr_surge_threshold": 21.5,
            "kr_volume_threshold": 900,
            "early_signal_ratio_52w_min": 0.975,
        },
    )

    assert env["BASE"] == "1"
    assert env["CRAWL_KR_SURGE_THRESHOLD"] == "21.5"
    assert env["CRAWL_KR_VOLUME_THRESHOLD"] == "900"
    assert env["CRAWL_EARLY_SIGNAL_RATIO_52W_MIN"] == "0.975"


def test_build_crawling_env_rejects_unknown_parameter_key() -> None:
    try:
        build_crawling_env(parameter_values={"unknown_threshold": 1})
    except ValueError as exc:
        assert "unknown_threshold" in str(exc)
    else:
        raise AssertionError("expected unknown parameter key to fail")


def test_run_crawling_command_uses_injected_runner_and_project_root() -> None:
    calls = []
    project_root = Path.cwd()

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        return type(
            "Completed",
            (),
            {"returncode": 0, "stdout": "ok", "stderr": ""},
        )()

    result = run_crawling_command(
        DRY_RUN_MODE,
        python_executable="python-test",
        project_root=project_root,
        base_env={"BASE": "1"},
        runner=fake_runner,
    )

    assert result.returncode == 0
    assert result.stdout == "ok"
    assert result.stderr == ""
    assert result.command == ["python-test", "-m", "src.crawling.run_daily", "--dry-run"]
    assert calls[0][0] == result.command
    assert calls[0][1]["cwd"] == str(project_root)
    assert calls[0][1]["capture_output"] is True
    assert calls[0][1]["text"] is True
    assert calls[0][1]["env"]["BASE"] == "1"
    assert calls[0][1]["env"]["PYTHONIOENCODING"] == "utf-8"


def test_run_crawling_command_forwards_parameter_values_to_env() -> None:
    calls = []

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        return type(
            "Completed",
            (),
            {"returncode": 0, "stdout": "", "stderr": ""},
        )()

    run_crawling_command(
        "kr",
        python_executable="python-test",
        project_root=Path.cwd(),
        parameter_values={"kr_surge_threshold": 22.0},
        runner=fake_runner,
    )

    assert calls[0][1]["env"]["CRAWL_KR_SURGE_THRESHOLD"] == "22.0"


def test_write_crawling_run_log_creates_readable_log_file() -> None:
    log_dir = Path.cwd() / ".pytest_tmp" / "crawling_run_tab_logs"
    result = CrawlingRunResult(
        command=["python", "-m", "src.crawling.run_daily", "--dry-run"],
        returncode=0,
        stdout="ok",
        stderr="",
        started_at=datetime(2026, 4, 21, 10, 0, 0),
        finished_at=datetime(2026, 4, 21, 10, 0, 1),
    )

    log_path = write_crawling_run_log(result, log_dir=log_dir)

    assert log_path.parent == log_dir
    assert log_path.name == "20260421-100000-crawling-run.log"
    text = log_path.read_text(encoding="utf-8")
    assert "command: python -m src.crawling.run_daily --dry-run" in text
    assert "exit_code: 0" in text
    assert "stdout:" in text
    assert "ok" in text


def test_run_crawling_command_writes_log_when_log_dir_is_provided() -> None:
    log_dir = Path.cwd() / ".pytest_tmp" / "crawling_run_command_logs"

    def fake_runner(command, **kwargs):
        return type(
            "Completed",
            (),
            {"returncode": 0, "stdout": "runner ok", "stderr": ""},
        )()

    result = run_crawling_command(
        DRY_RUN_MODE,
        python_executable="python-test",
        project_root=Path.cwd(),
        runner=fake_runner,
        log_dir=log_dir,
    )

    assert result.log_path is not None
    assert result.log_path.exists()
    assert "runner ok" in result.log_path.read_text(encoding="utf-8")


def test_list_crawling_run_logs_returns_newest_first() -> None:
    log_dir = Path.cwd() / ".pytest_tmp" / "crawling_run_log_list"
    log_dir.mkdir(parents=True, exist_ok=True)
    older = log_dir / "20260421-090000-crawling-run.log"
    newer = log_dir / "20260421-100000-crawling-run.log"
    background = log_dir / "20260421-110000-stdout.log"
    ignored = log_dir / "notes.txt"
    older.write_text("older", encoding="utf-8")
    newer.write_text("newer", encoding="utf-8")
    background.write_text("background", encoding="utf-8")
    ignored.write_text("ignored", encoding="utf-8")

    logs = list_crawling_run_logs(log_dir, limit=3)

    assert logs == [background, newer, older]


def test_read_log_tail_returns_last_lines() -> None:
    log_dir = Path.cwd() / ".pytest_tmp" / "crawling_run_log_tail"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "20260421-100000-crawling-run.log"
    log_path.write_text("one\ntwo\nthree\n", encoding="utf-8")

    assert read_log_tail(log_path, lines=2) == "two\nthree"


def test_sync_crawling_recent_log_selection_prefers_active_stdout() -> None:
    log_dir = Path.cwd() / ".pytest_tmp" / "crawling_log_selection"
    log_dir.mkdir(parents=True, exist_ok=True)
    older = log_dir / "20260421-090000-crawling-run.log"
    active_stdout = log_dir / "20260421-100000-stdout.log"
    older.write_text("older", encoding="utf-8")
    active_stdout.write_text("active", encoding="utf-8")
    session_state = {"crawling_run_recent_log": older}

    selected = sync_crawling_recent_log_selection(
        [active_stdout, older],
        session_state=session_state,
        preferred_log=active_stdout,
        force=True,
    )

    assert selected == active_stdout
    assert session_state["crawling_run_recent_log"] == active_stdout


def test_refresh_crawling_log_view_requests_rerun_when_active_and_enabled() -> None:
    calls = []

    class FakeStreamlit:
        def rerun(self):
            calls.append("rerun")

    refreshed = refresh_crawling_log_view(
        active=True,
        enabled=True,
        interval_seconds=0.25,
        sleep=lambda seconds: calls.append(("sleep", seconds)),
        st_api=FakeStreamlit(),
    )

    assert refreshed is True
    assert calls == [("sleep", 0.25), "rerun"]


def test_refresh_crawling_log_view_skips_when_background_is_inactive() -> None:
    calls = []

    class FakeStreamlit:
        def rerun(self):
            calls.append("rerun")

    refreshed = refresh_crawling_log_view(
        active=False,
        enabled=True,
        sleep=lambda seconds: calls.append(("sleep", seconds)),
        st_api=FakeStreamlit(),
    )

    assert refreshed is False
    assert calls == []


def test_start_crawling_background_run_uses_popen_and_log_files() -> None:
    calls = []
    log_dir = Path.cwd() / ".pytest_tmp" / "crawling_background"

    class FakeProcess:
        pid = 1234

        def poll(self):
            return None

    def fake_popen(command, **kwargs):
        calls.append((command, kwargs))
        return FakeProcess()

    run = start_crawling_background_run(
        "kr",
        python_executable="python-test",
        project_root=Path.cwd(),
        parameter_values={"kr_surge_threshold": 22.0},
        log_dir=log_dir,
        popen=fake_popen,
    )

    assert isinstance(run, CrawlingBackgroundRun)
    assert run.pid == 1234
    assert run.command == ["python-test", "-m", "src.crawling.run_daily", "--mode", "kr"]
    assert run.stdout_path.parent == log_dir
    assert run.stderr_path.parent == log_dir
    assert run.stdout_path.name.endswith("-stdout.log")
    assert run.stderr_path.name.endswith("-stderr.log")
    assert calls[0][1]["cwd"] == str(Path.cwd())
    assert calls[0][1]["env"]["CRAWL_KR_SURGE_THRESHOLD"] == "22.0"


def test_poll_crawling_background_run_reports_running_and_finished() -> None:
    class FakeProcess:
        def __init__(self) -> None:
            self.values = [None, 0]

        def poll(self):
            return self.values.pop(0)

    run = CrawlingBackgroundRun(
        command=["python"],
        pid=77,
        process=FakeProcess(),
        stdout_path=Path("stdout.log"),
        stderr_path=Path("stderr.log"),
        started_at=datetime(2026, 4, 21, 10, 0, 0),
    )

    running = poll_crawling_background_run(run)
    finished = poll_crawling_background_run(run)

    assert running["running"] is True
    assert running["returncode"] is None
    assert finished["running"] is False
    assert finished["returncode"] == 0


def test_is_crawling_background_run_active_uses_process_poll() -> None:
    class FakeProcess:
        def poll(self):
            return None

    run = CrawlingBackgroundRun(
        command=["python"],
        pid=77,
        process=FakeProcess(),
        stdout_path=Path("stdout.log"),
        stderr_path=Path("stderr.log"),
        started_at=datetime(2026, 4, 21, 10, 0, 0),
    )

    assert is_crawling_background_run_active(run) is True


def test_terminate_crawling_background_run_terminates_running_process() -> None:
    class FakeProcess:
        def __init__(self) -> None:
            self.terminated = False
            self.wait_timeout = None

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout):
            self.wait_timeout = timeout
            return 0

    process = FakeProcess()
    run = CrawlingBackgroundRun(
        command=["python"],
        pid=77,
        process=process,
        stdout_path=Path("stdout.log"),
        stderr_path=Path("stderr.log"),
        started_at=datetime(2026, 4, 21, 10, 0, 0),
    )

    result = terminate_crawling_background_run(run, timeout=3)

    assert result == 0
    assert process.terminated is True
    assert process.wait_timeout == 3


def test_terminate_crawling_background_run_skips_finished_process() -> None:
    class FakeProcess:
        def __init__(self) -> None:
            self.terminated = False

        def poll(self):
            return 0

        def terminate(self):
            self.terminated = True

    process = FakeProcess()
    run = CrawlingBackgroundRun(
        command=["python"],
        pid=77,
        process=process,
        stdout_path=Path("stdout.log"),
        stderr_path=Path("stderr.log"),
        started_at=datetime(2026, 4, 21, 10, 0, 0),
    )

    result = terminate_crawling_background_run(run)

    assert result == 0
    assert process.terminated is False


def test_terminate_crawling_background_run_kills_when_terminate_times_out() -> None:
    class FakeTimeoutExpired(Exception):
        pass

    class FakeProcess:
        def __init__(self) -> None:
            self.killed = False

        def poll(self):
            return None

        def terminate(self):
            pass

        def wait(self, timeout):
            if not self.killed:
                raise subprocess.TimeoutExpired(cmd=["python"], timeout=timeout)
            return -9

        def kill(self):
            self.killed = True

    import subprocess

    process = FakeProcess()
    run = CrawlingBackgroundRun(
        command=["python"],
        pid=77,
        process=process,
        stdout_path=Path("stdout.log"),
        stderr_path=Path("stderr.log"),
        started_at=datetime(2026, 4, 21, 10, 0, 0),
    )

    result = terminate_crawling_background_run(run, timeout=1)

    assert result == -9
    assert process.killed is True


def test_emit_background_completion_status_reports_nonzero_as_error() -> None:
    class FakeStreamlit:
        def __init__(self) -> None:
            self.success_calls = []
            self.error_calls = []

        def success(self, message):
            self.success_calls.append(message)

        def error(self, message):
            self.error_calls.append(message)

    fake_st = FakeStreamlit()

    emit_background_completion_status(2, st_api=fake_st)

    assert fake_st.success_calls == []
    assert fake_st.error_calls == ["종료 코드: 2"]


def test_emit_background_completion_status_reports_zero_as_success() -> None:
    class FakeStreamlit:
        def __init__(self) -> None:
            self.success_calls = []
            self.error_calls = []

        def success(self, message):
            self.success_calls.append(message)

        def error(self, message):
            self.error_calls.append(message)

    fake_st = FakeStreamlit()

    emit_background_completion_status(0, st_api=fake_st)

    assert fake_st.success_calls == ["종료 코드: 0"]
    assert fake_st.error_calls == []


def test_dashboard_app_wires_crawling_run_tab() -> None:
    text = Path("dashboard/app.py").read_text(encoding="utf-8")

    assert "from dashboard.components.crawling_run_tab import render_crawling_run_tab" in text
    assert "크롤링 실행" in text
    assert "render_crawling_run_tab()" in text


def test_pyproject_declares_dashboard_runtime_dependencies() -> None:
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dependencies = {dep.split(">=")[0].lower() for dep in data["project"]["dependencies"]}

    assert "streamlit" in dependencies
    assert "yfinance" in dependencies
    assert "mplfinance" in dependencies
    assert "playwright" in dependencies

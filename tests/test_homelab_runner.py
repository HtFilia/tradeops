"""Native process lifecycle checks; no database or network is contacted."""

import threading
from unittest.mock import Mock, patch
from urllib.error import HTTPError

import pytest

from deploy import homelab_run as runner


def test_readiness_requires_all_workers_and_accepts_unauthenticated_session() -> None:
    workers = runner.worker_specs()
    processes = [Mock(poll=Mock(return_value=None)) for _ in workers]
    response = Mock()
    response.status = 200
    response.read.return_value = (
        b'{"status":"ok","instruments":{"EQ-ACME":{"last_tick":{"mid":100}}}}'
    )
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    unauthorized = HTTPError(workers[0].health_url, 401, "Unauthorized", {}, None)
    with patch.object(
        runner, "urlopen", side_effect=[unauthorized, response, response]
    ):
        assert runner.ready(workers, processes)
    with patch.object(runner, "urlopen", side_effect=OSError("unavailable")):
        assert not runner.ready(workers, processes)
    processes[1].poll.return_value = 1
    assert not runner.ready(workers, processes)


def test_market_health_without_a_tick_is_not_ready() -> None:
    workers = runner.worker_specs()
    processes = [Mock(poll=Mock(return_value=None)) for _ in workers]
    response = Mock(status=200)
    response.read.return_value = b'{"status":"ok","instruments":{}}'
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    with patch.object(runner, "urlopen", return_value=response):
        assert not runner.ready(workers, processes)


def test_one_worker_exit_stops_the_project_even_if_exit_code_is_zero() -> None:
    processes = [Mock(poll=Mock(return_value=0)), Mock(poll=Mock(return_value=None))]
    assert runner.monitor(processes, threading.Event()) == 1


def test_shutdown_terminates_all_children_and_waits_for_them() -> None:
    processes = [Mock(poll=Mock(return_value=None)) for _ in range(3)]
    runner.stop_children(processes)
    for process in processes:
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=10)


def test_workers_use_current_interpreter_loopback_and_one_uvicorn_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MARKET_DATA_HTTP_HOST", "127.0.0.1")
    monkeypatch.setenv("MARKET_DATA_HTTP_PORT", "8110")
    specs = runner.worker_specs()
    assert [w.name for w in specs] == ["auth", "market", "trading"]
    for worker in specs:
        assert worker.command[0] == runner.sys.executable
        assert worker.health_url.startswith("http://127.0.0.1:")
    assert "--host" in specs[0].command
    assert "0.0.0.0" not in str(specs)


def test_supervisor_refuses_non_loopback_market_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MARKET_DATA_HTTP_HOST", "0.0.0.0")
    with pytest.raises(ValueError, match="loopback"):
        runner.worker_specs()


def test_shutdown_kills_a_worker_that_ignores_termination() -> None:
    process = Mock(poll=Mock(return_value=None))
    process.wait.side_effect = [runner.subprocess.TimeoutExpired("worker", 10), None]
    runner.stop_children([process])
    process.terminate.assert_called_once()
    process.kill.assert_called_once()
    assert process.wait.call_count == 2


def test_partial_startup_failure_stops_children_already_started() -> None:
    process = Mock(poll=Mock(return_value=None))
    with (
        patch.object(runner.signal, "signal"),
        patch.object(
            runner.subprocess, "Popen", side_effect=[process, OSError("spawn failed")]
        ),
        patch.object(runner, "stop_children") as cleanup,
    ):
        with pytest.raises(OSError, match="spawn failed"):
            runner.main()
    cleanup.assert_called_once_with([process])

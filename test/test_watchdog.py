import asyncio
import os
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pyrogram import Client
from pyrogram.session import Session

os.environ.setdefault("BOT_TOKEN", "123456:watchdog-test-token")
os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "watchdog-test-hash")

import core.watchdog as watchdog  # noqa: E402


@pytest.fixture(autouse=True)
def watchdog_state(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    exit_codes: list[int] = []
    monkeypatch.setattr(watchdog, "ws", SimpleNamespace(exit_flag=False, reconnect_grace_seconds=0.2))
    monkeypatch.setattr(watchdog.os, "_exit", exit_codes.append)
    monkeypatch.setattr(watchdog, "STOP_TIMEOUT", 0.03)
    watchdog._grace_task = None
    watchdog._disconnected_at = None
    return exit_codes


class FakeClient:
    def __init__(self, session: SimpleNamespace) -> None:
        self.main_session = session
        self.stop_calls = 0
        self.stop_task: asyncio.Task[Any] | None = None
        self.stop_path_task_cancelled = False

    async def stop(self) -> None:
        self.stop_calls += 1
        self.stop_task = asyncio.current_task()
        watchdog.ws.exit_flag = True
        await watchdog.on_disconnect(cast(Client, self), cast(Session, self.main_session))
        self.stop_path_task_cancelled = bool(self.stop_task and self.stop_task.cancelling())


def main_session() -> SimpleNamespace:
    return SimpleNamespace(is_media=False)


async def disconnect(client: FakeClient, session: SimpleNamespace) -> None:
    await watchdog.on_disconnect(cast(Client, client), cast(Session, session))


async def connect(client: FakeClient, session: SimpleNamespace) -> None:
    await watchdog.on_connect(cast(Client, client), cast(Session, session))


def test_duplicate_disconnect_callbacks_share_grace_and_recovery_cancels_it(watchdog_state: list[int]) -> None:
    async def scenario() -> None:
        session = main_session()
        client = FakeClient(session)

        await disconnect(client, session)
        first_task = watchdog._grace_task
        await asyncio.sleep(0.004)
        await disconnect(client, session)

        assert watchdog._grace_task is first_task
        await connect(client, session)
        await asyncio.sleep(0.22)

        assert watchdog._grace_task is None
        assert watchdog_state == []
        assert client.stop_calls == 0

    asyncio.run(scenario())


def test_recovery_within_grace_does_not_stop_client(watchdog_state: list[int]) -> None:
    async def scenario() -> None:
        session = main_session()
        client = FakeClient(session)

        await disconnect(client, session)
        await asyncio.sleep(0.12)
        await connect(client, session)
        await asyncio.sleep(0.11)

        assert watchdog_state == []
        assert client.stop_calls == 0

    asyncio.run(scenario())


def test_permanent_outage_stops_client_and_exits(watchdog_state: list[int]) -> None:
    async def scenario() -> None:
        session = main_session()
        client = FakeClient(session)

        await disconnect(client, session)
        await asyncio.sleep(0.22)

        assert watchdog_state == [1]
        assert client.stop_calls == 1
        assert not client.stop_path_task_cancelled

    asyncio.run(scenario())


def test_normal_shutdown_does_not_schedule_exit(watchdog_state: list[int]) -> None:
    async def scenario() -> None:
        session = main_session()
        client = FakeClient(session)
        watchdog.ws.exit_flag = True

        await disconnect(client, session)

        assert watchdog._grace_task is None
        assert watchdog_state == []
        assert client.stop_calls == 0

    asyncio.run(scenario())


def test_media_disconnect_does_not_schedule_exit(watchdog_state: list[int]) -> None:
    async def scenario() -> None:
        session = SimpleNamespace(is_media=True)
        client = FakeClient(session)

        await disconnect(client, session)

        assert watchdog._grace_task is None
        assert watchdog_state == []
        assert client.stop_calls == 0

    asyncio.run(scenario())


def test_shutdown_during_grace_cancels_pending_task(watchdog_state: list[int]) -> None:
    async def scenario() -> None:
        session = main_session()
        client = FakeClient(session)

        await disconnect(client, session)
        grace_task = watchdog._grace_task
        watchdog.ws.exit_flag = True
        await disconnect(client, session)
        await asyncio.sleep(0.22)

        assert grace_task is not None and grace_task.cancelled()
        assert watchdog._grace_task is None
        assert watchdog_state == []
        assert client.stop_calls == 0

    asyncio.run(scenario())


def test_hanging_stop_times_out_and_exits(watchdog_state: list[int]) -> None:
    class HangingClient(FakeClient):
        async def stop(self) -> None:
            self.stop_calls += 1
            await asyncio.Event().wait()

    async def scenario() -> None:
        session = main_session()
        client = HangingClient(session)

        await disconnect(client, session)
        await asyncio.sleep(0.24)

        assert watchdog_state == [1]
        assert client.stop_calls == 1

    asyncio.run(scenario())


def test_stop_error_does_not_prevent_exit(watchdog_state: list[int]) -> None:
    class FailingClient(FakeClient):
        async def stop(self) -> None:
            self.stop_calls += 1
            raise ConnectionError("cannot stop")

    async def scenario() -> None:
        session = main_session()
        client = FailingClient(session)

        await disconnect(client, session)
        await asyncio.sleep(0.22)

        assert watchdog_state == [1]
        assert client.stop_calls == 1

    asyncio.run(scenario())


def test_recovered_connection_can_start_a_new_outage(watchdog_state: list[int]) -> None:
    async def scenario() -> None:
        session = main_session()
        client = FakeClient(session)

        await disconnect(client, session)
        first_disconnect = watchdog._disconnected_at
        await connect(client, session)
        assert first_disconnect is not None
        assert watchdog._disconnected_at is None

        await disconnect(client, session)
        await asyncio.sleep(0.22)

        assert watchdog_state == [1]
        assert client.stop_calls == 1

    asyncio.run(scenario())

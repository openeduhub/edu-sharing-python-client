"""An interrupted blocking caller must cancel its queued background work."""

import asyncio
import threading

import httpx
import pytest

from edusharing._sync import LoopThread
from edusharing.transport import Transport


def test_interrupted_wait_cancels_a_write_before_it_can_be_sent(monkeypatch):
    loop = LoopThread()
    started, finished = threading.Event(), threading.Event()
    release = asyncio.Event()
    sent = []
    submit = asyncio.run_coroutine_threadsafe

    async def queued_write():
        started.set()
        try:
            await release.wait()
            sent.append("POST")
        finally:
            finished.set()

    def interrupted_submit(coro, target):
        future = submit(coro, target)

        def interrupted_wait():
            assert started.wait(5), "background task never started"
            raise KeyboardInterrupt

        monkeypatch.setattr(future, "result", interrupted_wait)
        return future

    try:
        with monkeypatch.context() as patch:
            patch.setattr(asyncio, "run_coroutine_threadsafe", interrupted_submit)
            with pytest.raises(KeyboardInterrupt):
                loop.run(queued_write())
        # The loop processes cancellation before this barrier releases the
        # semaphore-equivalent wait. No real signal or timing race is needed.

        async def open_gate():
            await asyncio.sleep(0)
            release.set()
            await asyncio.sleep(0)

        loop.run(open_gate())
        assert finished.wait(5)
        assert sent == []
    finally:
        loop.close()


def test_interruption_before_the_background_task_starts_never_sends(monkeypatch):
    loop = LoopThread()
    occupied, release = threading.Event(), threading.Event()
    sent = []
    submit = asyncio.run_coroutine_threadsafe
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: sent.append(request.method) or httpx.Response(200, json={})))
    transport = Transport("https://repo.test/edu-sharing", client=client)

    def block_loop():
        occupied.set()
        assert release.wait(5)

    def interrupted_submit(coro, target):
        future = submit(coro, target)

        def interrupted_wait():
            raise KeyboardInterrupt

        monkeypatch.setattr(future, "result", interrupted_wait)
        return future

    try:
        loop._loop.call_soon_threadsafe(block_loop)
        assert occupied.wait(5)
        with monkeypatch.context() as patch:
            patch.setattr(asyncio, "run_coroutine_threadsafe", interrupted_submit)
            with pytest.raises(KeyboardInterrupt):
                loop.run(transport.request("POST", "/create"))
        release.set()
        loop.run(asyncio.sleep(0))
        assert sent == []
    finally:
        release.set()
        loop.run(client.aclose())
        loop.close()

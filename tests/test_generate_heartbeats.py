import pytest
import asyncio
from pytest import MonkeyPatch
from unittest.mock import AsyncMock
from server.raft_node import Node, HEARTBEAT_TIMEOUT


@pytest.mark.asyncio
async def test_generate_heartbeats_leader_sends_heartbeat(
    monkeypatch: MonkeyPatch,
) -> None:
    node = Node("node1", ["node2", "node3"])
    node.current_role = "LEADER"
    node.node_last_activity_time = 0

    # Patch time to simulate timeout
    monkeypatch.setattr("server.raft_node.time", lambda: HEARTBEAT_TIMEOUT + 1)
    # Patch replicate_log to track calls
    node.replicate_log = AsyncMock(return_value=True)

    # Patch asyncio.sleep to break the loop after one iteration
    async def fake_sleep(_: float):
        raise asyncio.CancelledError()

    monkeypatch.setattr("server.raft_node.asyncio.sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await node.generate_heartbeats()

    # Should call replicate_log for each node
    assert node.replicate_log.await_count == len(node.nodes)


@pytest.mark.asyncio
async def test_generate_heartbeats_leader_no_heartbeat(
    monkeypatch: MonkeyPatch,
) -> None:
    node = Node("node1", ["node2", "node3"])
    node.current_role = "LEADER"
    node.node_last_activity_time = 10

    # Patch time so that not enough time has passed
    monkeypatch.setattr("server.raft_node.time", lambda: 10.5)
    node.replicate_log = AsyncMock()

    # Patch asyncio.sleep to break the loop after one iteration
    async def fake_sleep(_: float):
        raise asyncio.CancelledError()

    monkeypatch.setattr("server.raft_node.asyncio.sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await node.generate_heartbeats()

    # Should not call replicate_log
    node.replicate_log.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_heartbeats_follower(monkeypatch: MonkeyPatch) -> None:
    node = Node("node1", ["node2", "node3"])
    node.current_role = "FOLLOWER"
    node.node_last_activity_time = 0

    node.replicate_log = AsyncMock()

    # Patch asyncio.sleep to break the loop after one iteration
    async def fake_sleep(_: float):
        raise asyncio.CancelledError()

    monkeypatch.setattr("server.raft_node.asyncio.sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await node.generate_heartbeats()

    # Should not call replicate_log
    node.replicate_log.assert_not_awaited()

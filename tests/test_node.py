# from urllib import request
import pytest
import asyncio
from pytest import MonkeyPatch
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Any, Coroutine
from server.raft_node import Node


@pytest.mark.asyncio
async def test_initial_state() -> None:
    node = Node("node1", ["node2", "node3"])
    assert node.node_id == "node1"
    assert node.nodes == ["node2", "node3"]
    assert node.majority == 2
    assert node.current_role == "FOLLOWER"
    assert node.node_last_activity_time is not None
    assert node.current_term == 0
    assert node.voted_for is None
    assert len(node.log) == 0
    assert node.commit_length == 0
    assert len(node.votes_received) == 0
    assert len(node.sent_length) == 0
    assert len(node.acked_length) == 0
    assert node.state_machine == "_"


@pytest.mark.asyncio
async def test_start_creates_specific_tasks(monkeypatch: MonkeyPatch) -> None:
    node = Node("node1", ["node2", "node3"])

    # Replace the methods with mocks before calling start()
    node.election_timer = AsyncMock()
    node.generate_heartbeats = AsyncMock()

    # Mock create_task to track created tasks
    created_tasks: List[Any] = []

    def track_create_task(coro: Coroutine[Any, Any, Any]) -> Any:
        # Get the coroutine name for tracking
        if hasattr(coro, "__name__"):
            created_tasks.append(coro.__name__)

        # Properly close the coroutine to prevent warnings
        if hasattr(coro, "close"):
            coro.close()

    monkeypatch.setattr(asyncio, "create_task", track_create_task)

    # Mock server setup
    with (
        patch("server.raft_node.web.AppRunner") as mock_runner,
        patch("server.raft_node.web.TCPSite") as mock_site,
    ):
        mock_runner.return_value.setup = AsyncMock()
        mock_site.return_value.start = AsyncMock()

        await node.start()

        # Verify tasks were created
        assert len(created_tasks) >= 2  # Adjust based on expected number of tasks
        # Verify server setup
        mock_runner.return_value.setup.assert_called_once()
        mock_site.return_value.start.assert_called_once()


@pytest.mark.asyncio
async def test_handle_root() -> None:
    node = Node("node1", ["node2", "node3"])

    request = MagicMock()
    resp = await node.handle_root(request)
    text = resp.text

    assert resp.status == 200
    assert text is not None, "Response text should not be None"

    assert "Role  : FOLLOWER" in text
    assert "Node  : node1" in text
    assert "Term  : 0" in text
    assert "Log   : []" in text
    assert "Commit Length : 0" in text
    assert "Sent Length   : {}" in text
    assert "Acked Length  : {}" in text
    assert "State Machine : _" in text

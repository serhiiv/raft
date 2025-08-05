import pytest
from pytest import MonkeyPatch
from unittest.mock import AsyncMock, MagicMock
from server.raft_node import Node


@pytest.mark.asyncio
async def test_handle_command_not_leader(monkeypatch: MonkeyPatch) -> None:
    node = Node("node1", ["node2", "node3"])
    node.current_role = "FOLLOWER"  # Not a leader

    # Mock request with a command
    request = MagicMock()
    request.json = AsyncMock(return_value={"command": "msg1"})
    resp = await node.handle_command(request)

    # Handle potential None value from resp.text
    text = resp.text
    assert text is not None, "Response text should not be None"
    assert "ERROR: I am not a LEADER, cannot process command" in text
    # Log should not be modified
    assert len(node.log) == 0


@pytest.mark.asyncio
async def test_handle_command_leader_success(monkeypatch: MonkeyPatch) -> None:
    node = Node("node1", ["node2", "node3"])
    node.current_role = "LEADER"
    node.current_term = 1
    node.acked_length = {"node1": 0, "node2": 0, "node3": 0}
    node.sent_length = {"node2": 0, "node3": 0}
    node.majority = 2

    # Patch replicate_log to always succeed
    node.replicate_log = AsyncMock(return_value=True)

    # Mock request with a command
    request = MagicMock()
    request.json = AsyncMock(return_value={"command": "msg1"})

    resp = await node.handle_command(request)

    # Handle potential None value from resp.text
    text = resp.text
    assert text is not None, "Response text should not be None"
    assert "OK: Command 'msg1' added to log" in text
    assert node.log[-1] == (1, "msg1")


@pytest.mark.asyncio
async def test_handle_command_leader_no_quorum(monkeypatch: MonkeyPatch) -> None:
    node = Node("node1", ["node2", "node3"])
    node.current_role = "LEADER"
    node.current_term = 1
    node.acked_length = {"node1": 0, "node2": 0, "node3": 0}
    node.sent_length = {"node2": 0, "node3": 0}
    node.majority = 2  # Require majority for quorum

    # Patch replicate_log: only one follower succeeds
    results = False
    node.replicate_log = AsyncMock(return_value=results)

    # Mock request with a command
    request = MagicMock()
    request.json = AsyncMock(return_value={"command": "msg1"})
    resp = await node.handle_command(request)

    text = resp.text
    assert text is not None, "Response text should not be None"
    assert "ERROR: Not enough quorum to commit the command" in text
    # Command should still be added to log even without quorum
    assert node.log[-1] == (1, "msg1")


@pytest.mark.asyncio
async def test_handle_command_empty_command(monkeypatch: MonkeyPatch) -> None:
    node = Node("node1", ["node2", "node3"])
    node.current_role = "LEADER"

    # Mock request with empty command
    request = MagicMock()
    request.json = AsyncMock(return_value={"command": ""})
    resp = await node.handle_command(request)

    text = resp.text
    assert text is not None, "Response text should not be None"
    assert "ERROR: No command" in text
    # Log should not be modified
    assert len(node.log) == 0

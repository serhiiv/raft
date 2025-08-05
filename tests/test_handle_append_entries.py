import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from server.raft_node import Node


@pytest.fixture
def node():
    # Create a Node with id 'node1' and two followers
    node = Node("node1", ["node2", "node3"])
    node.current_term = 2
    node.current_role = "FOLLOWER"
    node.log = [(1, "msg1"), (2, "msg2")]
    node.commit_length = 1
    return node


@pytest.mark.asyncio
async def test_handle_append_entries_higher_term(node: Node) -> None:
    # Incoming term is higher than current_term
    request_data = dict(
        term=3,
        leader_id="node2",
        log_length=2,
        log_term=2,
        entries=[],
        leader_commit=1,
    )

    request = MagicMock()
    request.json = AsyncMock(return_value=request_data)
    resp = await node.handle_append_entries(request)
    response_text = getattr(resp, "text", "{}")
    data = json.loads(response_text)

    assert node.current_term == 3
    assert node.current_role == "FOLLOWER"
    assert node.current_leader == "node2"
    assert data["success"] is True
    assert data["term"] == 3
    assert data["ack"] == 2


@pytest.mark.asyncio
async def test_handle_append_entries_candidate_to_follower(node: Node) -> None:
    # Node is CANDIDATE, term matches, should become FOLLOWER
    node.current_role = "CANDIDATE"
    node.current_term = 5
    request_data = dict(
        term=5,
        leader_id="node2",
        log_length=2,
        log_term=2,
        entries=[],
        leader_commit=2,
    )

    request = MagicMock()
    request.json = AsyncMock(return_value=request_data)
    resp = await node.handle_append_entries(request)
    response_text = getattr(resp, "text", "{}")
    data = json.loads(response_text)

    assert node.current_role == "FOLLOWER"
    assert node.current_leader == "node2"
    assert data["success"] is True
    assert data["term"] == 5
    assert data["ack"] == 2


@pytest.mark.asyncio
async def test_handle_append_entries_log_ok_and_append(node: Node) -> None:
    # Should append entries and return success
    node.current_term = 4
    node.current_role = "FOLLOWER"
    node.log = [(1, "msg1"), (4, "msg2")]
    request_data = dict(
        term=4,
        leader_id="node2",
        log_length=2,
        log_term=4,
        entries=[(4, "msg3"), (4, "msg4")],
        leader_commit=3,
    )

    request = MagicMock()
    request.json = AsyncMock(return_value=request_data)
    resp = await node.handle_append_entries(request)
    response_text = getattr(resp, "text", "{}")
    data = json.loads(response_text)

    assert data["success"] is True
    assert data["ack"] == 4
    assert node.log == [(1, "msg1"), (4, "msg2"), (4, "msg3"), (4, "msg4")]
    assert node.commit_length == 3


@pytest.mark.asyncio
async def test_handle_append_entries_log_not_ok(node: Node) -> None:
    # log_term does not match, should return failure
    node.current_term = 4
    node.current_role = "FOLLOWER"
    node.log = [(1, "msg1"), (3, "msg2")]
    request_data = dict(
        term=4,
        leader_id="node2",
        log_length=2,
        log_term=4,  # does not match node.log[1][0] == 3
        entries=[],
        leader_commit=1,
    )

    request = MagicMock()
    request.json = AsyncMock(return_value=request_data)
    resp = await node.handle_append_entries(request)
    response_text = getattr(resp, "text", "{}")
    data = json.loads(response_text)

    assert data["success"] is False
    assert data["ack"] == 0


@pytest.mark.asyncio
async def test_handle_append_entries_term_too_low(node: Node) -> None:
    # Incoming term is lower than current_term, should fail
    node.current_term = 5
    node.current_role = "FOLLOWER"
    request_data = dict(
        term=4,
        leader_id="node2",
        log_length=2,
        log_term=2,
        entries=[],
        leader_commit=1,
    )

    request = MagicMock()
    request.json = AsyncMock(return_value=request_data)
    resp = await node.handle_append_entries(request)
    response_text = getattr(resp, "text", "{}")
    data = json.loads(response_text)

    assert data["success"] is False
    assert data["term"] == 5
    assert data["ack"] == 0

import pytest
import json
from unittest.mock import MagicMock, AsyncMock
from server.raft_node import Node


@pytest.fixture
def node():
    node = Node("node1", ["node2", "node3"])
    node.node_last_activity_time = 0  # for determinism
    return node


@pytest.mark.asyncio
async def test_handle_request_vote_grants_vote_on_fresh_term_and_log(
    node: Node,
) -> None:
    # No log entries, no vote yet
    request_data = dict(
        term=1,
        candidate_id="node2",
        last_log_index=0,
        last_log_term=0,
    )

    request = MagicMock()
    request.json = AsyncMock(return_value=request_data)
    resp = await node.handle_request_vote(request)
    response_text = getattr(resp, "text", "{}")
    data = json.loads(response_text)

    assert data["vote_granted"] is True
    assert data["node_id"] == "node1"
    assert data["term"] == 1
    assert node.current_term == 1
    assert node.voted_for == "node2"
    assert node.current_role == "FOLLOWER"


@pytest.mark.asyncio
async def test_handle_request_vote_rejects_if_log_outdated(node: Node) -> None:
    # Node has a log entry with term 2
    node.log = [(2, "msg1")]
    node.current_term = 2
    node.voted_for = None

    request_data = dict(
        term=2,
        candidate_id="node2",
        last_log_index=0,
        last_log_term=1,  # Lower than node's last log term
    )

    request = MagicMock()
    request.json = AsyncMock(return_value=request_data)
    resp = await node.handle_request_vote(request)
    response_text = getattr(resp, "text", "{}")
    data = json.loads(response_text)

    assert data["vote_granted"] is False
    assert data["node_id"] == ""
    assert node.voted_for is None


@pytest.mark.asyncio
async def test_handle_request_vote_rejects_if_already_voted(node: Node) -> None:
    node.current_term = 3
    node.voted_for = "node3"
    node.log = [(3, "msg1")]

    request_data = dict(
        term=3,
        candidate_id="node2",
        last_log_index=1,
        last_log_term=3,  # Same term as node's current term
    )

    request = MagicMock()
    request.json = AsyncMock(return_value=request_data)
    resp = await node.handle_request_vote(request)
    response_text = getattr(resp, "text", "{}")
    data = json.loads(response_text)

    assert data["vote_granted"] is False
    assert data["node_id"] == ""
    assert node.voted_for == "node3"


@pytest.mark.asyncio
async def test_handle_request_vote_grants_vote_if_not_yet_voted(node: Node) -> None:
    node.current_term = 4
    node.voted_for = None
    node.log = [(4, "msg1")]

    request_data = dict(
        term=4,
        candidate_id="node2",
        last_log_index=1,
        last_log_term=4,  # Same term as node's current term
    )

    request = MagicMock()
    request.json = AsyncMock(return_value=request_data)
    resp = await node.handle_request_vote(request)
    response_text = getattr(resp, "text", "{}")
    data = json.loads(response_text)

    assert data["vote_granted"] is True
    assert data["node_id"] == "node1"
    assert node.voted_for == "node2"


@pytest.mark.asyncio
async def test_handle_request_vote_updates_term_and_role(node: Node) -> None:
    node.current_term = 2
    node.current_role = "LEADER"
    node.voted_for = None
    node.log = [(2, "msg1")]

    # Candidate has a higher term
    request_data = dict(
        term=3,
        candidate_id="node2",
        last_log_index=1,
        last_log_term=2,
    )

    request = MagicMock()
    request.json = AsyncMock(return_value=request_data)
    resp = await node.handle_request_vote(request)
    response_text = getattr(resp, "text", "{}")
    data = json.loads(response_text)

    assert node.current_term == 3
    assert node.current_role == "FOLLOWER"
    assert node.voted_for == "node2"
    assert data["vote_granted"] is True

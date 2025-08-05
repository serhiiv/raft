import pytest
from aioresponses import aioresponses
from unittest.mock import patch
from server.raft_node import Node


@pytest.fixture
def node() -> Node:
    node = Node("node1", ["node2", "node3"])
    node.current_role = "LEADER"
    node.current_term = 2
    node.log = [(1, "msg1"), (2, "msg2")]
    node.sent_length = {"node2": 1, "node3": 2}
    node.acked_length = {"node1": 2, "node2": 1, "node3": 0}
    node.commit_length = 0
    node.majority = 2
    node.state_machine = "_"
    return node

    # log_length=1
    # log_term=1
    # leader_commit=0
    # entries=[(2, "msg2")]


@pytest.mark.asyncio
async def test_replicate_log_successful_update_simple(node: Node) -> None:
    response = dict(term=2, ack=2, success=True)

    with aioresponses() as mock:
        # Mock the HTTP request
        mock.post("http://node2:8080/append_entries", payload=response)  # type: ignore

        result = await node.replicate_log("node2")

        assert result is True
        assert node.sent_length["node2"] == 2
        assert node.acked_length["node2"] == 2
        assert node.commit_length == 2
        assert node.state_machine == "_msg1_msg2_"


@pytest.mark.asyncio
async def test_replicate_log_higher_term(node: Node) -> None:
    # Simulate follower responds with higher term
    response = dict(term=3, ack=0, success=False)

    with aioresponses() as mock:
        # Mock the HTTP request
        mock.post("http://node2:8080/append_entries", payload=response)  # type: ignore

        result = await node.replicate_log("node2")

        assert result is True
        assert node.current_term == 3
        assert node.current_role == "FOLLOWER"
        assert node.voted_for is None


@pytest.mark.asyncio
async def test_replicate_log_unsuccessful(node: Node) -> None:
    # Simulate follower responds with unsuccessful, sent_length > 0, triggers retry
    response = dict(term=2, ack=0, success=False)

    with aioresponses() as mock:
        # Mock the HTTP request
        response = dict(term=2, ack=0, success=False)
        mock.post("http://node2:8080/append_entries", payload=response)  # type: ignore
        result = await node.replicate_log("node2")

        assert result is True
        assert node.sent_length["node2"] == 0


@pytest.mark.asyncio
async def test_replicate_log_exception_returns_false(node: Node) -> None:
    with patch(
        "server.raft_node.ClientSession", side_effect=Exception("network error")
    ):
        result = await node.replicate_log("node2")
        assert result is False

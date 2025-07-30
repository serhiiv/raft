import pytest
import pytest_asyncio
from aiohttp import web
from typing import Any, AsyncGenerator

from server.raft_node import Node


@pytest.fixture
def node_id() -> str:
    return "node-1"


@pytest.fixture
def nodes() -> list[str]:
    return ["node-2", "node-3"]


@pytest_asyncio.fixture
async def node(node_id: str, nodes: list[str]) -> AsyncGenerator[Node, None]:
    node = Node(node_id, nodes)
    yield node


@pytest_asyncio.fixture
async def app() -> web.Application:
    node = Node("node-1", ["node-2", "node-3"])
    return node.app


@pytest_asyncio.fixture
async def client(aiohttp_client: Any, app: web.Application) -> Any:
    return await aiohttp_client(app)


@pytest.mark.asyncio
async def test_initial_state(node: Node) -> None:
    assert node.node_id == "node-1"
    assert node.nodes == ["node-2", "node-3"]
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
async def test_handle_command_not_leader(client: Any) -> None:
    resp = await client.post("/", json={"command": "test"})
    assert resp.status == 200
    text = await resp.text()
    assert "ERROR: I am not a LEADER" in text


# @pytest.mark.asyncio
# async def test_handle_request_vote(client: Any) -> None:
#     request_data = {
#         "term": 1,
#         "candidate_id": "node-2",
#         "last_log_index": 0,
#         "last_log_term": 0
#     }
#     resp = await client.post('/request_vote', json=request_data)
#     assert resp.status == 200
#     data = await resp.json()
#     assert data["term"] == 1
#     assert data["vote_granted"] == True

# @pytest.mark.asyncio
# async def test_handle_append_entries(client: Any) -> None:
#     request_data = {
#         "term": 1,
#         "leader_id": "node-2",
#         "log_length": 0,
#         "log_term": 0,
#         "entries": [(1, "test")],
#         "leader_commit": 0
#     }
#     resp = await client.post('/append_entries', json=request_data)
#     assert resp.status == 200
#     data = await resp.json()
#     assert data["term"] == 1
#     assert data["success"] == True

#     assert node.current_term == 1

# @pytest.mark.asyncio
# async def test_append_entries(node):
#     entries = [(1, "test")]
#     node.append_entries(0, 1, entries)
#     assert node.log == entries
#     assert node.commit_length == 1
#     assert node.state_machine == "test"


@pytest.mark.asyncio
async def test_commit_log_entries_0(node: Node) -> None:
    # Setup
    node.current_role = "LEADER"
    node.current_term = 1
    node.log = [(1, "test1")]
    node.acked_length = {"node-1": 1, "node-2": 0, "node-3": 0}

    # Test
    node.commit_log_entries()
    assert node.commit_length == 0
    assert node.state_machine == "_"



@pytest.mark.asyncio
async def test_commit_log_entries_1(node: Node) -> None:
    # Setup
    node.current_role = "LEADER"
    node.current_term = 1
    node.log = [(1, "test1")]
    node.acked_length = {"node-1": 1, "node-2": 1, "node-3": 0}

    # Test
    node.commit_log_entries()
    assert node.commit_length == 1
    assert node.state_machine == "_test1_"


@pytest.mark.asyncio
async def test_commit_log_entries_2(node: Node) -> None:
    # Setup
    node.current_role = "LEADER"
    node.current_term = 1
    node.log = [(1, "test1"), (1, "test2")]
    node.acked_length = {"node-1": 2, "node-2": 1, "node-3": 2}

    # Test
    node.commit_log_entries()
    assert node.commit_length == 2
    assert node.state_machine == "_test1_test2_"


@pytest.mark.asyncio
async def test_handle_root(client: Any) -> None:
    resp = await client.get("/")
    assert resp.status == 200
    text = await resp.text()
    assert "Role: FOLLOWER" in text
    assert "Node: node-1" in text
    assert "Term: 0" in text
    assert "Log : []" in text
    assert "Commit Length: 0" in text
    assert "Sent Length: {}" in text
    assert "Acked Length: {}" in text
    assert "State Machine: _" in text

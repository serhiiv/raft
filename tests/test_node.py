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
async def test_handle_root(client: Any) -> None:
    resp = await client.get("/")
    assert resp.status == 200
    text = await resp.text()
    assert "Role  : FOLLOWER" in text
    assert "Node  : node-1" in text
    assert "Term  : 0" in text
    assert "Log   : []" in text
    assert "Commit Length : 0" in text
    assert "Sent Length   : {}" in text
    assert "Acked Length  : {}" in text
    assert "State Machine : _" in text

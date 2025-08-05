import pytest
from pytest import MonkeyPatch
from unittest.mock import AsyncMock, patch
from server.raft_node import Node, ResponseVote, RequestVote


@pytest.fixture
def node():
    # Create a Node with node_id 'n1' and two other nodes
    node = Node("node1", ["node2", "node3"])
    node.node_last_activity_time = 0  # for determinism
    return node


@pytest.mark.asyncio
async def test_election_timer_becomes_candidate(
    monkeypatch: MonkeyPatch, node: Node
) -> None:
    node.current_role = "FOLLOWER"
    node.node_last_activity_time = 0  # Simulate old activity time

    # Patch time to simulate timeout
    monkeypatch.setattr("server.raft_node.time", lambda: 100)
    # Patch election to avoid infinite loop
    node.election = AsyncMock()

    # Run only one iteration of the loop
    with patch("asyncio.sleep", new=AsyncMock(side_effect=Exception("break"))):
        try:
            await node.election_timer()
        except Exception as e:
            assert str(e) == "break"

    assert node.current_role == "CANDIDATE"
    node.election.assert_awaited_once()


@pytest.mark.asyncio
async def test_election_timer_no_election(monkeypatch: MonkeyPatch, node: Node) -> None:
    node.current_role = "FOLLOWER"
    node.node_last_activity_time = 100  # Simulate recent activity

    # Patch time to simulate no timeout
    monkeypatch.setattr("server.raft_node.time", lambda: 101)
    node.election = AsyncMock()

    # Run only one iteration of the loop
    with patch("asyncio.sleep", new=AsyncMock(side_effect=Exception("break"))):
        try:
            await node.election_timer()
        except Exception as e:
            assert str(e) == "break"

    # Should remain follower - no election started
    assert node.current_role == "FOLLOWER"
    node.election.assert_not_awaited()


@pytest.mark.asyncio
async def test_election_timer_not_follower(
    monkeypatch: MonkeyPatch, node: Node
) -> None:
    node.current_role = "LEADER"  # Not a follower
    node.node_last_activity_time = 0  # Old activity time

    # Patch time to simulate timeout
    monkeypatch.setattr("server.raft_node.time", lambda: 100)
    node.election = AsyncMock()

    # Run only one iteration of the loop
    with patch("asyncio.sleep", new=AsyncMock(side_effect=Exception("break"))):
        try:
            await node.election_timer()
        except Exception as e:
            assert str(e) == "break"

    # Should remain leader - no election for non-followers
    assert node.current_role == "LEADER"
    node.election.assert_not_awaited()


@pytest.mark.asyncio
async def test_election_becomes_leader(monkeypatch: MonkeyPatch, node: Node) -> None:
    # Setup node with 2 followers (majority is 2)
    node.current_role = "CANDIDATE"
    node.current_term = 1
    node.log = [(1, "msg1")]

    # Mock post_request_vote to grant votes from both followers
    async def mock_post_request_vote(
        node_id: str, request_data: RequestVote
    ) -> ResponseVote:
        return ResponseVote(
            node_id=node_id,
            term=request_data["term"],
            vote_granted=True,
        )

    monkeypatch.setattr(node, "post_request_vote", mock_post_request_vote)

    await node.election()

    assert node.current_role == "LEADER"
    assert node.current_leader == "node1"
    assert node.voted_for == "node1"
    assert node.current_term == 2
    for n in node.nodes:
        assert node.sent_length[n] == len(node.log)
        assert node.acked_length[n] == 0


@pytest.mark.asyncio
async def test_election_becomes_follower_on_higher_term(
    monkeypatch: MonkeyPatch, node: Node
) -> None:
    node.current_role = "CANDIDATE"
    node.current_term = 1

    # Mock post_request_vote to return higher term
    async def mock_post_request_vote(
        node_id: str, request_data: RequestVote
    ) -> ResponseVote:
        return ResponseVote(
            node_id=node_id,
            term=request_data["term"] + 1,
            vote_granted=False,
        )

    monkeypatch.setattr(node, "post_request_vote", mock_post_request_vote)

    await node.election()

    assert node.current_role == "FOLLOWER"
    assert node.current_term == 3  # incremented in election, then set to 5 by response
    assert node.voted_for is None


@pytest.mark.asyncio
async def test_election_no_quorum(monkeypatch: MonkeyPatch, node: Node) -> None:
    node.current_role = "CANDIDATE"
    node.current_term = 1

    # Only one vote granted (not enough for majority)
    async def mock_post_request_vote(
        node_id: str, request_data: RequestVote
    ) -> ResponseVote:
        return ResponseVote(
            node_id=node_id,
            term=request_data["term"],
            vote_granted=False,
        )

    monkeypatch.setattr(node, "post_request_vote", mock_post_request_vote)

    # Patch asyncio.sleep to break the election loop after one round
    with patch("server.raft_node.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        # Set current_role to something else after first round to exit loop
        async def set_follower(timeout: float) -> None:
            node.current_role = "FOLLOWER"

        mock_sleep.side_effect = set_follower

        await node.election()

    assert node.current_role == "FOLLOWER"
    assert node.current_term == 2
    assert node.current_leader == ""
    assert node.voted_for == "node1"
    assert node.votes_received == set(["node1"])


@pytest.mark.asyncio
async def test_post_request_vote_exception(node: Node) -> None:
    node.current_term = 2
    request_data = RequestVote(
        term=2,
        candidate_id="node1",
        last_log_index=0,
        last_log_term=0,
    )

    # Patch ClientSession to raise an exception
    with patch("server.raft_node.ClientSession") as mock_session:
        mock_session.return_value.__aenter__.side_effect = Exception("Network error")

        resp = await node.post_request_vote("node2", request_data)
        assert resp["node_id"] == ""
        assert resp["term"] == node.current_term
        assert resp["vote_granted"] is False

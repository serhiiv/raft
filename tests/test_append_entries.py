import pytest
from server.raft_node import Node


@pytest.fixture
def node():
    node = Node("node1", ["node2", "node3"])
    node.current_term = 1
    node.state_machine = "_"
    return node


def test_append_entries_appends_new_entries(node: Node) -> None:
    node.log = [(1, "msg1")]
    node.commit_length = 0
    entries = [(1, "msg2"), (1, "msg3")]
    node.append_entries(log_length=1, leader_commit=0, entries=entries)
    assert node.log == [(1, "msg1"), (1, "msg2"), (1, "msg3")]


def test_append_entries_truncates_conflicting_entries(node: Node) -> None:
    node.log = [(1, "msg1"), (2, "msg2"), (2, "msg3")]
    node.commit_length = 0
    # New entry at index 1 with different term, should truncate log from index 1
    entries = [(3, "msgX"), (3, "msgY")]
    node.append_entries(log_length=1, leader_commit=0, entries=entries)
    assert node.log == [(1, "msg1"), (3, "msgX"), (3, "msgY")]


def test_append_entries_no_entries_no_change(node: Node) -> None:
    node.log = [(1, "msg1"), (2, "msg2")]
    node.commit_length = 0
    node.append_entries(log_length=2, leader_commit=0, entries=[])
    assert node.log == [(1, "msg1"), (2, "msg2")]


def test_append_entries_commit_length_and_state_machine(node: Node) -> None:
    node.log = [(1, "msg1"), (1, "msg2"), (1, "msg3")]
    node.commit_length = 0
    node.state_machine = "_"
    node.append_entries(log_length=3, leader_commit=2, entries=[])
    assert node.commit_length == 2
    # state_machine should have applied "msg1" and "msg2"
    assert node.state_machine == "_msg1_msg2_"


def test_append_entries_commit_length_does_not_decrease(node: Node) -> None:
    node.log = [(1, "msg1"), (1, "msg2"), (1, "msg3")]
    node.commit_length = 2
    node.state_machine = "_msg1_msg2_"
    node.append_entries(log_length=3, leader_commit=1, entries=[])
    # commit_length should not decrease
    assert node.commit_length == 2
    assert node.state_machine == "_msg1_msg2_"


def test_append_entries_partial_truncate_and_append(node: Node) -> None:
    node.log = [(1, "msg1"), (2, "msg2"), (2, "msg3")]
    node.commit_length = 0
    # Truncate at index 1, then append new entries
    entries = [(3, "msgX"), (3, "msgY")]
    node.append_entries(log_length=1, leader_commit=0, entries=entries)
    assert node.log == [(1, "msg1"), (3, "msgX"), (3, "msgY")]

import os
import random
import logging
import asyncio
from time import time
from typing import TypedDict, List, Tuple, Dict, Set, Optional
from aiohttp import web, ClientSession, ClientTimeout


class RequestVote(TypedDict):
    term: int
    candidate_id: str
    last_log_index: int
    last_log_term: int


class ResponseVote(TypedDict):
    node_id: str
    term: int
    vote_granted: bool


class RequestAppend(TypedDict):
    term: int
    leader_id: str
    log_length: int
    log_term: int
    entries: List[Tuple[int, str]]
    leader_commit: int


class ResponseAppend(TypedDict):
    term: int
    ack: int
    success: bool


HEARTBEAT_TIMEOUT = float(os.getenv("HEARTBEAT_TIMEOUT", 1.0))
ELECTION_TIMEOUT = float(os.getenv("ELECTION_TIMEOUT", 5.0))


logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s.%(msecs)03d  %(funcName)s -  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class Node:
    def __init__(self, node_id: str, nodes: List[str]):
        ### Node state
        self.node_id: str = node_id
        self.nodes: List[str] = nodes
        self.majority: int = (len(nodes) + 2) // 2
        self.current_role: str = "FOLLOWER"  # FOLLOWER, CANDIDATE, LEADER
        self.node_last_activity_time: float = time()

        ### Persistent current_role on all nodes: (Updated on stable storage before responding to RPCs)
        # self.current_term - latest term node has seen (initialized to 0 on first boot, increases monotonically)
        # self.voted_for - candidateId that received vote in current term (or null if none)
        # self.log - log[] log entries; each entry contains command for state machine, and term when entry was received by leader (first index is 1)Each log entry: {"term": int, "index": int, "command": str}
        self.current_term: int = 0
        self.voted_for: Optional[str] = None
        self.log: List[Tuple[int, str]] = []  # Each log entry: (term, command)

        ### Volatile state on all nodes:
        # # self.commit_index - index of highest log entry known to be committed (initialized to 0, increases monotonically)
        # # self.last_applied - index of highest log entry applied to state machine (initialized to 0, increases monotonically)
        # self.commit_index: int = 0
        # self.last_applied: int = 0

        # ### Volatile state on leaders: (Reinitialized after election)
        # # self.next_index - for each node, index of the next log entry to send to that node (initialized to leader last log index + 1)
        # # self.match_index - index of highest log entry known to be replicated on each node (initialized to 0, increases monotonically)
        # self.next_index: dict[str, int] = {node: 0 for node in nodes}
        # self.match_index: dict[str, int] = {node: 0 for node in nodes}

        self.commit_length: int = 0
        self.current_leader: str = ""
        self.votes_received: Set[str] = set()
        self.sent_length: Dict[str, int] = {}
        self.acked_length: Dict[str, int] = {}

        self.state_machine: str = "_"

        ### Web application setup
        self.app = web.Application()
        self.app.add_routes(
            [
                web.get("/", self.handle_root),
                web.post("/", self.handle_command),
                web.post("/request_vote", self.handle_request_vote),
                web.post("/append_entries", self.handle_append_entries),
            ]
        )
        self.command_lock = asyncio.Semaphore(1)  # Add semaphore for commands

    async def start(self):
        """Start the Raft node."""
        logger.warning(f"I start as {self.current_role} for term {self.current_term}")
        logger.warning(f"My neighbor nodes {self.nodes}")
        asyncio.create_task(self.check_election_timer())
        asyncio.create_task(self.generate_heartbeats())
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner)
        await site.start()

    async def check_election_timer(self):
        """Check election timeout and start election if needed."""
        while True:
            if self.current_role == "FOLLOWER":
                if (time() - self.node_last_activity_time) > ELECTION_TIMEOUT:
                    self.current_role = "CANDIDATE"
                    logger.warning("I am CANDIDATE")
                    await self.start_election()
            await asyncio.sleep(HEARTBEAT_TIMEOUT)

    async def start_election(self) -> None:
        """Start an election and request votes from other nodes."""
        while True:
            if self.current_role == "CANDIDATE":
                self.current_term += 1
                self.voted_for = self.node_id
                self.votes_received = set([self.node_id])

                request_data = RequestVote(
                    term=self.current_term,
                    candidate_id=self.node_id,
                    last_log_index=len(self.log),
                    last_log_term=self.log[-1][0] if self.log else 0,
                )

                logger.warning(
                    f"I started election for term {self.current_term} and voted for myself"
                )
                for resp in asyncio.as_completed(
                    [self.post_request_vote(node, request_data) for node in self.nodes]
                ):
                    data = await resp

                    if (
                        self.current_role == "CANDIDATE"
                        and data["term"] == self.current_term
                        and data["vote_granted"]
                    ):
                        self.votes_received.add(data["node_id"])
                        if len(self.votes_received) >= self.majority:
                            self.current_role = "LEADER"
                            self.current_leader = self.node_id
                            self.node_last_activity_time = time()

                            for node in self.nodes:
                                self.sent_length[node] = len(self.log)
                                self.acked_length[node] = 0
                                # ReplicateLog(nodeId, follower )

                            logger.warning(f"I am LEADER for term {self.current_term}")
                            return

                    elif data["term"] > self.current_term:
                        self.current_term = data["term"]
                        self.current_role = "FOLLOWER"
                        self.voted_for = None
                        logger.warning(f"I am FOLLOWER for term {self.current_term}")
                        self.node_last_activity_time = time()
                        return

                await asyncio.sleep(
                    random.uniform(ELECTION_TIMEOUT, ELECTION_TIMEOUT * 2)
                )
            else:
                return

    async def post_request_vote(
        self, node: str, request_data: RequestVote
    ) -> ResponseVote:
        url = f"http://{node}:8080/request_vote"
        logging.warning(f"RequestVote with term {request_data['term']} to '{url}'")
        try:
            async with ClientSession() as session:
                async with session.post(
                    url, json=request_data, timeout=ClientTimeout(HEARTBEAT_TIMEOUT)
                ) as resp:
                    data: ResponseVote = await resp.json()
                    return data
        except Exception:
            logging.warning(
                f"FAILED RequestVote with term {request_data['term']} to '{url}'"
            )
            return ResponseVote(
                node_id="",
                term=self.current_term,
                vote_granted=False,
            )

    async def handle_request_vote(self, request: web.Request) -> web.Response:
        """Handle RequestVote RPC."""
        data: RequestVote = await request.json()
        self.node_last_activity_time = time()

        log_term = self.log[len(self.log) - 1][0] if self.log else 0

        log_ok = (data["last_log_term"] > log_term) or (
            data["last_log_term"] == log_term
            and data["last_log_index"] >= len(self.log)
        )
        term_ok = (data["term"] > log_term) or (
            data["last_log_term"] == log_term
            and self.voted_for in (data["candidate_id"], None)
        )
        if log_ok and term_ok:
            self.current_term = data["term"]
            self.current_role = "FOLLOWER"
            self.voted_for = data["candidate_id"]
            vote_granted = True
            logger.warning(f"I am FOLLOWER for term {self.current_term}")
        else:
            vote_granted = False

        return web.json_response(
            ResponseVote(
                node_id=self.node_id if vote_granted else "",
                term=self.current_term,
                vote_granted=vote_granted,
            )
        )

    async def generate_heartbeats(self):
        while True:
            if self.current_role == "LEADER":
                if (time() - self.node_last_activity_time) > HEARTBEAT_TIMEOUT:
                    logger.info("Sent heartbeat")
                    self.node_last_activity_time = time()
                    for resp in asyncio.as_completed(
                        [self.replicate_log(node) for node in self.nodes]
                    ):
                        await resp
                else:
                    await asyncio.sleep(
                        self.node_last_activity_time + HEARTBEAT_TIMEOUT - time()
                    )
            else:
                await asyncio.sleep(HEARTBEAT_TIMEOUT)

    async def handle_append_entries(self, request: web.Request) -> web.Response:
        data: RequestAppend = await request.json()
        self.node_last_activity_time = time()

        if data["term"] > self.current_term:
            # If the term in the request is greater than the current term,
            # update the current term and role, and reset voted_for.
            self.current_term = data["term"]
            self.voted_for = None
            self.current_role = "FOLLOWER"
            self.current_leader = data["leader_id"]
            logger.warning(f"I am FOLLOWER for term {self.current_term}")

        if data["term"] == self.current_term and self.current_role == "CANDIDATE":
            # If the term is equal to the current term and the role is CANDIDATE,
            # convert to FOLLOWER and set the current leader.
            self.current_role = "FOLLOWER"
            self.current_leader = data["leader_id"]
            logger.warning(f"I am FOLLOWER for term {self.current_term}")

        log_term = self.log[data["log_length"] - 1][0] if data["log_length"] > 0 else 0
        log_ok = (len(self.log) >= data["log_length"]) and (
            data["log_length"] == 0 or log_term == data["log_term"]
        )

        if data["term"] == self.current_term and log_ok:
            self.append_entries(
                data["log_length"], data["leader_commit"], data["entries"]
            )
            ack = data["log_length"] + len(data["entries"])
            return web.json_response(
                ResponseAppend(
                    term=self.current_term,
                    ack=ack,
                    success=True,
                )
            )
        else:
            bad = ResponseAppend(term=self.current_term, ack=0, success=False)
            return web.json_response(bad)

    def append_entries(
        self, log_length: int, leader_commit: int, entries: list[tuple[int, str]]
    ) -> None:
        """This function checks if the log length is valid, appends new entries, and updates the commit index."""
        if len(entries) > 0 and len(self.log) > log_length:
            if self.log[log_length][0] != entries[0][0]:
                self.log = self.log[:log_length]
        if log_length + len(entries) > len(self.log):
            for entry in entries:
                self.log.append((entry[0], entry[1]))
        if leader_commit > self.commit_length:
            for i in range(self.commit_length, leader_commit):
                self.state_machine += self.log[i][1] + "_"
            self.commit_length = leader_commit

    async def handle_command(self, request: web.Request) -> web.Response:
        async with self.command_lock:  # Ensure only one command processes at a time
            request_data = await request.json()

            if self.current_role == "LEADER":
                command: str = request_data.get("command", "")
                if command:
                    self.log.append((self.current_term, command))
                    self.acked_length[self.node_id] = len(self.log)

                    logger.warning(f"Send commands '{command}'")

                    # Create replication tasks for all nodes
                    replication_tasks = [
                        self.replicate_log(node) for node in self.nodes
                    ]

                    quorum: int = 1  # Start with 1 for the leader itself
                    # Wait for all replications to complete
                    for resp in asyncio.as_completed(replication_tasks):
                        data: bool = await resp
                        quorum += int(data)
                    if quorum >= self.majority:
                        text = f"OK: Command '{command}' added to log"
                    else:
                        text = "ERROR: Not enough quorum to commit the command"
                else:
                    text = "ERROR: No command"
            else:
                text = "ERROR: I am not a LEADER, cannot process command"
            return web.Response(text=text)

    async def replicate_log(self, follower_id: str) -> bool:
        """Replicate log entries to a follower node."""
        log_length = self.sent_length[follower_id]
        request_data = RequestAppend(
            leader_id=self.node_id,
            term=self.current_term,
            log_length=log_length,
            log_term=self.log[log_length - 1][0] if log_length > 0 else 0,
            leader_commit=self.commit_length,
            entries=self.log[log_length:],
        )
        # (LogRequest, leaderId, currentTerm, i, prevLogTerm, commitLength, entries)
        # (LogRequest, leaderId, term, logLength, logTerm, leaderCommit, entries)
        url = f"http://{follower_id}:8080/append_entries"
        try:
            # logging.warning(
            #     f"POST Replicate log to '{follower_id}' with {request_data}"
            # )
            async with ClientSession() as session:
                async with session.post(
                    url, json=request_data, timeout=ClientTimeout(HEARTBEAT_TIMEOUT)
                ) as resp:
                    data: ResponseAppend = await resp.json()

                    # Process the response from the follower
                    if (
                        data["term"] == self.current_term
                        and self.current_role == "LEADER"
                    ):
                        if (
                            data["success"]
                            and data["ack"] >= self.acked_length[follower_id]
                        ):
                            # Update sent and acked lengths
                            self.sent_length[follower_id] = data["ack"]
                            self.acked_length[follower_id] = data["ack"]
                            self.commit_log_entries()
                        elif self.sent_length[follower_id] > 0:
                            # Decrease sent length and retry replication
                            self.sent_length[follower_id] -= 1
                            await self.replicate_log(follower_id)
                    elif data["term"] > self.current_term:
                        # If the term in the response is greater, update current term and role
                        self.current_term = data["term"]
                        self.current_role = "FOLLOWER"
                        self.voted_for = None
                        logger.warning(f"I am FOLLOWER for term {self.current_term}")
        except Exception:
            return False
        return True

    def commit_log_entries(self):
        def acks(length: int) -> int:
            return len({k for k, v in self.acked_length.items() if v >= length})

        ready = {r for r in range(1, len(self.log) + 1) if acks(r) >= self.majority}
        if (
            ready
            and max(ready) > self.commit_length
            and self.log[max(ready) - 1][0] == self.current_term
        ):
            for i in range(self.commit_length, max(ready)):
                self.state_machine += self.log[i][1] + "_"
            self.commit_length = max(ready)

    async def handle_root(self, request: web.Request) -> web.Response:
        # returns Raft-log and node status
        return web.Response(
            text=(
                f"Role: {self.current_role}\n"
                f"Node: {self.node_id}\n"
                f"Term: {self.current_term}\n"
                f"Log : {self.log}\n"
                "-\n"
                f"Commit Length: {self.commit_length}\n"
                f"Sent Length: {self.sent_length}\n"
                f"Acked Length: {self.acked_length}\n"
                f"State Machine: {self.state_machine}\n"
                # f"Heartbeat Timeout: {HEARTBEAT_TIMEOUT}\n"
                # f"Election Timeout: {ELECTION_TIMEOUT}\n"
                # f"Current Leader: {self.current_leader}\n"
                # f"Votes Received: {self.votes_received}\n"
                # f"Voted For: {self.voted_for}\n"
                # "-" * 20 + "\n"
                # f"Node Last Activity Time: {self.node_last_activity_time}\n"
            )
        )

import asyncio
from time import time
from typing import Any
from aiohttp import web, ClientSession, ClientTimeout
import random
import logging

HEARTBEAT_TIMEOUT: float = 1.0  # Heartbeat interval in seconds
ELECTION_TIMEOUT: float = 5.0  # Election timeout in seconds

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s.%(msecs)03d  %(funcName)s -  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class Node:
    def __init__(self, my_name: str, servers: list[str]):
        ### Node state
        self.my_name: str = my_name
        self.servers: list[str] = servers
        self.majority: int = (len(servers) + 2) // 2
        self.state: str = "FOLLOWER"  # FOLLOWER, CANDIDATE, LEADER
        self.server_last_activity_time: float = time()

        ### Persistent state on all servers: (Updated on stable storage before responding to RPCs)
        # self.current_term - latest term server has seen (initialized to 0 on first boot, increases monotonically)
        # self.voted_for - candidateId that received vote in current term (or null if none)
        # self.log - log[] log entries; each entry contains command for state machine, and term when entry was received by leader (first index is 1)Each log entry: {"term": int, "index": int, "command": str}
        self.current_term: int = 0
        self.voted_for: str | None = None
        self.log: list[tuple[int, str]] = []  # Each log entry: (term, command)

        ### Volatile state on all servers:
        # self.commit_index - index of highest log entry known to be committed (initialized to 0, increases monotonically)
        # self.last_applied - index of highest log entry applied to state machine (initialized to 0, increases monotonically)
        self.commit_index: int = 0
        self.last_applied: int = 0

        ### Volatile state on leaders: (Reinitialized after election)
        # self.next_index - for each server, index of the next log entry to send to that server (initialized to leader last log index + 1)
        # self.match_index - index of highest log entry known to be replicated on each server (initialized to 0, increases monotonically)
        self.next_index: dict[str, int] = {server: 0 for server in servers}
        self.match_index: dict[str, int] = {server: 0 for server in servers}

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

    async def start(self):
        """Start the Raft node."""
        logger.warning(f"I start as {self.state} for term {self.current_term}")
        logger.warning(f"My neighbor servers {self.servers}")
        asyncio.create_task(self.check_election_timer())
        asyncio.create_task(self.generate_heartbeats())
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner)
        await site.start()

    async def check_election_timer(self):
        """Check election timeout and start election if needed."""
        while True:
            if self.state == "FOLLOWER":
                if (time() - self.server_last_activity_time) > ELECTION_TIMEOUT:
                    self.state = "CANDIDATE"
                    logger.warning("I switched to CANDIDATE")
                    await self.start_election()
            await asyncio.sleep(HEARTBEAT_TIMEOUT)

    async def start_election(self) -> None:
        """Start an election and request votes from other servers."""
        while True:
            if self.state == "CANDIDATE":
                self.current_term += 1
                self.voted_for = self.my_name
                logger.warning(
                    f"I started election for term {self.current_term} and voted for myself"
                )
                votes = 1
                for resp in asyncio.as_completed(
                    [self.post_request_vote(server) for server in self.servers]
                ):
                    data = await resp

                    if (
                        self.state == "CANDIDATE"
                        and data["term"] == self.current_term
                        and data["vote_granted"]
                    ):
                        votes += 1
                        if votes >= self.majority:
                            self.server_last_activity_time = time()
                            self.state = "LEADER"
                            self.next_index = {
                                server: len(self.log) for server in self.servers
                            }
                            self.match_index = {server: 0 for server in self.servers}
                            print(
                                "self.next_index",
                                self.next_index,
                                "self.match_index",
                                self.match_index,
                            )
                            logger.warning(
                                f"I switched to LEADER for term {self.current_term}"
                            )
                            return
                    elif data["term"] > self.current_term:
                        self.server_last_activity_time = time()
                        self.current_term = data["term"]
                        self.state = "FOLLOWER"
                        self.voted_for = None
                        logger.warning(
                            f"I switched to FOLLOWER for term {self.current_term}"
                        )
                        return
                await asyncio.sleep(
                    random.uniform(ELECTION_TIMEOUT, ELECTION_TIMEOUT * 2)
                )
            else:
                return

    async def post_request_vote(self, server: str) -> dict[str, Any]:
        url = f"http://{server}:8080/request_vote"
        data: dict[str, Any] = {
            "term": self.current_term,
            "candidate_id": self.my_name,
            "last_log_index": len(self.log),  # Assuming log starts at index 0
            "last_log_term": self.log[-1][0] if self.log else 0,  # Last log term
        }
        logging.warning(f"RequestVote with term {data['term']} to '{url}'")
        try:
            async with ClientSession() as session:
                async with session.post(
                    url, json=data, timeout=ClientTimeout(HEARTBEAT_TIMEOUT)
                ) as resp:
                    data = await resp.json()
                    logging.info(f"Answer from '{url}' with data {data}")
                    return data

        except Exception:
            logging.warning(f"FAILED RequestVote with term {data['term']} to '{url}'")
            return {"term": 0, "success": False}

    async def generate_heartbeats(self):
        while True:
            if self.state == "LEADER":
                for resp in asyncio.as_completed(
                    [self.post_heartbeat(server) for server in self.servers]
                ):
                    data = await resp
                    if data["term"] > self.current_term:
                        self.current_term = data["term"]
                        self.state = "FOLLOWER"
                        self.server_last_activity_time = time()
                        logger.warning(
                            f"I switched to FOLLOWER for term {self.current_term}"
                        )
                        break

            await asyncio.sleep(HEARTBEAT_TIMEOUT)

    async def post_heartbeat(self, server: str) -> dict[str, Any]:
        url = f"http://{server}:8080/append_entries"
        data: dict[str, Any] = {"term": self.current_term}
        try:
            logging.info(f"POST heartbeat to '{url}' with term {data['term']}")
            async with ClientSession() as session:
                async with session.post(
                    url, json=data, timeout=ClientTimeout(HEARTBEAT_TIMEOUT)
                ) as resp:
                    return await resp.json()
        except Exception:
            return {"term": 0, "success": False}

    async def handle_request_vote(self, request: web.Request) -> web.Response:
        """Handle RequestVote RPC."""
        data = await request.json()
        self.server_last_activity_time = time()

        last_log_term = self.log[len(self.log) - 1][0] if self.log else 0

        log_ok = (data["last_log_term"] > last_log_term) or (
            data["last_log_term"] == last_log_term
            and data["last_log_index"] >= len(self.log)
        )
        term_ok = (data["term"] > last_log_term) or (
            data["last_log_term"] == last_log_term
            and self.voted_for in (data["candidate_id"], None)
        )
        if log_ok and term_ok:
            self.current_term = data["term"]
            self.state = "FOLLOWER"
            self.voted_for = data["candidate_id"]
            vote_granted = True
            logger.warning(f"I switched to FOLLOWER for term {self.current_term}")
        else:
            vote_granted = False

        return web.json_response(
            {"term": self.current_term, "vote_granted": vote_granted}
        )

    async def handle_append_entries(self, request: web.Request) -> web.Response:
        data = await request.json()
        self.server_last_activity_time = time()

        if data["term"] > self.current_term:
            self.current_term = data["term"]
            self.state = "FOLLOWER"
            self.server_last_activity_time = time()
            logger.warning(f"I switched to FOLLOWER for term {self.current_term}")

        return web.json_response({"term": self.current_term, "success": True})

    async def handle_command(self, request: web.Request) -> web.Response:
        data = await request.json()

        answer: str = "I am not a LEADER, cannot process command"
        if self.state == "LEADER":
            command = data.get("command", None)
            if command:
                self.log.append((self.current_term, command))
                # ackedLength[nodeId] := log.length
                # for each follower ∈ nodes \ {nodeId} do
                #     ReplicateLog(nodeId, follower )
                # end for
                logger.warning(
                    f"Log entry added: {self.log[-1]}, commit_index: {self.commit_index}, last_applied: {self.last_applied}"
                )
                answer = "Ok, command added to log"

        return web.json_response({"answer": answer})

    async def handle_root(self, request: web.Request) -> web.Response:
        # returns Raft-log and node status
        return web.json_response(
            {
                "my_name": self.my_name,
                "state": self.state,
                "log": self.log,
                "term": self.current_term,
                "voted_for": self.voted_for,
                "servers": self.servers,
                "majority": self.majority,
                "server_last_activity_time": self.server_last_activity_time,
            }
        )

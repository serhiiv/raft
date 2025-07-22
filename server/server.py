import os
import socket
import asyncio
from raft_node import Node

# import logging

# logging.basicConfig(
#     level=logging.WARNING,
#     format="%(asctime)s.%(msecs)03d  %(levelname)s:  %(message)s",
#     datefmt="%H:%M:%S",
# )
# logger = logging.getLogger(__name__)


# Define the main function to start the Raft node
async def main():
    # get the cluster size from environment variable or default to 3
    cluster_size = int(os.getenv("CLUSTER_SIZE", 3))

    # cluster nodes names are raft-node-1, raft-node-2, ..., raft-node-n
    # where n is the cluster size
    servers = [f"raft-node-{i + 1}" for i in range(cluster_size)]
    # find the current node's name by matching its IP address
    node_ip = socket.gethostbyaddr(socket.gethostname())[2][0]
    node_name = "localhost"  # default to localhost if not found
    for server in servers:
        try:
            server_ip = socket.gethostbyaddr(server)[2][0]
            if node_ip == server_ip:
                node_name = server
                break
        except (socket.herror, socket.gaierror):
            pass
    if node_name in servers:
        servers.remove(node_name)

    node = Node(node_name, servers)
    await node.start()
    while True:
        await asyncio.sleep(3600)  # keep running


if __name__ == "__main__":
    asyncio.run(main())

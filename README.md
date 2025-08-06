# Limited implementation of the Raft protocol.

The implementation is done in Python based on the pseudocode described in [Distributed Systems](https://www.cl.cam.ac.uk/teaching/2021/ConcDisSys/dist-sys-notes.pdf) (6.2 The Raft consensus algorithm)

To sequentially execute all self-test steps, a bash script self-test.sh was written

To test, execute the following commands:

- `docker compose build`
- `bash self-test.sh`

The following constants are specified for the test:

- CLUSTER_SIZE=3
- HEARTBEAT_TIMEOUT=1.0
- ELECTION_TIMEOUT=2.0
- election_waiting=$(echo "$ELECTION_TIMEOUT * 6" | bc)

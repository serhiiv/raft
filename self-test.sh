#!/bin/bash

export CLUSTER_SIZE=3
export HEARTBEAT_TIMEOUT=0.4
export ELECTION_TIMEOUT=2.0

clear

echo "##### Self-test steps: #####"
echo
log_time=$(date -u +"%Y-%m-%dT%H:%M:%SZ")


echo "### STEP 1. Start 2 nodes"


docker compose up --scale node=2 -d
echo
docker ps
echo
echo
echo "== WAIT for the LEADER election..."

sleep $(echo "$ELECTION_TIMEOUT * 3" | bc)
echo
echo "=> LIST docker logs"
docker compose logs --since "$log_time"
log_time=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
echo
echo "=> LIST nodes status"
for port in {8001..8003}; do
    echo -e "\nPort: $port -----------------------------------------------------"
    curl -s "http://127.0.0.1:$port"
    echo -e "----------------------------------------------------------------\n"
done

echo
echo "?? CHECK: the Leader should be elected"
echo
read -p "=< Press any key to continue..." -n1 -s
echo
echo
echo "### STEP 2. Post msg1, msg2"
echo

while true; do
    read -p "=< PLEASE, enter the LEADER port number (8001-8003): " leader_port
    case $leader_port in
        8001 ) break;;
        8002 ) break;;
        8003 ) break;;
        * ) echo "=< PLEASE, enter a valid port number (8001-8003).";;
    esac
done
echo

echo "== SEND message 'msg1' to the leader"
curl -s --json '{"command": "msg1"}' --request POST http://127.0.0.1:$leader_port
echo
echo
sleep 1
echo "== SEND message 'msg2' to the leader"
curl -s --json '{"command": "msg2"}' --request POST http://127.0.0.1:$leader_port
echo

sleep 1


echo
echo "=> LIST docker logs"
docker compose logs --since "$log_time"
log_time=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
echo
echo "=> LIST nodes status"
for port in {8001..8003}; do
    echo -e "\nPort: $port -----------------------------------------------------"
    curl -s "http://127.0.0.1:$port"
    echo -e "----------------------------------------------------------------\n"
done


echo
echo "?? CHECK: messages should be replicated and committed"
echo
read -p "Press any key to continue..." -n1 -s
echo
echo
echo "### STEP 3. Start 3-rd node"
echo


docker compose up -d
echo
docker ps

sleep $(echo "$ELECTION_TIMEOUT * 3" | bc)


echo
echo "=> LIST docker logs"
docker compose logs --since "$log_time"
log_time=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
echo
echo "=> LIST nodes status"
for port in {8001..8003}; do
    echo -e "\nPort: $port -----------------------------------------------------"
    curl -s "http://127.0.0.1:$port"
    echo -e "----------------------------------------------------------------\n"
done



echo
echo "?? CHECK: messages should be replicated on the 3-rd node"
echo
read -p "Press any key to continue..." -n1 -s
echo
echo
echo "### STEP 4. Partition a Leader - (OldLeader)"
echo


while true; do
    read -p "=< PLEASE, enter the LEADER name (raft-node-?): " leader_name
    case $leader_name in
        raft-node-1 ) break;;
        raft-node-2 ) break;;
        raft-node-3 ) break;;
        * ) echo "=< PLEASE, enter a valid node name (raft-node-1, raft-node-2, raft-node-3).";;
    esac
done
docker network disconnect raft-cluster $leader_name
docker network connect lost-cluster $leader_name

sleep $(echo "$ELECTION_TIMEOUT * 3" | bc)

echo
echo "=> LIST docker logs"
docker compose logs --since "$log_time"
log_time=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
echo
echo "=> LIST nodes status"
for port in {8001..8003}; do
    echo -e "\nPort: $port -----------------------------------------------------"
    curl -s "http://127.0.0.1:$port"
    echo -e "----------------------------------------------------------------\n"
done


echo
echo "?? CHECK: a NewLeader should be elected"
echo
read -p "Press any key to continue..." -n1 -s
echo
echo
echo "### STEP 5. Post msg3, msg4 via NewLeader"
echo


while true; do
    read -p "=< PLEASE, enter the NEW-LEADER port number (8001-8003): " new_leader_port
    case $leader_port in
        8001 ) break;;
        8002 ) break;;
        8003 ) break;;
        * ) echo "=< PLEASE, enter a valid port number (8001-8003).";;
    esac
done
echo

echo "== SEND message 'msg3' to the leader"
curl -s --json '{"command": "msg3"}' --request POST http://127.0.0.1:$new_leader_port
echo
echo
sleep 1

echo "== SEND message 'msg4' to the leader"
curl -s --json '{"command": "msg4"}' --request POST http://127.0.0.1:$new_leader_port
echo
sleep 1


echo
echo "=> LIST docker logs"
docker compose logs --since "$log_time"
log_time=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
echo
echo "=> LIST nodes status"
for port in {8001..8003}; do
    echo -e "\nPort: $port -----------------------------------------------------"
    curl -s "http://127.0.0.1:$port"
    echo -e "----------------------------------------------------------------\n"
done


echo
echo "?? CHECK: messages should be replicated and committed"
echo
read -p "Press any key to continue..." -n1 -s
echo
echo
echo "### STEP 6. Post msg5 via OldLeader"
echo


echo "== SEND message 'msg5' to the leader"
curl -s --json '{"command": "msg5"}' --request POST http://127.0.0.1:$leader_port
echo
sleep 1


echo
echo "=> LIST docker logs"
docker compose logs --since "$log_time"
log_time=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
echo
echo "=> LIST nodes status"
for port in {8001..8003}; do
    echo -e "\nPort: $port -----------------------------------------------------"
    curl -s "http://127.0.0.1:$port"
    echo -e "----------------------------------------------------------------\n"
done



echo
echo "?? CHECK: message should not be committed (or reply NotALeader)"
echo
read -p "Press any key to continue..." -n1 -s
echo
echo
echo "### STEP 7. Join cluster"
echo


docker network disconnect lost-cluster $leader_name
docker network connect raft-cluster $leader_name

sleep $(echo "$ELECTION_TIMEOUT * 3" | bc)

echo
echo "=> LIST docker logs"
docker compose logs --since "$log_time"
log_time=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
echo
echo "=> LIST nodes status"
for port in {8001..8003}; do
    echo -e "\nPort: $port -----------------------------------------------------"
    curl -s "http://127.0.0.1:$port"
    echo -e "----------------------------------------------------------------\n"
done


echo
echo
echo "?? CHECK: msg5 on the OldLeader should be replaced by messages from the NewLeader"
echo
read -p "Press any key to FINISH self-test..." -n1 -s
echo
echo

docker compose down

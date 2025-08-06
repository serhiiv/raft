#!/bin/bash
clear

export CLUSTER_SIZE=3
export HEARTBEAT_TIMEOUT=1.0
export ELECTION_TIMEOUT=2.0

election_waiting=$(echo "$ELECTION_TIMEOUT * 6" | bc)
log_time=$(date -u +"%Y-%m-%dT%H:%M:%S.%NZ")



echo -e "\n\n\n###########################################"
echo "## STEP 1. Start two nodes"
echo
read -p "press any key to continue..." -n1 -s
echo

echo
docker compose up --scale node=2 -d
echo
docker ps

echo
echo "== WAIT for the LEADER election..."
sleep $election_waiting

first_leader_name="raft-$(docker compose logs --since $log_time | grep 'LEADER' | tail -n1 | cut -d ' ' -f1)"
first_leader_port=$(docker ps | grep "$first_leader_name" | grep -oP '0\.0\.0\.0:\K[0-9]+')

source ./view-logs.sh "$log_time"
log_time=$(date -u +"%Y-%m-%dT%H:%M:%S.%NZ")
echo
echo "LEADER name: $first_leader_name"
echo
echo "?? CHECK: the Leader should be elected"



echo -e "\n\n\n###########################################"
echo "## STEP 2. Post msg1, msg2"
echo
read -p "press any key to continue..." -n1 -s
echo

echo
echo "== SEND message 'msg1' to the leader"
curl -s --json '{"command": "msg1"}' --request POST http://127.0.0.1:$first_leader_port
echo

echo
echo "== SEND message 'msg2' to the leader"
curl -s --json '{"command": "msg2"}' --request POST http://127.0.0.1:$first_leader_port
echo
sleep 2

source ./view-logs.sh "$log_time"
log_time=$(date -u +"%Y-%m-%dT%H:%M:%S.%NZ")
echo
echo "?? CHECK: messages 'msg1' and 'msg2' should be replicated and committed"



echo -e "\n\n\n###########################################"
echo "## STEP 3. Start 3-rd node"
echo
read -p "Press any key to continue..." -n1 -s
echo

echo
docker compose up -d
echo
docker ps

sleep 3

source ./view-logs.sh "$log_time"
log_time=$(date -u +"%Y-%m-%dT%H:%M:%S.%NZ")
echo
echo "?? CHECK: messages 'msg1' and 'msg2' should be replicated on the 3-rd node"



echo -e "\n\n\n###########################################"
echo "## STEP 4. Partition a Leader - (OldLeader)"
echo
read -p "Press any key to continue..." -n1 -s
echo

echo
echo "network disconnect raft-cluster $first_leader_name"
docker network disconnect raft-cluster $first_leader_name
echo "docker network create lost-cluster"
docker network create lost-cluster 
echo "network connect lost-cluster $first_leader_name"
docker network connect lost-cluster $first_leader_name

echo
echo "== WAIT for the LEADER election..."
sleep $election_waiting

second_leader_name="raft-$(docker compose logs --since $log_time | grep 'LEADER' | tail -n1 | cut -d ' ' -f1)"
second_leader_port=$(docker ps | grep "$second_leader_name" | grep -oP '0\.0\.0\.0:\K[0-9]+')

source ./view-logs.sh "$log_time"
log_time=$(date -u +"%Y-%m-%dT%H:%M:%S.%NZ")
echo
echo "New LEADER name: $second_leader_name"
echo
echo "?? CHECK: a NewLeader should be elected"



echo -e "\n\n\n###########################################"
echo "## STEP 5. Post msg3, msg4 via NewLeader"
echo
read -p "press any key to continue..." -n1 -s
echo

echo
echo "== SEND message 'msg3' to the leader"
curl -s --json '{"command": "msg3"}' --request POST http://127.0.0.1:$second_leader_port
echo

echo
echo "== SEND message 'msg4' to the leader"
curl -s --json '{"command": "msg4"}' --request POST http://127.0.0.1:$second_leader_port
echo
sleep 2

source ./view-logs.sh "$log_time"
log_time=$(date -u +"%Y-%m-%dT%H:%M:%S.%NZ")
echo
echo "?? CHECK: messages 'msg3' and 'msg4' should be replicated and committed"



echo -e "\n\n\n###########################################"
echo "## STEP 6. Post msg5 via first Leader"
echo
read -p "press any key to continue..." -n1 -s
echo

echo
echo "== SEND message 'msg5' to the leader"
curl -s --json '{"command": "msg5"}' --request POST http://127.0.0.1:$first_leader_port
echo
sleep 2

source ./view-logs.sh "$log_time"
log_time=$(date -u +"%Y-%m-%dT%H:%M:%S.%NZ")
echo
echo "?? CHECK: message 'msg5' should NOT be committed (or reply NotALeader)"



echo -e "\n\n\n###########################################"
echo "## STEP 7. Join cluster"
echo
read -p "press any key to continue..." -n1 -s
echo

echo
echo "network disconnect lost-cluster $first_leader_name"
docker network disconnect lost-cluster $first_leader_name
echo "network connect raft-cluster $first_leader_name"
docker network connect raft-cluster $first_leader_name


echo
echo "== WAIT for the LEADER election..."
sleep $election_waiting

source ./view-logs.sh "$log_time"
log_time=$(date -u +"%Y-%m-%dT%H:%M:%S.%NZ")
echo
echo "?? CHECK: 'msg5' on the '$first_leader_name' should be replaced by messages 'msg3' and 'msg4'"
echo



echo -e "\n\n\n###########################################"
echo "## STEP 8. FINISH self-test"
read -p "press any key to continue..." -n1 -s
echo

echo
docker network rm lost-cluster
docker compose down

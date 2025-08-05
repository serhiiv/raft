#!/bin/bash

echo
echo "-- SHOW docker logs"
echo -e "----------------------------------------------------------------"
docker compose logs --since "$1"
echo -e "----------------------------------------------------------------"
echo
echo "-- SHOW nodes status"
for node in {'raft-node-1','raft-node-2','raft-node-3'}; do
    port=$(docker ps | grep "$node" | grep -oP '0\.0\.0\.0:\K[0-9]+')
    echo -e "----------------------------------------------------------------"
    curl -s "http://127.0.0.1:$port"
done
echo -e "----------------------------------------------------------------"

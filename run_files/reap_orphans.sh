#!/bin/bash
# Remove orphaned ephemeral substrate-worker containers.
#
# Normal teardown (destroy_worker in the orchestrator's finally block) removes
# each experiment's container. Orphans only appear when an orchestrator is
# killed/restarted mid-experiment, so its finally block never ran. This reaper
# removes only EXITED ephemeral workers — never touches running ones (which are
# live experiments) or the named stack containers.
set -u
ids=$(docker ps -aq --filter "name=substrate-worker-worker-" --filter "status=exited")
if [ -z "$ids" ]; then
  echo "[reap] no orphaned exited substrate workers"
  exit 0
fi
n=$(echo "$ids" | grep -c .)
docker rm $ids >/dev/null 2>&1 && echo "[reap] removed $n orphaned exited substrate workers"

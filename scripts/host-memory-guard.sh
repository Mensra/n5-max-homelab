#!/bin/bash
# Host-wide memory pressure watchdog. Runs on the Proxmox host itself
# (not inside any LXC), checks every 10 seconds, and if available
# memory drops below a safe floor, immediately stops the known
# heavy/experimental workload (ComfyUI on LXC 102) to relieve the WHOLE
# HOST before it degrades enough to drop SSH/console sessions or DNS
# response times, per the 2026-09-18 incident (unbounded/near-unbounded
# container memory usage repeatedly starved the whole host, not just
# its own container, dropping the user's terminal and causing real
# service disruption even when no single container technically OOM'd).
#
# Deliberately checks the HOST's actual available memory (MemAvailable
# in /proc/meminfo), not any single container's own cgroup usage --
# that's what nearly took down DNS: usage can look "fine" per-container
# while the host overall is still critically short.
set -u

FLOOR_KB=$((20 * 1024 * 1024))   # 20GB floor -- below this, act immediately
LOG=/var/log/host-memory-guard.log
COOLDOWN_SECS=300                 # don't re-trigger more than once per 5 min
LAST_ACTION_FILE=/run/host-memory-guard.last-action

log() {
  echo "$(date -Iseconds) $1" >> "$LOG"
}

while true; do
  avail_kb=$(awk '/MemAvailable/ {print $2}' /proc/meminfo)

  if [ "$avail_kb" -lt "$FLOOR_KB" ]; then
    now=$(date +%s)
    last=0
    [ -f "$LAST_ACTION_FILE" ] && last=$(cat "$LAST_ACTION_FILE")
    if [ $((now - last)) -ge "$COOLDOWN_SECS" ]; then
      log "TRIGGERED: MemAvailable=${avail_kb}KB below floor=${FLOOR_KB}KB -- stopping comfyui on LXC 102"
      if pct exec 102 -- docker stop comfyui >> "$LOG" 2>&1; then
        log "comfyui stopped successfully"
      else
        log "FAILED to stop comfyui -- check LXC 102 reachability"
      fi
      echo "$now" > "$LAST_ACTION_FILE"
    fi
  fi

  sleep 10
done

#!/bin/bash
# AI workload "baton" watcher -- ComfyUI and Ollama share the same GPU-accessible
# memory pool on this box and must not both be actively working at once.
# Instead of gating every click or intercepting traffic, this just polls both
# services' real state and forcibly yields whichever one has been holding the
# baton longer if the other one starts up while it's still active.

LOG=/var/log/ai-baton-watcher.log
POLL_INTERVAL=4

comfy_running_since=""
ollama_running_since=""

log() {
  echo "$(date -Iseconds) $1" >> "$LOG"
}

comfyui_busy() {
  curl -s --max-time 2 http://localhost:8188/queue 2>/dev/null \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(1 if d.get('queue_running') else 0)" 2>/dev/null
}

ollama_model() {
  curl -s --max-time 2 http://localhost:11434/api/ps 2>/dev/null \
    | python3 -c "
import json,sys
d=json.load(sys.stdin)
m=d.get('models',[])
print(m[0]['name'] if m else '')
" 2>/dev/null
}

# Is Ollama actually generating, or just holding an idle model in memory (keep_alive)?
# /api/ps can't tell; the llama-server runner's CPU time can: ~3200 ticks/2s while
# generating (all cores), exactly 0 when idle (measured 2026-09-25).
ollama_generating() {
  local p a b
  p=$(pgrep -f llama-server | head -1)
  [ -z "$p" ] && { echo 0; return; }
  a=$(awk '{print $14+$15}' /proc/$p/stat 2>/dev/null) || { echo 0; return; }
  sleep 1
  b=$(awk '{print $14+$15}' /proc/$p/stat 2>/dev/null) || { echo 0; return; }
  [ $((b - a)) -gt 50 ] && echo 1 || echo 0
}

force_interrupt_comfyui() {
  curl -s --max-time 3 -X POST http://localhost:8188/interrupt >/dev/null 2>&1
  log "ACTION: interrupted ComfyUI job to yield baton to Ollama"
}

force_unload_ollama() {
  local model="$1"
  curl -s --max-time 5 -X POST http://localhost:11434/api/generate \
    -H "Content-Type: application/json" \
    -d "{\"model\": \"$model\", \"keep_alive\": 0}" >/dev/null 2>&1
  log "ACTION: force-unloaded Ollama model '$model' to yield baton to ComfyUI"
}

log "ai-baton-watcher started (poll interval ${POLL_INTERVAL}s)"

while true; do
  now=$(date +%s)

  c_busy=$(comfyui_busy)
  o_model=$(ollama_model)

  if [ "$c_busy" = "1" ]; then
    [ -z "$comfy_running_since" ] && comfy_running_since=$now
  else
    comfy_running_since=""
  fi

  if [ -n "$o_model" ]; then
    [ -z "$ollama_running_since" ] && ollama_running_since=$now
  else
    ollama_running_since=""
  fi

  if [ "$c_busy" = "1" ] && [ -n "$o_model" ]; then
    # both holding at once. An IDLE loaded Ollama model (left by keep_alive after a chat
    # reply, e.g. Open WebUI's reply to an image request) always yields: reloading it costs
    # seconds, interrupting an image costs up to ~25 min (2026-09-25). Otherwise whoever
    # started first keeps the baton.
    if [ "$(ollama_generating)" = "0" ]; then
      log "CONFLICT: ComfyUI job running, Ollama model '$o_model' loaded but idle -- yielding Ollama"
      force_unload_ollama "$o_model"
      ollama_running_since=""
    elif [ "$comfy_running_since" -le "$ollama_running_since" ]; then
      log "CONFLICT: ComfyUI was running first (since $comfy_running_since), Ollama loaded '$o_model' at $ollama_running_since -- yielding Ollama"
      force_unload_ollama "$o_model"
      ollama_running_since=""
    else
      log "CONFLICT: Ollama was loaded first (since $ollama_running_since, model '$o_model'), ComfyUI started at $comfy_running_since -- yielding ComfyUI"
      force_interrupt_comfyui
      comfy_running_since=""
    fi
  fi

  sleep "$POLL_INTERVAL"
done

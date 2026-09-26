# Scripts

Taken from the running build and sanitized (addresses and names are placeholders). Read before
running; they assume the layout described in [../GUIDE.md](../GUIDE.md).

| File | Runs where | What it does |
|---|---|---|
| `ai-baton-watcher.sh` | AI container (systemd service) | Polls ComfyUI's queue and Ollama's loaded models every 4 s; if both hold the GPU, the idle one (or the later one) yields. Detects "Ollama loaded but idle" from the `llama-server` runner's CPU time |
| `host-memory-guard.sh` | Proxmox host (systemd timer/service) | Stops the experimental AI workload if host `MemAvailable` falls below a floor -- the one check that sees GPU (GTT) memory |
| `setup-breakglass.sh` | Proxmox host | Creates/refreshes one break-glass local admin in Jellyfin, Immich, Open WebUI, Grafana, Homarr and Portainer, and tests each login. Edit the config block first |
| `comfyui-docker-compose.yml` | AI container | ComfyUI on ROCm for gfx1151 with the flags and limits that worked (`--disable-mmap`, `--reserve-vram 12`, memory/swap limits, thread counts) |

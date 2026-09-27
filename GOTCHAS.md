# Gotchas: the traps that cost the most time

One line each; details in [GUIDE.md](GUIDE.md).

## Hardware (Minisforum N5 Max)
1. **The M.2 bay heatsink may ship loose in the accessory box.** Fit it (peel the pad film).
2. **Only one M.2 slot is PCIe 4.0 x4; the rest are x1.** Put the drive that matters there and check `lspci -vv`.
3. **The HDD fans follow ambient temperature, not the drives.** Their base speed (Start PWM) is what cools the drives under load.
4. **The community fan driver mislabels the N5 Max's channels** (they're CPU1, CPU2, PSU) and can't see the HDD fans. Measure those by sound instead (GUIDE section 7).
5. **The internal PCIe x4 slot is already used** by the Thunderbolt 5 card behind the two 80 Gbps ports.

## Strix Halo GPU / AI
6. **GPU memory (GTT) isn't charged to any container's memory limit.** Budget GTT + container limits against physical RAM yourself, and set `amdgpu gttsize`.
7. **ComfyUI needs `--disable-mmap`** or every model costs ~2x its size (page cache + GTT copy of the same file).
8. **ROCm 7.14.1 busy-spins a CPU core forever on gfx1151** (TheRock #7051/#8213) -- fans at max while idle. A 7.13 nightly idles cleanly.
9. **Set OMP/MKL/OpenBLAS/NumExpr thread counts to the container's real cores**, and update them when cores change.
10. **Open WebUI 0.11's Image switch needs `function_calling: legacy`** on the chat model, or the chat model gets the photo and (if text-only) errors out.
11. **FLUX Kontext takes one photo at ~1 MP.** For "combine photo A and photo B at 2000x1200", use FLUX.2's multi-reference graph.
12. **Ollama "loaded" isn't "busy".** Check the `llama-server` runner's CPU time before interrupting a GPU job on its behalf.

## Containers, updates, networking
13. **Ubuntu's stock `nftables.service` flushes Docker's rules when the package updates.** Disable it (don't stop it) where Docker runs.
14. **Enable Docker `live-restore`** so daemon upgrades don't restart your DNS.
15. **Unattended-upgrades covers security only**; normal updates pile up.
16. **Jellyfin: passing `/dev/dri` isn't enough** -- switch Transcoding to VA-API, or it stays on the CPU.
17. **`pct exec` into a *privileged* LXC takes ownership of the caller's stdout file** (it becomes root, mode 600). Pipe through `| cat` in scripts/automation.
18. **Proxmox task-log flooding can silently stop scheduled backups** (a per-file `pct push` loop generated ~5,000 tasks/day).

## DNS / SSO
19. **Every `*.home` name must point at the reverse proxy,** never at a backend.
20. **`.home` is treated as a public suffix by browsers** -- no shared cookie across `*.home`, so domain-level forward auth can't work there.
21. **Use one Authentik hostname everywhere,** or you get split sessions.
22. **Apps that set `Secure` cookies need HTTPS** even on the LAN (Proxmox, PBS, Portainer, Cockpit) -- otherwise an endless login loop with no error.

## Break-glass
23. **Test your SSO fallbacks with SSO actually stopped.** Ours found documented passwords that worked nowhere.
24. **Auto-redirect to SSO hides the password box:** Immich `?autoLaunch=0`, Grafana `?disableAutoLogin`.
25. **Portainer lets only its initial admin log in locally once OAuth is on.**

## Process
26. **Read release notes and the software's own source/docs before changing anything; test the exact scenario that failed.**
27. **Keep each password in one place** and use readable placeholders everywhere else.

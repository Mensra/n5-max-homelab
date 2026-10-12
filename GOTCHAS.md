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

## DNS capacity, alerting and Wi-Fi (added October 2026)
28. **AdGuard Home's rate limit (20 queries/s, counted for the whole /24 by default) silently drops bursts.** On a private resolver set `ratelimit` to 0 (live, via `/control/dns_config`). We measured it: 60 parallel lookups, 19 answered; after the change 60/60 and 120/120. It shows up as "server misbehaving" in Docker and as random, unexplained "unavailable" in smart-home integrations.
29. **A webhook can answer HTTP 200 to an id it does not know** (Home Assistant does). A 200 is not delivery. Keep the id in exactly one place and read it from there at send time.
30. **Alert about a failure through something that cannot fail with it.** Proxmox and its backup server run on the same box as Home Assistant, so their failure notices use their own native mail, straight to your mailbox, not through the smart-home stack.
31. **Proxmox Backup Server in a container has no mail relay.** Its default notification target delivered nowhere for months. Give it a direct SMTP target and a matcher that only passes warning/error (the default matcher also routes successes).
32. **`docker compose up -d <service>` can stop your container.** In a project whose network another container is attached to, compose tries to recreate the network, fails halfway and leaves the service stopped and detached. Check `docker ps -a` after any compose command; use `down` then `up -d` for the whole project.
33. **Never run every vendor driver command "as a getter".** Looping through all `wl` commands without arguments on an Asus/Broadcom router crashed the 5 GHz radio firmware on router and node (`cwmax`). Use an allow-list of known read-only commands.
34. **RouterOS prints CRLF over SSH.** `[ "$x" -ge 1 ]` fails on `"4\r"`; strip with `tr -d '\r'`.
35. **MAC deny lists in the Broadcom driver are runtime-only** and vanish at every wireless restart or reboot. If you use them to pin a device to one access point, re-apply from a timer, and release them automatically when the access point is down.
36. **On a NIC whose driver clears TX checksum/TSO above MTU 1500 (RTL8127, r8169), jumbo frames cost the offloads.** Measure 1500 against 9000 before keeping mixed MTUs on one segment.

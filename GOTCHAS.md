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
37. **Hours of local AI inference heat-soak the network PHYs to about 88 C** (idle about 60 C, driver limit 110 C), with the CPU die near 82 C and the GPU near 80 C. It is not a fault, but it is a number to know before you set alarms: measure during a long run, not only during short load tests.
38. **A path-activated systemd oneshot has a start limit (5 starts in 10 seconds).** A burst of requests latches the whole path off until someone resets it. If the service takes a lock and loops until the folder is empty, set `StartLimitIntervalSec=0`.
39. **Python's `smtplib` errors are `OSError` subclasses.** Retrying on `OSError` also retries a refused login three times, which can lock the mailbox. Retry only connect/login on network errors and re-raise any server answer; never repeat a send.
40. **A global alert mute can swallow the one notice that needed a human.** Approval requests must be exempt from a mute, or replayed when it ends.
41. **An unprivileged notify script plus a log file recreated by logrotate as root-owned is a silent failure:** the redirect fails, bash runs nothing, the script exits 0. A UPS sent no alert for 18 days. Test every alert path as the user it really runs as.
42. **UPS transfers of 5-10 seconds, six a day, are flicker.** Debounce the on-battery notice (60 s); never delay low-battery or shutdown events.
43. **A one-shot unit with no timeout and a hung ssh command never ends, and stops its own timer.** Set `TimeoutStartSec`; serialise logins to small routers with a shared `flock` (a single-core MIPS router timed out ssh banner exchange in 7 of 10 runs while several jobs logged in at once).
44. **A network-security appliance that answers ARP can block the IPv4 of any new MAC until you whitelist it.** Symptom: the device reaches the LAN but nothing beyond; the gateway's MAC resolves to the appliance. Give the new MAC to the owner first.
45. **nftables bridge rules for a container:** the chain name `fwd` is reserved; the filter chain must be at priority -100 (after conntrack) or replies are dropped; traffic to the host itself needs its own input hook.
46. **`sed -i` on a bind-mounted single file creates a new inode and the container keeps the old file.** Edit in place and reload through the proxy's admin socket.
47. **A single-label private TLD (`.home`) is its own public suffix to browsers:** a `Domain=home` cookie is dropped and domain-wide forward auth loops. Use single-application mode (host-only cookie) or add a label.
48. **An app that only knows a shared token belongs behind a trusted-proxy mode,** with its port closed to everything but the proxy; then command-line tools and timers need the app's local password.
49. **Hybrid (recurrent + attention) local models resume only from llama.cpp checkpoints about 5 and 513 tokens before the previous prompt's end.** Change anything earlier and the server reads the whole prompt again (`forcing full prompt re-processing`): 79k tokens took 6 min 40 s per step.
50. **OpenClaw 2026.10.9 on native Ollama rewrites envelope timestamps and a runtime-context carrier every request,** which breaks the prefix (openclaw/openclaw#182891, open). Keep prompts small, run long jobs in fresh sessions, read the model server's log.
51. **Do not ask a local model for one enormous answer.** 1,165 lines in a single response took 24 minutes and hid errors; ask for batches and write each as soon as it is judged.
52. **The agent runtime's "stalled session" warning also fires while the model is only reading a long prompt.** Check the model server before restarting anything.
53. **One model slot, many consumers:** a consumer with different runner options (context size, thinking) empties the prompt cache for everyone. Give the host-RAM prompt cache real size (`LLAMA_ARG_CACHE_RAM`) and keep consumers' options identical where possible.
54. **Rank candidate models on false-positive rate before speed or style.** A model with half the memory use matched the winner on reliability and still failed the privacy screen; 8-bit versus 4-bit of the same model was no clear win.
55. **A cloud assistant's command output is data leaving the box.** For private data, build local programs that print counts only and have no mode that prints a field value; test them on invented rows. Do not assume a field delimiter: look at the shape first.
56. **One-off ZFS "pre-update" snapshots are the biggest source of reclaimable space (362 GiB, 90 percent of it) and nothing ages them.** Snapshots keep deleted files alive. Give every checkpoint an expiry when it is created.
57. **Ask the hypervisor which volumes belong to guests; do not keep a list of folders to sweep.** A hand list missed 450 stray backup copies, a three-path pattern 70 more.
58. **Monitoring that polls SMART will keep a sleeping backup drive awake.** Exclude it in the collector's selector (exclusion first) and read `/proc/diskstats` instead.
59. **A failing check that passes at its next scheduled run must not alert.** Retry the connection inside the job and require several failed checks in a row, longer than the next run.
60. **A rollback is not proven until you drill it.** A throwaway stack driven through the real update engine found that a failed image pull still took the stack down before rolling back.
61. **Test any gate that executes on behalf of an AI with hostile input through the real chain:** fixed verbs, an allow-list of names, strict JSON schema, shell chaining, substitution, traversal, newlines, oversize.
62. **Anonymous Docker Hub pulls return 429.** Floating-tag checks and update notifiers all query the registry; pin tags and watch for failures.
63. **A reviewer plugin only reviews the paths it lists.** The agent edited its own persona file unreviewed because the list covered memory and skills but not that file.
64. **An agent told to "navigate by address" treats a page's own Next button as forbidden.** State the principle: navigation is reading; only buying, cancelling, returning or changing is off limits.
65. **A 2.4 GHz noise plateau on a router that the vendor's driver causes can be A/B tested:** with the driver's interference mitigation off (mode 0) the plateaus stopped; with it on they came back. Measure noise before and after, one change at a time.
66. **Camera stream drops on weak Wi-Fi look like NVR problems.** Compare signal level and stream statistics per access point and move the camera before touching the NVR.
67. **iPhone photos are HEIC.** Pick one universal reader (libvips) and make every photo tool use it instead of installing a converter per task.
68. **Entities that never report in Home Assistant clutter every picker.** Disable the never-active ones (105 here); leave anything that has ever reported.
69. **Do not put a transcode into a camera index service to fix a viewer problem.** Fix the delivery path (the viewer's codec choice) instead; a service should do the one thing it was built for.

# Building a home server on a Strix Halo mini-PC NAS (Minisforum N5 Max)

A practical guide distilled from a real build (September 2026): Proxmox VE on a
Minisforum N5 Max running a household NAS, media and photo servers, single sign-on,
backups, DNS, and a local AI stack. It lists the decisions that mattered and the
problems that cost the most time, in the order you'd meet them. Versions are as of
the build; check current releases before copying numbers.

Addresses are written as `<host-ip>`, `<media-lxc-ip>` and so on. Use your own.

---

## 1. The hardware, and what it means for the design

| Part | In this build | Why it matters |
|---|---|---|
| CPU/GPU | AMD Ryzen AI MAX+ 395 with Radeon 8060S (RDNA 3.5, `gfx1151`) + an NPU | One chip does everything; the GPU has no memory of its own |
| Memory | 128 GB LPDDR5X, soldered (Linux sees ~124 GiB) | Shared by the OS, every container, **and** the GPU |
| GPU memory | 1 GiB fixed carve-out ("VRAM") + a large dynamic pool ("GTT") taken from system RAM | See section 5 -- this is the single most important fact about this platform |
| Boot drive | 128 GB NVMe | Keep the host OS small; never let data land on it |
| Swap drive (added) | 512 GB NVMe (Lexar NM790, TLC, DRAM-less) in the one PCIe 4.0 x4 M.2 slot | Swap off ZFS; see "M.2 bay" below |
| Data drives | 5 × 14 TB SATA (Seagate Exos class) | ZFS raidz2 (any 2 drives can fail) |
| Backup drive | 48 TB USB enclosure | Single-disk ZFS pool for the backup server; not redundant by itself |
| Network | 10 GbE + 2.5 GbE | Bonded active-backup: the 10 GbE carries traffic, 2.5 GbE is failover |
| Fan/sensor chip | ITE IT5571 embedded controller | No in-kernel driver; see section 7 |

**M.2 bay (under the fan bracket, found 2026-09-24):** the M.2 connectors sit under a
large finned heatsink next to the two blower fans. **On this unit the heatsink was not installed: it shipped loose in a small accessory box.** Check your box, peel the protective film off its thermal pad, and fit it. Reviewers count five M.2
slots, and only one of them is PCIe 4.0 x4; the rest are x1 (ServeTheHome, NAS Compares).
The factory boot drive is a PCIe 3.0 x4 part in an x1 slot, so `lspci` shows it at
8 GT/s x1 "(downgraded)". That's normal and plenty for a boot disk. Put any drive that
matters in the x4 slot and confirm with `lspci -vv` (LnkSta should read 16 GT/s, Width x4).
The board's SMBIOS slot names (`dmidecode -t slot`) don't match the silkscreen,
so trust the link status over the labels. Use single-sided drives with no heatsink of
their own so the bay heatsink fits over them.

**Design consequence:** because RAM is shared with the GPU, "how much memory does
this container get" is not the whole question. The GPU can take tens of gigabytes
from the same pool without any container limit seeing it (section 5).

---

## 2. Architecture at a glance

```
Proxmox VE host (Debian 13)
  ZFS storage-pool (raidz2, 5 drives)   one dataset per share: media, photo, music, ...
  ZFS pbs-pool (USB drive)              backup datastore only
  Host-level: NUT (UPS), Netdata, the backup scripts/timers, the DR-docs sync

  LXC 100 "media/SSO"   Docker: AdGuard Home (DNS), Caddy (reverse proxy), Authentik
                        (SSO + LDAP outpost), Jellyfin, Immich, Homarr, Uptime Kuma,
                        Portainer, Diun, TeslaMate ...; native Samba + SSSD
  LXC 101 "backups"     Proxmox Backup Server (native install)
  LXC 102 "AI"          Docker: Ollama, Open WebUI, ComfyUI, SearXNG, Home Assistant,
                        Lemonade (NPU)
```

Why containers (LXC) and not VMs: they share the host kernel, so GPU/NPU device
passthrough is a few config lines and memory isn't locked away in a VM. Why three:
the things that must never go down (DNS, sign-on, shares) are kept apart from the
heavy, experimental AI workloads, with backups in a third.

---

## 3. Build order

Each step assumes the previous one works. Test each through the path a real user
would take (a real browser, a real Samba client), not only with command-line checks.

1. **BIOS.** Set the fan curves (section 7). Check "restore on AC power loss" so the
   box comes back by itself after an outage (easy to forget; can't be checked from
   the OS).
2. **Proxmox VE** on the NVMe drive. Use the `pve-no-subscription` repository (or buy
   a subscription -- Proxmox says no-subscription "is not recommended ... on
   production servers"). Update with `apt update && apt full-upgrade`, **never
   `apt upgrade`**.
3. **Network.** Bond the two NICs active-backup under `vmbr0`, MTU 9000 if your
   switch supports it. Reserve fixed addresses in the router for the host and every
   container (by MAC) before anything depends on them.
4. **Storage.** `zpool create -o ashift=12 ... raidz2` on the five drives; one
   dataset per share so each gets its own snapshots, quota (e.g. Time Machine) and
   recordsize (large for video). Set a weekly scrub and scheduled snapshots.
5. **LXC 100 core services first: DNS, then reverse proxy, then sign-on.**
   - AdGuard Home answers `*.home` names, all pointing at Caddy -- never at a
     backend's own address (section 6).
   - Caddy maps each `name.home` to its backend.
   - Authentik for single sign-on (OIDC for apps that support it, a dedicated LDAP
     outpost for Samba group lookups via SSSD).
6. **File shares.** Samba inside LXC 100, share groups resolved from Authentik's
   LDAP via SSSD. Samba *passwords* stay local: Authentik's LDAP can't provide the
   NT hash Samba needs, so this split is forced by the protocol.
7. **Apps** (Jellyfin, Immich, the dashboard, monitoring). For Jellyfin, passing `/dev/dri`
   through is only half the job: **also switch Dashboard -> Playback -> Transcoding to VA-API** and
   pick the decode codecs the chip really supports (`vainfo`). Ours sat at "none" for two weeks,
   transcoding on the CPU, until a review caught it (section 5). Give every container an explicit memory limit.
8. **Backups** (section 8) -- before putting real data on it, not after.
9. **The AI container** (section 5).
10. **Alerting** (section 9) and a printed/downloaded copy of your restore guide.

---

## 4. Decisions worth copying

- **Everything is reached by name, never by IP:port.** DNS finds Caddy, Caddy finds
  the backend. Moving or re-porting a service is then one edit, not a hunt through
  dashboards, monitors and bookmarks.
- **HTTPS (Caddy's internal CA) for any app that sets a `Secure` cookie** -- Proxmox
  VE, PBS, Portainer, Cockpit. Over plain `http://` the browser silently drops the
  cookie and you get an endless login loop with no error. Also needed for browser
  microphone access (e.g. voice input in Open WebUI).
- **Pin image versions** and let Diun tell you about new ones. Update deliberately.
- **Size memory limits from measurement, not guesses:** each container's
  `memory.peak` and `memory.events` (section 9) plus the project's own documented
  requirement. Several apps publish none; measure those.
- **Keep one written restore procedure and test that it points at the right places.**
  Ours silently pointed at a retired location for weeks (section 8).

---

## 5. Strix Halo and the AI stack: what's different

**GPU memory (GTT) is not governed by any container limit.** The GPU borrows system
RAM through the GTT pool. On this platform, as of ROCm 7.14, GTT allocations are not
charged to the cgroup of the process that made them, so Docker's `mem_limit`, the
container's own memory limit, and `memory.min` reservations elsewhere all ignore it.
A model loaded into the GPU can starve the whole host while every limit looks fine.
AMD has said memcg accounting for GTT on these APUs is coming; check whether your
kernel/ROCm has it.

What to do until then:
- Set a hard GTT ceiling: `options amdgpu gttsize=<MiB>` in `/etc/modprobe.d/`
  (this build: 57344, i.e. 56 GiB). It is the only kernel-enforced GPU limit.
- Budget the GPU pool and the containers' RAM limits **together** against physical
  RAM. In this build, 75 GB for ComfyUI's container plus a 56 GB GTT ceiling was more
  than the machine has, and a large image-model load took the whole host down.
- Run one big GPU workload at a time (large LLM *or* image model). ROCm has no
  equivalent of NVIDIA MPS; the real limit is memory capacity anyway.
- Watch host memory, not just container memory: a simple guard that stops the
  experimental workload when `MemAvailable` gets low is the one check that sees GTT.

**Passing the GPU and NPU into an LXC:** allow and bind `/dev/dri`, `/dev/kfd` (GPU
compute) and `/dev/accel/accel0` (NPU) in the container config, and set
`lxc.prlimit.memlock: unlimited`.

**ROCm/PyTorch versions matter more than usual.** `gfx1151` became officially
supported in ROCm 7.14 (July 2026) -- **but** the ROCm 7.14.1 runtime we built had a known bug on
this chip: an idle `AsyncEventsLoop` thread busy-spins one CPU core forever (ROCm/TheRock issues
#7051 and #8213, still open in late September 2026), which pinned the fans at full speed with no
work running. We went back to a ROCm 7.13 nightly image, which idles cleanly. Check those issues
before moving to 7.14.x; AMD publishes PyTorch wheels for it at their own
index (see AMD's "Install PyTorch for ROCm" page). Older nightlies work but miss
things -- for example, ComfyUI only turns on its DynamicVRAM memory manager on AMD
when ROCm is 7.14 or newer (`dynamic_vram_supported()` in its `main.py`). If your
image prints `rocSHMEM Could not open libnuma`, install `libnuma-dev` (it wants the
unversioned `libnuma.so`).

**Thread pools:** PyTorch/OpenMP size themselves from `nproc`. If a container ever
sees the host's full thread count instead of its own core allocation, CPU work
oversubscribes badly. Set `OMP_NUM_THREADS` / `MKL_NUM_THREADS` /
`OPENBLAS_NUM_THREADS` / `NUMEXPR_NUM_THREADS` to the container's real core count --
and update them when you change the core count.

**Ollama:** `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_NUM_PARALLEL=1` (RAM scales with
parallel x context length, per its docs). For a helper model that only runs
occasionally, `keep_alive: 0` frees GPU memory right after each answer.

**Out-of-memory handling inside the AI container:** use `systemd-oomd` (pressure
based) rather than any home-made watchdog keyed on load average. Load average
counts normal container start-up churn and will kill healthy services in a loop.

### Image generation (ComfyUI + FLUX.2) that actually fits

- **Start ComfyUI with `--disable-mmap` on Strix Halo.** Without it the model files stay in the page
  cache *and* get copied into GTT, which on this chip is the same RAM, so every model costs about
  twice its size. Our first 1024x1024 FLUX.2 render pushed host free memory from ~97 GB down to 16 GB
  and the memory guard stopped it; with `--disable-mmap` the same job bottomed out at 46 GB free.
- **Don't over-reserve.** `--reserve-vram` was set to 32 (GB) from the pre-fix days, which left FLUX.2
  "loaded partially" and streaming 6 GB per step. Dropping it to 12 let the whole model load. On this
  chip that did *not* make sampling faster (the "offloaded" part is in the same RAM anyway), but it
  freed memory.
- **FLUX.2 dev fp8 (34 GB) + its Mistral text encoder (17 GB) fits** with room to spare. Measured on
  the Radeon 8060S at ~88 W: 1024x1024 / 28 steps ~8 min sampling; 1536x1536 ~18 min; 2000x1200 with
  two reference photos ~60 min (plus ~5-7 min to load the models from spinning disks). The GPU sits at
  100 % and 86-95 % of its top clock -- it's compute-bound, not memory- or power-bound.
- **For "combine these photos" requests use FLUX.2's multi-reference graph** (each photo ->
  ImageScaleToTotalPixels 1 MP -> VAEEncode -> chained ReferenceLatent), not FLUX Kontext: Kontext
  takes one photo and always works at ~1 MP regardless of the size you ask for. Workflows are in
  `workflows/`.
- **Open WebUI (0.11.x) as the front end:** Admin -> Images, engine ComfyUI, paste the API-format
  workflow and map the nodes. Traps we hit:
  - The chat "Image" switch only runs the image tool directly when the model's
    `function_calling` parameter is **legacy**; otherwise the chat model is handed the photo and asked
    to decide -- a text-only model then fails with "Multimodal data provided, but model does not
    support multimodal requests". We made a dedicated "Image Studio" model on a small vision model
    (`qwen3-vl:4b`) with function calling set to legacy and Image on by default.
  - Turn **"Image prompt generation" off** if you want your words passed through unchanged (no
    chat-model rewrite or refusal).
  - Don't map `steps` for the edit workflow: Open WebUI's edit path never fills it and sends null,
    and ComfyUI rejects the job with a 400.
  - The edit path maps attached photos to the image nodes in order; with a two-photo workflow give the
    second LoadImage a harmless placeholder so one-photo edits still validate.
- **One GPU, two big workloads:** a small watcher (`scripts/ai-baton-watcher.sh`) makes ComfyUI and
  Ollama take turns. Lesson learned: Ollama's `/api/ps` can't tell "loaded but idle" from "answering";
  the `llama-server` runner's CPU time can (thousands of ticks per 2 s while generating, exactly 0
  idle). An idle leftover model should yield to an image job, or every second image after a chat
  reply gets interrupted.

---

## 6. Names, DNS and single sign-on pitfalls

- **Every `*.home` DNS entry must point at the reverse proxy.** Entries pointing
  straight at a backend "work" only until something uses the name over HTTPS or
  through the proxy's rules.
- **Docker containers don't use your LAN DNS by default.** Any container that must
  resolve `*.home` itself needs `dns: [<adguard-ip>]` in its compose file.
- **Routers can quietly bypass your DNS.** Ours (Asus/Merlin) always advertises
  itself as the IPv6 DNS server; fix with a `server=/home/<adguard-ip>` line in its
  dnsmasq custom config. Don't set the router's LAN domain name to your zone.
- **Plan for DNS being down.** With no fallback the whole household loses internet
  names when the server is off; a small router script that switches to a fallback
  resolver after a few failed checks (and back) solves it.
- **`.home` and cookies:** browsers apply the Public Suffix List; an unlisted
  single-label TLD like `.home` is treated as a public suffix, so a cookie for
  `Domain=home` is refused. Anything that needs one login cookie shared across
  subdomains (e.g. Authentik's domain-level forward auth) cannot work on `x.home`.
  `home.arpa` (RFC 8375) is on the list too; ICANN reserved `.internal` for private
  use. Any of them works if you add one label: `*.nas.home`. Plain OIDC logins
  don't need a shared cookie and work fine on `.home`.
- **Use one Authentik address everywhere.** Authentik builds its issuer and login URLs
  from whatever host the app contacted. Apps configured with the raw IP and apps
  configured with the hostname end up with separate sessions.
- **Redirect URIs must use the hostname** the browser actually uses, never a raw IP.
- **Create Authentik objects through its UI, REST API or Blueprints**, not its Django
  shell. Shell-created providers skipped defaults here (empty grant types, a missing
  logout/invalidation flow, no scope mappings).
- **Samba share access via Authentik groups** needs `sssd` in the container
  (`group: files sss` in nsswitch). `getent group` can show a membership change before
  `id user` does -- SSSD caches them separately.

---

## 7. Fans and sensors

- **Five fans, five tachometers in the BIOS:** CPU Fan1, CPU Fan2, PSU, HDD Fan1, HDD Fan2. The
  BIOS Hardware Monitor page shows all five speeds plus a "CPU" and a "System" temperature.
- **From Linux you see less.** The fan chip (an ITE embedded controller) has no in-kernel driver.
  The community driver `minisforum-n5-it5571` was written for the N5 / N5 Pro, not the Max. On the
  Max it loads with `force=1` plus a small patch, and its three speed channels are really
  **CPU Fan1, CPU Fan2 and PSU** (it labels them CPU / SSD / HDD). **The HDD fans aren't readable
  from Linux.** Match the driver's readings against the BIOS page before trusting any label. Build it
  with DKMS or rebuild it after every kernel update.
- **The CPU and PSU fans on "Auto" step through four fixed speeds** and stay at idle until the CPU
  passes about 65 C. That's normal for this board. Leave them on Auto.
- **The HDD fans follow the *ambient* ("System") temperature, not the drives.** They also get a short
  boost on CPU heat spikes. Drive load barely changes that input, so **the fans never ramp for drive
  heat**: their base speed is the only thing cooling the drives through long jobs. On "Smart Manual",
  **Start PWM** effectively sets the idle speed. Keep **Fan Start just below the room temperature**,
  or the fans drop to their minimum (~1,000 RPM) and the drives creep up under load. What worked
  here: Fan Off 0, Fan Start 25, TFull Speed 60, Start PWM 40. That gives ~2,100 RPM, drives at
  38-41 C through a nightly backup, and acceptable noise.
- **Tune the HDD fans by drive temperature,** logged every minute before and after each change, plus a
  few minutes of read-only random-seek load on the pool disks. Treat 45 C as the limit.
- The M.2 bay heatsink ships loose in the accessory box (see section 1).

---

## 8. Backups and disaster recovery

- **Proxmox Backup Server in its own LXC**, datastore on the separate USB pool. Give
  it the documented resources: 4+ cores, 4 GiB RAM plus about 1 GiB per TiB stored.
- **Two jobs:** the built-in vzdump job for the containers, and scripted
  `proxmox-backup-client` runs for the share datasets. Immich also writes its own
  daily database dump into the photo dataset, which the share backup picks up.
- **Keep the host's own config and your restore guide in a synced folder** on the
  data pool (it rides along in the nightly share backup), and download a copy
  somewhere off the box.
- **Test the restore script's source paths** whenever you move things. Ours kept
  looking for a retired folder that still existed empty, so it would have "found"
  it and restored nothing.

Two Proxmox traps that silently stopped container backups for days:
1. **Task-log flooding.** Proxmox keeps only about the last 2,000 tasks, and a daily
   job deletes older task logs. A sync script that ran `pct push` per file every 15
   minutes produced ~5,000 tasks a day, so a still-running backup's log was deleted,
   and the scheduler then skipped the job every minute forever
   ("could not update job state ... no such task"). Write to bind-mounted datasets
   from the host instead of `pct push`, and alert on that scheduler message.
2. **Backup hook scripts that start background processes** must detach them from the
   hook's output (`exec </dev/null >/dev/null 2>&1` and close inherited file
   descriptors). vzdump waits for the hook's output pipe to close; a background loop
   holding it stalled every backup for hours.

---

## 9. Memory protection, monitoring and alerts

- **`memory.min` needs the parent protected too.** Proxmox puts containers under
  `/sys/fs/cgroup/lxc/<id>`. Setting `memory.min` on `lxc/<id>` does nothing if
  `/sys/fs/cgroup/lxc` itself has `memory.min` 0 -- the kernel caps a child's
  effective protection at the parent's (`effective_protection()` in
  `mm/page_counter.c`). Set the parent to at least the sum of the children.
- **ZFS file caching is not charged to containers** (the ARC lives outside cgroups),
  so heavy file I/O doesn't push containers toward their memory limits here.
- **Read the kernel's own per-container records**, not snapshots:
  `memory.peak` (high-water mark since start), `memory.events` (`max` = times it hit
  its limit, `oom_kill` = kills) and the kernel log. In this build the DNS server had
  been killed for memory once and was hitting its limit hundreds of times a day before
  anyone looked.
- **Detection without delivery is the common failure.** Netdata ships an OOM-kill
  alarm routed to nobody by default; Proxmox, ZFS (ZED) and smartd email `root`, and
  many ISPs block outbound port 25, so none of it arrives. Relay mail through your
  provider's submission port (587) with an app password, or push alerts to something
  you already look at (e.g. Uptime Kuma push monitors).
- A useful minimum: out-of-memory kills (with the container named), memory-limit hits
  as an early warning, ZFS pool health, backup job results (including the scheduler
  error above), and a heartbeat so a dead watcher is noticed.

---

## 10. Keeping it healthy

- **Host updates:** monthly, with someone present, outside backup hours;
  `apt update && apt full-upgrade`; the previous kernel stays installed as a fallback
  (`proxmox-boot-tool kernel pin`). Rebuild any out-of-tree module (the fan driver)
  after a kernel update -- or use DKMS.
- **After any change,** check what it might have broken nearby, not only whether the
  change itself worked.
- **Before trusting a fix,** read the software's own source or documentation for the
  behavior, then test the exact scenario that failed. A passing test of the wrong
  scenario is the most expensive kind of wrong.

---

## 11. Updating without breaking things

- **Read the release notes before every update, and test the thing that could break.** "The cure can
  be worse than the problem." Updates that looked routine here were not:
- **Ubuntu's stock `nftables` service will wipe Docker's firewall rules.** Its default
  `/etc/nftables.conf` starts with `flush ruleset`; when an `apt` upgrade of the `nftables` package
  restarted the service inside a Docker LXC, every Docker NAT rule vanished. Running containers stayed
  reachable through `docker-proxy`, but nothing could restart ("iptables: No chain/target/match by
  that name"). In a DNS container this would have taken the house's DNS down. If the file is the stock
  empty accept-all config, **`systemctl disable nftables` -- don't `stop` it** (its ExecStop is also a
  flush). Restart Docker to rebuild its chains.
- **Turn on Docker `live-restore`** (`"live-restore": true` in `daemon.json`, applied with
  `systemctl reload docker` -- no container restarts). Containers then keep running while the Docker
  daemon itself is upgraded (patch releases only, per Docker's docs). We upgraded Docker and
  containerd in the DNS container with a per-second DNS check running: zero failed lookups.
- **Unattended-upgrades on Ubuntu only covers `-security`.** Normal bug-fix updates pile up (we found
  85 per container); schedule them, researched, like any other change.
- **Reverse proxy upgrades: diff the parsed config.** Before moving Caddy 2.9 -> 2.11 we ran both
  versions' `caddy adapt` on our Caddyfile and compared the JSON (zero differences), then probed every
  site before and after and checked the internal CA's fingerprint was unchanged.
- **Major versions: check your plugins first.** Jellyfin 12's database migration is one-way and
  third-party plugins must be removed first; our SSO plugin had no 12.x release, so upgrading would have
  broken single sign-on. We stayed on the patched 10.11 line.

---

## 12. Break-glass access: test it with SSO actually down

- **Every SSO-protected app needs a local admin that works without the identity provider** -- and the
  only proof is to stop the identity provider and log in. We stopped Authentik and tried every app.
- **Auto-redirect hides the password box.** Immich, Grafana and Homarr bounce straight to the (dead)
  SSO page. Bypass addresses that worked: Immich `/auth/login?autoLaunch=0`, Grafana
  `/login?disableAutoLogin`; Homarr's `/auth/login` still served its form.
- **Portainer only lets the initial admin (id 1) log in locally once OAuth is on** ("Only initial admin
  is allowed to login without oauth"). Rename that account rather than creating another.
- **The outage test found stale passwords in our own documentation**: both Samba accounts had been
  changed at some point and the written values worked nowhere. We confirmed the real ones by comparing
  Samba's stored NT hashes (read-only) against the documented candidates, fixed the docs, and re-tested.
- **Samba kept working with SSO down**: passwords are local (Samba needs NT hashes) and SSSD served
  the cached group memberships.
- **One shared break-glass admin** (same memorable username and passphrase everywhere, used only for
  emergencies) is easier to get right under stress than a different fallback per app.
  `scripts/setup-breakglass.sh` creates it in six apps and tests each login.
- **Keep each password in exactly one place** and refer to it by a readable placeholder everywhere else
  (`{{PW_SOMETHING}}`). Every duplicate is a copy that can silently go out of date -- and the day you
  need the emergency sheet is the day a stale value hurts most.

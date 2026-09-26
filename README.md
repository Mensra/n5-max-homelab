# N5 Max home lab: NAS + media + single sign-on + local AI on one Strix Halo box

Field notes from building a household server on a **Minisforum N5 Max** (AMD Ryzen AI Max+ 395,
Radeon 8060S, 128 GB unified memory, 5 drive bays) with **Proxmox VE**, September 2026.

It runs, on one box:

- **Storage:** ZFS raidz2 on 5 × 14 TB, SMB shares with per-share group access, Time Machine,
  nightly backups to Proxmox Backup Server on a separate 48 TB drive
- **Media and photos:** Jellyfin (hardware transcoding on the iGPU), Immich
- **Household plumbing:** AdGuard Home DNS with automatic router failover, Caddy reverse proxy,
  Authentik single sign-on (OIDC + LDAP for Samba), Uptime Kuma, Homarr, Portainer,
  TeslaMate (Tesla data logger with its Grafana dashboards)
- **Local AI:** Ollama (llama3.3:70b fits), Open WebUI, ComfyUI with **full-quality FLUX.2 dev**
  for text-to-image and "combine these photos" edits, all offline

It isn't fast at AI -- the GPU is roughly mid-range -- but it can *hold* models that no consumer
graphics card can, and at 2026 memory prices nothing we could find matches it for the money
([VALUE.md](VALUE.md)).

## Start here

| File | What's in it |
|---|---|
| [MISTAKES.md](MISTAKES.md) | What went wrong during the build, including the times it broke things, and the lesson from each |
| [GOTCHAS.md](GOTCHAS.md) | The traps that cost the most time, one line each. Read this even if you read nothing else |
| [GUIDE.md](GUIDE.md) | The full guide: hardware, build order, AI stack, DNS/SSO, fans, backups, monitoring, updates, break-glass |
| [VALUE.md](VALUE.md) | What else you could buy for equivalent storage + AI, with September 2026 prices |
| [scripts/](scripts/) | Reusable pieces: GPU "baton" watcher, host memory guard, break-glass admin setup, ComfyUI compose |
| [workflows/](workflows/) | ComfyUI API-format workflows for FLUX.2 text-to-image and two-reference-photo composition |

## Disclaimer -- use at your own risk

- **Everything here is provided "as is", without warranty of any kind** (see [LICENSE](LICENSE)). It
  describes one person's home setup. Nothing here is professional, security or legal advice.
- **The scripts change live systems** (accounts, containers, firewall and storage settings). Read them,
  understand them, adapt them, and test on something you can afford to lose. **Have working, tested
  backups before you change anything.**
- **You are responsible for your own data, hardware, security and compliance.** The author accepts no
  liability for data loss, downtime, hardware damage or anything else that results from using this.
- Hardware may void its warranty if opened or modified; check with the manufacturer.
- Versions, prices and behaviour are as of September 2026 and will change. Check current releases and
  vendor documentation before copying numbers.
- Addresses are written as `<host-ip>`, `<media-lxc-ip>`, `<ai-lxc-ip>`; use your own.
- Product names are trademarks of their owners; no affiliation with, or endorsement by, any vendor.
- This is one build, documented honestly -- including the mistakes ([MISTAKES.md](MISTAKES.md)). It is
  not a product and there is no support.

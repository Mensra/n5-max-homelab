#!/usr/bin/env python3
# ha-alert: THE alert call for the server. The phone is only the alarm (bell + both phones once, then the Nextube chimes
# until a pad is touched, via the webhook of the HA automation "host alert"). The REPAIR is read on a large screen next to the hardware:
# for every alert this writes a plain page, served by HA itself (/local), at one short fixed address that can be typed or left open:
#   http://ha.example.lan/local/alerts/latest.html   (the newest alert; refreshes itself; shows "Resolved" when the check passes)
# The page: what happened, the numbered steps for THIS alert (the text after "WHAT TO DO:" in the message, written next to the code that
# detects the failure, split at "(1) (2) ..."), then the general checklist for that kind of problem (/etc/alert-playbook), then the other
# recent alerts. Big type, high contrast, commands in blocks.
#   ha-alert send  KEY "Title" "Message"   once per issue (a key stays silent until quiet for ONCE_QUIET_SECS, default 24 h; each call
#                                          restarts it); if HA does not answer, the full text goes by email to root so it is never lost
#   ha-alert clear KEY                     dismisses the bell and marks the page Resolved (pages are removed after 30 days)
# The webhook id is read from HA's own automations.yaml each time (no second copy: HA answers 200 even to a wrong id).
# Not for Proxmox/PBS: they run on this box, so they use their own native email.
import html, json, os, re, subprocess, sys, time, urllib.request

HA_DIR = "/path/to/home-assistant/config"      # LXC 102 root filesystem, seen from the host
HA_API = os.environ.get("HA_URL", "http://ha.example.lan:8123")
PAGES = HA_DIR + "/www/alerts"
BASE = "http://ha.example.lan/local/alerts"                           # what a browser opens (Caddy -> HA)
PLAYBOOK, ONCE = "/etc/alert-playbook", "/var/lib/host-alerts-once"

def slug(s): return re.sub(r"[^A-Za-z0-9_.-]", "_", s)

def webhook_id():
    m = re.search(r"- id: n5_host_alert\n.*?webhook_id: (\S+)", open(HA_DIR + "/automations.yaml").read(), re.S)
    return m.group(1) if m else ""

def post(body):                                                           # True when HA answered 200 and the id exists
    wid = webhook_id()
    try:
        r = urllib.request.Request(f"{HA_API}/api/webhook/{wid}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        return bool(wid) and urllib.request.urlopen(r, timeout=10).status == 200
    except Exception:
        return False

def section(text, file, prefix):                                         # lines of a Markdown section (single source: the document itself)
    try: lines = open(file).read().splitlines()
    except OSError: return []
    for i, l in enumerate(lines):
        if l.startswith(prefix):
            lv = len(l) - len(l.lstrip("#")); out = []
            for m in lines[i + 1:]:
                if re.match(r"#{1,%d} " % lv, m): break
                out.append(m)
            return [x for x in out if x.strip()]
    return []

def general(key):                                                         # -> (first checks, same-or-identical blocks, different blocks)
    text, best = open(PLAYBOOK).read() if os.path.exists(PLAYBOOK) else "", ([], [], [])
    for sec in re.split(r"^## ", text, flags=re.M)[1:]:
        head, _, body = sec.partition("\n"); checks, same, diff = [], [], []
        for l in body.splitlines():
            if not l.strip(): continue
            m = re.match(r"@(same|different)(-include)? (.*)", l)
            if not m: checks.append(l); continue
            x = section(text, *[s.strip() for s in m.group(3).split("|")]) if m.group(2) else [m.group(3)]
            (same if m.group(1) == "same" else diff).extend(x)
        if any(key.startswith(p) for p in head.split()): return checks, same, diff
        if head.strip() == "default": best = (checks, same, diff)
    return best

CSS = ("body{font-family:system-ui,sans-serif;font-size:24px;line-height:1.5;max-width:56em;margin:0 auto;padding:1em 1.5em;background:#fff;color:#111}"
       "h1{font-size:2em;margin:.2em 0}h2{font-size:1.3em;margin:1.4em 0 .3em;border-bottom:3px solid #888}"
       "li{margin:.6em 0}code,pre{font-family:ui-monospace,monospace;background:#eee;border:1px solid #bbb;border-radius:4px;padding:.05em .3em}"
       ".ok{background:#cfc;border:3px solid #080;padding:.5em 1em;font-weight:bold}small,.old{color:#555}"
       "@media(prefers-color-scheme:dark){body{background:#111;color:#eee}code,pre{background:#222;border-color:#666}h2{border-color:#aaa}small,.old{color:#bbb}.ok{background:#030;color:#cfc}}")

def render(key, title, what, steps, gen, resolved=""):
    checks, same, diff = gen
    code = lambda s: re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", re.sub(r"`([^`]+)`", r"<code>\1</code>", html.escape(s)))
    md = lambda items: "".join(f"<p style='margin:.3em 0 .3em {(len(i) - len(i.lstrip())) * 0.5:g}em'>{code(i.strip())}</p>" for i in items)
    block = lambda h, items: f"<h2>{h}</h2>{md(items)}" if items else ""
    sec = lambda h, items: (f"<h2>{h}</h2>" + "".join(f"<p>{code(i)}</p>" for i in items)) if items else ""
    spec = (f"<h2>Do this</h2><ol>{''.join(f'<li>{code(s)}</li>' for s in steps)}</ol>" if len(steps) > 1 else sec("Do this", steps))
    others = sorted((f for f in os.listdir(PAGES) if f.endswith(".html") and f not in ("latest.html", slug(key) + ".html")),
                    key=lambda f: -os.path.getmtime(f"{PAGES}/{f}"))[:6] if os.path.isdir(PAGES) else []
    more = ("<h2>Other recent alerts</h2><p class=old>" + " &nbsp; ".join(f"<a href='{BASE}/{f}'>{f[:-5]}</a>" for f in others) + "</p>") if others else ""
    banner = f"<p class=ok>RESOLVED {html.escape(resolved)}: the check passes again. Nothing more to do.</p>" if resolved else ""
    return (f"<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<meta http-equiv=refresh content=30><title>{html.escape(title)}</title><style>{CSS}</style></head><body>{banner}"
            f"<h1>{html.escape(title)}</h1><small>{time.strftime('%Y-%m-%d %H:%M %Z')} on {os.uname().nodename} &middot; alert {html.escape(key)}</small>"
            f"{sec('What happened', [what] if what else [])}{spec}{sec('First checks', checks)}{block('If it is replaced by the same model, an identical one, or the same maker\'s same product line (e.g. a newer version)', same)}{block('If it is replaced by a different make or a different product line', diff)}{more}"
            f"<p><small>This page refreshes itself. Touching a Nextube pad silences the clock; the alert clears when the check passes.</small></p></body></html>")

def write(name, text):
    os.makedirs(PAGES, exist_ok=True); os.chown(PAGES, 100000, 100000)
    p = f"{PAGES}/{name}"; open(p, "w").write(text); os.chmod(p, 0o644)

def plain(title, what, steps, gen):
    checks, same, diff = gen
    n = "\n".join(f"  {i}. {s}" for i, s in enumerate(steps, 1))
    out = f"{title}\n\nWHAT HAPPENED\n{what}\n\nDO THIS\n{n or '  (see the first checks)'}\n\nFIRST CHECKS\n" + "\n".join(f"  - {g}" for g in checks)
    if same: out += "\n\nIF REPLACED BY THE SAME / AN IDENTICAL / THE SAME MAKER'S SAME LINE\n" + "\n".join(same)
    if diff: out += "\n\nIF REPLACED BY A DIFFERENT MAKE OR LINE\n" + "\n".join(diff)
    return out

def main(a):
    if len(a) < 3 or a[1] not in ("send", "clear"): sys.exit("usage: ha-alert send KEY TITLE MESSAGE | clear KEY")
    act, key = a[1], a[2]; title = a[3] if len(a) > 3 else ""; msg = a[4] if len(a) > 4 else ""
    if act == "clear":
        try:                                                              # mark the page(s) Resolved instead of leaving stale instructions
            for n in (slug(key) + ".html", "latest.html"):
                p = f"{PAGES}/{n}"
                if os.path.exists(p) and f"alert {html.escape(key)}</small>" in open(p).read() and "RESOLVED" not in open(p).read():
                    t = open(p).read(); write(n, t.replace("<body>", f"<body><p class=ok>RESOLVED {time.strftime('%Y-%m-%d %H:%M')}: the check passes again. Nothing more to do.</p>", 1))
        except OSError: pass
        sys.exit(0 if post({"action": "clear", "key": key}) else 1)
    f = f"{ONCE}/{slug(key)}"; os.makedirs(ONCE, mode=0o700, exist_ok=True)   # once per issue
    now = int(time.time()); last = int(open(f).read() or 0) if os.path.exists(f) else 0
    open(f, "w").write(str(now))
    if now - last < int(os.environ.get("ONCE_QUIET_SECS", 86400)): return
    what, _, todo = msg.partition("WHAT TO DO:")
    what = what.strip(); steps = [s.strip() for s in re.split(r"\s*\(\d\)\s*", todo) if s.strip()]; gen = general(key)
    url = ""
    try:                                                                  # the page; if it cannot be written the alert still goes out
        write(slug(key) + ".html", render(key, title, what, steps, gen)); write("latest.html", render(key, title, what, steps, gen))
        url = f"{BASE}/latest.html"
        for old in os.listdir(PAGES):
            if old != "latest.html" and time.time() - os.path.getmtime(f"{PAGES}/{old}") > 30 * 86400: os.remove(f"{PAGES}/{old}")
    except OSError: pass
    short = (what[:250] + f" Repair steps are on the screen at the hardware: {url}") if url else (what + " " + " ".join(steps))[:1400]
    if not post({"action": "raise", "key": key, "title": title, "message": short, "url": url}):
        body = plain(title, what, steps, gen) + (f"\n\nPage (when Home Assistant is back): {url}" if url else "")
        subprocess.run(["/usr/sbin/sendmail", "-t"], input=f"To: root\nSubject: [server ALERT] {title}\n\n{body}\n\n-- ha-alert fallback (Home Assistant did not answer) on {os.uname().nodename}\n", text=True)

main(sys.argv)

#!/usr/bin/env python3
# dns-stress: finds how many queries per second the home server's AdGuard answers (a stress test of the home resolver).
# Staged and self-limiting: each stage sends N queries/s for DURATION s from one UDP socket; a "household canary" asks a cached name every 100 ms
# during the whole run. A stage is GOOD when >= 99 % are answered and p99 < 250 ms; the run stops at the first stage that is not GOOD (or when
# the canary loses 3 lookups) and never goes past the next step. Workloads: cached (one name, local path) and unique (random names, forces the
# DoH upstream, kept low so the upstream resolver is not hammered). Usage: dns-stress.py cached|unique [server]
import asyncio, random, socket, struct, sys, time

SERVER = sys.argv[2] if len(sys.argv) > 2 else "ns.example.lan"
MODE = sys.argv[1] if len(sys.argv) > 1 else "cached"
DURATION = 4.0
STAGES = [8000, 12000, 16000, 24000, 32000, 48000] if MODE == "cached" else [20, 50, 100, 200, 400]

def query(qid, name):
    q = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0)
    for part in name.split("."): q += bytes([len(part)]) + part.encode()
    return q + b"\x00" + struct.pack(">HH", 1, 1)

class Client(asyncio.DatagramProtocol):
    def __init__(self): self.sent = {}; self.lat = []; self.rcodes = {}
    def connection_made(self, t): self.t = t
    def datagram_received(self, data, addr):
        qid = struct.unpack(">H", data[:2])[0]; t0 = self.sent.pop(qid, None)
        if t0 is not None:
            self.lat.append(time.perf_counter() - t0); rc = data[3] & 0xF; self.rcodes[rc] = self.rcodes.get(rc, 0) + 1

async def canary(stop, out):
    loop = asyncio.get_running_loop()
    while not stop.is_set():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.setblocking(False); s.connect((SERVER, 53))
        t0 = time.perf_counter()
        try:
            await loop.sock_sendall(s, query(random.randrange(65536), "cached-name.example.lan"))
            await asyncio.wait_for(loop.sock_recv(s, 512), 1.0); out.append(time.perf_counter() - t0)
        except Exception: out.append(None)
        s.close(); await asyncio.sleep(0.1)

async def stage(rate):
    loop = asyncio.get_running_loop()
    tr, cl = await loop.create_datagram_endpoint(Client, remote_addr=(SERVER, 53))
    stop = asyncio.Event(); can = []; ct = asyncio.create_task(canary(stop, can))
    total = int(rate * DURATION); start = time.perf_counter(); n = 0
    while n < total:
        due = int((time.perf_counter() - start) * rate) + 1       # pace: send what should have been sent by now
        while n < min(due, total):
            qid = n % 65536
            name = "cached-name.example.lan" if MODE == "cached" else f"st-{random.randrange(10**9)}.example.com"
            cl.sent[qid] = time.perf_counter(); tr.sendto(query(qid, name)); n += 1
        await asyncio.sleep(0.001)
    await asyncio.sleep(1.5)                                       # late answers
    stop.set(); await ct; tr.close()
    got = len(cl.lat); lat = sorted(cl.lat); p = lambda q: (lat[min(got - 1, int(q * got))] * 1000) if got else float("inf")
    cfail = sum(1 for c in can if c is None); cms = sorted(c * 1000 for c in can if c is not None)
    return dict(rate=rate, sent=total, answered=got, pct=100 * got / total, p50=p(.5), p99=p(.99), rcodes=cl.rcodes,
                canary_n=len(can), canary_fail=cfail, canary_max=(cms[-1] if cms else None))

async def main():
    print(f"mode={MODE} server={SERVER} duration={DURATION}s per stage")
    for rate in STAGES:
        r = await stage(rate)
        good = r["pct"] >= 99 and r["p99"] < 250 and r["canary_fail"] < 3
        print(f"{r['rate']:>5} q/s: sent {r['sent']:>6} answered {r['answered']:>6} ({r['pct']:5.1f}%) p50 {r['p50']:6.1f} ms p99 {r['p99']:7.1f} ms "
              f"rcodes {r['rcodes']} | canary {r['canary_n']-r['canary_fail']}/{r['canary_n']} ok, worst {r['canary_max'] and round(r['canary_max'],1)} ms -> {'GOOD' if good else 'LIMIT REACHED'}", flush=True)
        if not good: break
        await asyncio.sleep(5)                                     # let the resolver settle between stages

asyncio.run(main())

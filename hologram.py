#!/usr/bin/env python3
"""hologram.py — осколок = целое в меньшем разрешении. stdlib only.

  python3 hologram.py build  [--r 3] [--out hologram]   # пишет hologram/<repo>.json
  python3 hologram.py verify [--dir hologram]           # проверка осколков + порча
  python3 hologram.py curve  [--trials 300]             # кривая «k осколков -> целое»

Источник вселенной: GitHub API (GITHUB_TOKEN необязателен), иначе universe.json.
"""
import argparse, hashlib, json, os, random, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
USER = "rtynbirf"

def H(b): return hashlib.sha256(b).hexdigest()
def canon(o): return json.dumps(o, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()

def load_universe():
    """Живой список репо; при отказе API — universe.json."""
    try:
        recs, page = [], 1
        while True:
            req = urllib.request.Request(
                f"https://api.github.com/users/{USER}/repos?per_page=100&page={page}&type=owner",
                headers={"User-Agent": "hologram", **({"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"]} if os.environ.get("GITHUB_TOKEN") else {})})
            data = json.load(urllib.request.urlopen(req, timeout=20))
            if not data: break
            for r in data:
                recs.append({"name": r["name"], "desc": (r.get("description") or "")[:200],
                             "lang": r.get("language") or "", "cluster": ""})
            page += 1
        if recs:
            seed = {r["name"]: r for r in json.load(open(os.path.join(HERE, "universe.json")))}
            for r in recs: r["cluster"] = seed.get(r["name"], {}).get("cluster", "")
            return sorted(recs, key=lambda r: r["name"]), "github-api"
    except Exception as e:
        print("API недоступен (%s) -> universe.json" % type(e).__name__, file=sys.stderr)
    return sorted(json.load(open(os.path.join(HERE, "universe.json"))), key=lambda r: r["name"]), "universe.json"

def rec_hash(r): return H(canon(r))

def merkle(hashes):
    lvl = [bytes.fromhex(h) for h in hashes] or [b""]
    while len(lvl) > 1:
        if len(lvl) % 2: lvl.append(lvl[-1])
        lvl = [hashlib.sha256(lvl[i] + lvl[i+1]).digest() for i in range(0, len(lvl), 2)]
    return lvl[0].hex()

def holders(rec_name, names, r):
    """Rendezvous hashing: какие r осколков хранят плоть записи. Детерминированно, без координатора."""
    ranked = sorted(names, key=lambda s: H((rec_name + "|" + s).encode()))
    return set(ranked[:r])

def build(universe, r):
    names = [x["name"] for x in universe]
    hs = {x["name"]: rec_hash(x) for x in universe}
    index = [{"name": n, "hash": hs[n]} for n in names]
    root = merkle([hs[n] for n in names])
    byname = {x["name"]: x for x in universe}
    shards = {}
    for n in names:
        flesh = [byname[m] for m in names if m != n and n in holders(m, names, r)]
        shards[n] = {"hologram": 1, "root": root, "n": len(names), "r": r,
                     "self": byname[n], "index": index, "flesh": flesh}
    return shards, root

def reconstruct(shard_list):
    """Из любых осколков -> (имена+хэши целого, восстановленные записи). Всё проверено по хэшам индекса."""
    roots = {s["root"] for s in shard_list}
    if len(roots) != 1: raise ValueError("осколки разных целых")
    index = shard_list[0]["index"]
    want = {i["name"]: i["hash"] for i in index}
    if merkle([i["hash"] for i in index]) != next(iter(roots)):
        raise ValueError("индекс не сходится с корнем")
    got = {}
    for s in shard_list:
        for rec in [s["self"]] + s["flesh"]:
            if want.get(rec["name"]) == rec_hash(rec): got[rec["name"]] = rec
    return want, got

def cmd_build(a):
    uni, src = load_universe()
    shards, root = build(uni, a.r)
    os.makedirs(a.out, exist_ok=True)
    for n, s in shards.items():
        with open(os.path.join(a.out, n + ".json"), "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=1)
    size = sum(os.path.getsize(os.path.join(a.out, n + ".json")) for n in shards) // len(shards)
    print(f"источник={src} · репо={len(uni)} · r={a.r} · корень={root[:16]}… · средний осколок={size} байт")

def cmd_verify(a):
    sh = [json.load(open(os.path.join(a.dir, f), encoding="utf-8")) for f in sorted(os.listdir(a.dir)) if f.endswith(".json")]
    want, got = reconstruct(sh)
    assert len(got) == len(want), "из ВСЕХ осколков целое должно собраться полностью"
    # одиночный осколок: имя+хэш целого всегда, плоть частично
    w1, g1 = reconstruct([sh[0]])
    assert len(w1) == len(want)
    # порча: подменим запись в одном осколке — должна быть отвергнута
    bad = json.loads(json.dumps(sh[0]))
    if bad["flesh"]:
        bad["flesh"][0]["desc"] = "ПОДМЕНА"
        _, g2 = reconstruct([bad])
        assert bad["flesh"][0]["name"] not in g2 or g2[bad["flesh"][0]["name"]]["desc"] != "ПОДМЕНА", "подмена прошла!"
    # порча корня
    bad2 = json.loads(json.dumps(sh[0])); bad2["index"][0]["hash"] = "0" * 64
    try: reconstruct([bad2]); raise SystemExit("порча индекса не обнаружена")
    except ValueError: pass
    print(f"OK · осколков={len(sh)} · один осколок: целое в именах/хэшах 100%, плоть {len(g1)}/{len(want)} · подмена отвергается")

def curve(uni, r, trials, rng):
    shards, _ = build(uni, r)
    names = list(shards); n = len(names); rows = []
    for k in range(1, n + 1):
        vals = []
        for _ in range(trials if k < n else 1):
            pick = rng.sample(names, k)
            _, got = reconstruct([shards[x] for x in pick])
            vals.append(len(got) / n)
        vals.sort()
        rows.append((k, sum(vals)/len(vals), vals[0], vals[int(0.05*len(vals))]))
    return rows

def cmd_curve(a):
    uni, src = load_universe(); n = len(uni); rng = random.Random(31)
    out = {}
    for r in (1, 3, 5):
        out[r] = curve(uni, r, a.trials, rng)
    with open("curve.csv", "w") as f:
        f.write("r,k,mean_fidelity,p5_fidelity,min_fidelity\n")
        for r, rows in out.items():
            for k, m, mn, p5 in rows: f.write(f"{r},{k},{m:.4f},{p5:.4f},{mn:.4f}\n")
    # SVG без зависимостей
    W, Hh, P = 720, 420, 50
    def X(k): return P + (k-1)/(n-1)*(W-2*P)
    def Y(v): return Hh-P - v*(Hh-2*P)
    col = {1: "#c0392b", 3: "#d9a441", 5: "#2e7d32"}
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {Hh}" font-family="sans-serif" font-size="12">',
         f'<rect width="{W}" height="{Hh}" fill="#111"/>']
    for g in (0, .25, .5, .75, 1):
        s.append(f'<line x1="{P}" x2="{W-P}" y1="{Y(g)}" y2="{Y(g)}" stroke="#333"/><text x="8" y="{Y(g)+4}" fill="#999">{int(g*100)}%</text>')
    for r, rows in out.items():
        pts = " ".join(f"{X(k):.1f},{Y(m):.1f}" for k, m, _, _ in rows)
        s.append(f'<polyline fill="none" stroke="{col[r]}" stroke-width="2.5" points="{pts}"/>')
        s.append(f'<text x="{W-P-110}" y="{Y(0.12)+ {1:0,3:16,5:32}[r]}" fill="{col[r]}">r={r}: {rows[n//3-1][1]*100:.0f}% при k=n/3</text>')
    s.append(f'<text x="{P}" y="22" fill="#eee" font-size="14">Осколок восстанавливает целое · n={n} · имена+хэши всего — из любого 1 осколка</text>')
    s.append(f'<text x="{W//2-60}" y="{Hh-12}" fill="#999">k осколков из {n} →</text></svg>')
    open("curve.svg", "w").write("\n".join(s))
    print(f"n={n} ({src})")
    for r, rows in out.items():
        pk = lambda t: next(k for k, m, _, _ in rows if m >= t)
        print(f"r={r}: k=1 -> {rows[0][1]*100:.0f}% плоти; k=n/3 -> {rows[n//3-1][1]*100:.0f}%; 95% плоти при k={pk(.95)}; 99% при k={pk(.99)}")

if __name__ == "__main__":
    p = argparse.ArgumentParser(); sp = p.add_subparsers(dest="c", required=True)
    b = sp.add_parser("build"); b.add_argument("--r", type=int, default=3); b.add_argument("--out", default="hologram")
    v = sp.add_parser("verify"); v.add_argument("--dir", default="hologram")
    c = sp.add_parser("curve"); c.add_argument("--trials", type=int, default=300)
    a = p.parse_args(); {"build": cmd_build, "verify": cmd_verify, "curve": cmd_curve}[a.c](a)

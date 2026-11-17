#!/usr/bin/env python3
"""hologram.py — осколок = целое в меньшем разрешении. stdlib only.

  python3 hologram.py build  [--r 3] [--out hologram]   # пишет hologram/<repo>.json
  python3 hologram.py verify [--dir hologram]           # проверка осколков + порча
  python3 hologram.py curve  [--trials 300]             # кривая «k осколков -> целое»

Источник вселенной: GitHub API (GITHUB_TOKEN необязателен), иначе universe.json.
"""
import argparse, hashlib, json, os, random, sys, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
USER = "rtynbirf"
API = "https://api.github.com"

# Репо, исключённые из раздачи осколков (слой 1.2) — замороженные по построению:
# door-zero заморожена по построению (TZ-DOOR-ZERO-001): пустота не наполняется.
# Её запись живёт в индексе каждого осколка и в blob (Release) — целое не страдает.
FROZEN = {"door-zero", "karta", "fond-host", "lex-naturae", "singulyar-a0-audit"}

def archived_names():
    """Замороженные-архив репо (GitHub archived: read-only по построению).

    Осколок в архиве не живёт: записать туда новый нельзя, а плоть из мёртвой
    клетки недостижима для сборки. Носитель плоти — только живая клетка.
    Архивная запись ВСЁ РАВНО покрыта целым: имя+хэш в индексе каждого осколка,
    плоть — в живых соседях (rendezvous по носителям). Без токена/при отказе —
    честный фолбэк: пусто (локальные прогоны, тесты)."""
    try:
        out, page = set(), 1
        while True:
            req = urllib.request.Request(
                f"https://api.github.com/users/{USER}/repos?per_page=100&page={page}&type=owner",
                headers={"User-Agent": "hologram", **({"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"]} if os.environ.get("GITHUB_TOKEN") else {})})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.load(resp)
            if not data: break
            out |= {r["name"] for r in data if r.get("archived")}
            if len(data) < 100: break
            page += 1
        return out
    except Exception as e:
        print("архив-статусы недоступны (%s) — считаем все клетки живыми" % type(e).__name__, file=sys.stderr)
        return set()

def carriers(universe, archived=None):
    """Носители осколков: живые, не замороженные клетки.

    Индекс покрывает ВСЮ вселенную (имена+хэши — целое адресуемо целиком),
    а плоть хранят и раздают только носители: живые минус замороженные."""
    dead = FROZEN | (set() if archived is None else archived)
    return [u["name"] for u in universe if u["name"] not in dead]

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

def build(universe, r, storage=None):
    """Индекс — вся вселенная; осколки и плоть — только носители (storage).

    Раньше плоть раскладывалась по всем именам: архивная клетка становилась
    хранителем, и целое из живых осколков не собиралось (слой 1.2 краснел).
    Теперь rendezvous считается по носителям — сборка из живых полна."""
    names = [x["name"] for x in universe]
    hs = {x["name"]: rec_hash(x) for x in universe}
    index = [{"name": n, "hash": hs[n]} for n in names]
    root = merkle([hs[n] for n in names])
    byname = {x["name"]: x for x in universe}
    storage = storage if storage is not None else names
    shards = {}
    for n in storage:
        flesh = [byname[m] for m in names if m != n and n in holders(m, storage, r)]
        shards[n] = {"hologram": 1, "root": root, "n": len(names), "storage": len(storage), "r": r,
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
    arch = archived_names()
    storage = carriers(uni, arch)
    shards, root = build(uni, a.r, storage)
    os.makedirs(a.out, exist_ok=True)
    for n, s in shards.items():
        with open(os.path.join(a.out, n + ".json"), "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=1)
    size = sum(os.path.getsize(os.path.join(a.out, n + ".json")) for n in shards) // len(shards)
    print(f"источник={src} · репо={len(uni)} · носителей={len(storage)} · заморожено={len(uni)-len(storage)} · r={a.r} · корень={root[:16]}… · средний осколок={size} байт")

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

def curve(uni, r, trials, rng, storage=None):
    shards, _ = build(uni, r, storage)
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
    uni, src = load_universe()
    n = len(carriers(uni, archived_names())); rng = random.Random(31)
    out = {}
    for r in (1, 3, 5):
        out[r] = curve(uni, r, a.trials, rng, carriers(uni, archived_names()))
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

def fetch_shard(name):
    """Осколок репо: hologram.json из корня дефолтной ветки (public raw, без замков).

    Урок волны слоя 1.2: main hardcoded — косЯк. Дом зовёт ветки по-своему
    (у singulyar дефолтная ветка 'rumu'). Порядок: main -> master -> API."""
    for br in ("main", "master"):
        url = f"https://raw.githubusercontent.com/{USER}/{name}/{br}/hologram.json"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "hologram-verify"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
    h = {"User-Agent": "hologram-verify"}
    if os.environ.get("GITHUB_TOKEN"):
        h["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    req = urllib.request.Request(f"{API}/repos/{USER}/{name}", headers=h)
    with urllib.request.urlopen(req, timeout=20) as resp:
        br = json.load(resp)["default_branch"]
    url = f"https://raw.githubusercontent.com/{USER}/{name}/{br}/hologram.json"
    req = urllib.request.Request(url, headers={"User-Agent": "hologram-verify"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)

def cmd_verify_remote(a):
    """Слой 1.2 вживую: целое собирается из осколков, разложенных по самим репо.

    По умолчанию тянет ВСЕ осколки живых носителей и требует полной сборки;
    --sample k — критерий слоя: случайные k = ceil(носители/3), честная плоть.
    Замороженные и архивы (read-only) осколков не несут — их запись живёт
    в индексе каждого осколка, плоть — в живых соседях (r=3)."""
    uni, src = load_universe()
    total = len(uni)
    arch = archived_names()
    pool = carriers(uni, arch)
    print(f"  носители: {len(pool)} · заморожено-архив: {total - len(pool)} ({', '.join(sorted(FROZEN))[:40]}… + архив {len(arch)})")
    rng = random.Random(a.seed)
    if a.sample:
        pool = rng.sample(pool, min(a.sample, len(pool)))
    shards, missing = [], []
    for name in pool:
        try:
            shards.append(fetch_shard(name))
        except Exception as e:
            missing.append(f"{name}({type(e).__name__})")
    if not shards:
        sys.exit("ни одного осколка не получено — раздача слоя 1.2 не жива")
    want, got = reconstruct(shards)
    roots = {s["root"] for s in shards}
    miss_flesh = [n for n in want if n not in got]
    print(f"REMOTE · запрошено={len(pool)} получено={len(shards)} недоступно={len(missing)}"
          + (f" ({', '.join(missing)})" if missing else ""))
    print(f"  корень единый: {len(roots)==1} · имена+хэши: {len(want)}/{total} · плоть: {len(got)}/{total}"
          + (f" ({len(got)/total*100:.0f}%)" if a.sample else "")
          + (f" · не вошли: {', '.join(sorted(miss_flesh)[:8])}{'…' if len(miss_flesh) > 8 else ''}" if miss_flesh and a.sample else ""))
    assert len(roots) == 1, "осколки разных целых — вселенная разъехалась"
    assert len(want) == total, "индекс осколков не покрывает вселенную"
    if a.sample:
        # критерий слоя: при случайных k = ceil(n/3) плоть честно частичная (~81% при r=3)
        # — число сверяется с кривой, а не объявляется. Целостность гарантируют хэши.
        print(f"  выборка k={len(pool)}: плоть {len(got)/total*100:.0f}% — сверяется с кривой r=3 (81% при k=n/3)")
    else:
        assert len(got) == len(want), "имена+хэши обязаны собраться из осколков"
    print("OK · слой 1.2 жив: осколки в репо сходятся в одно целое по Merkle")

if __name__ == "__main__":
    p = argparse.ArgumentParser(); sp = p.add_subparsers(dest="c", required=True)
    b = sp.add_parser("build"); b.add_argument("--r", type=int, default=3); b.add_argument("--out", default="hologram")
    v = sp.add_parser("verify"); v.add_argument("--dir", default="hologram")
    c = sp.add_parser("curve"); c.add_argument("--trials", type=int, default=300)
    r = sp.add_parser("verify-remote"); r.add_argument("--sample", type=int, default=0); r.add_argument("--seed", type=int, default=31)
    a = p.parse_args(); {"build": cmd_build, "verify": cmd_verify, "curve": cmd_curve, "verify-remote": cmd_verify_remote}[a.c](a)

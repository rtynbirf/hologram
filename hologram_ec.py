#!/usr/bin/env python3
"""hologram_ec.py — ТОЧНОЕ восстановление целого из ЛЮБЫХ k осколков из n (Reed-Solomon / GF(256)).
stdlib only. Любой осколок дополнительно несёт целое в низком разрешении (имена+хэши).

  python3 hologram_ec.py build   [--k 0] [--blob FILE] [--out hologram_ec]
  python3 hologram_ec.py restore --dir hologram_ec [--out restored.bin]   # из любых k файлов в папке
  python3 hologram_ec.py verify  [--dir hologram_ec]                      # ВСЕ k-подмножества (или выборка) + порча
  python3 hologram_ec.py curve                                            # curve_ec.csv / curve_ec.svg
По умолчанию k = ceil(n/3): потеряй две трети вселенной — целое цело.
"""
import argparse, base64, hashlib, itertools, json, os, random, sys, zlib
from hologram import load_universe, canon, rec_hash, merkle, H

# ---------- GF(256), полином 0x11d ----------
EXP, LOG = [0]*512, [0]*256
_x = 1
for _i in range(255):
    EXP[_i] = _x; LOG[_x] = _i
    _x <<= 1
    if _x & 0x100: _x ^= 0x11d
for _i in range(255, 512): EXP[_i] = EXP[_i-255]
def mul(a, b): return 0 if a == 0 or b == 0 else EXP[LOG[a] + LOG[b]]
def inv(a):
    if a == 0: raise ZeroDivisionError
    return EXP[255 - LOG[a]]

def gen_matrix(n, k):
    """n×k систематическая: верх = единичная, низ = Коши 1/(x_i ^ y_j). Любые k строк обратимы."""
    assert 1 <= k <= n <= 256 - 0 and n <= 255
    M = [[1 if r == c else 0 for c in range(k)] for r in range(k)]
    for r in range(k, n):
        M.append([inv(r ^ c) for c in range(k)])   # x_i=r (>=k), y_j=c (<k): r^c != 0
    return M

def mat_inv(A):
    k = len(A); M = [row[:] + [1 if i == j else 0 for j in range(k)] for i, row in enumerate(A)]
    for c in range(k):
        p = next(r for r in range(c, k) if M[r][c])
        M[c], M[p] = M[p], M[c]
        iv = inv(M[c][c]); M[c] = [mul(iv, v) for v in M[c]]
        for r in range(k):
            if r != c and M[r][c]:
                f = M[r][c]; M[r] = [v ^ mul(f, w) for v, w in zip(M[r], M[c])]
    return [row[k:] for row in M]

def encode(data: bytes, n, k):
    L = -(-len(data) // k); data = data + b"\0" * (L*k - len(data))
    chunks = [data[i*L:(i+1)*L] for i in range(k)]
    G = gen_matrix(n, k); shares = []
    for row in G:
        out = bytearray(L)
        for j, coef in enumerate(row):
            if coef == 0: continue
            if coef == 1:
                for t in range(L): out[t] ^= chunks[j][t]
            else:
                lc = LOG[coef]; ch = chunks[j]
                for t in range(L):
                    b = ch[t]
                    if b: out[t] ^= EXP[LOG[b] + lc]
        shares.append(bytes(out))
    return shares, L

def decode(idx_shares, n, k, blob_len):
    """idx_shares: {i: share}, берём любые k."""
    ids = sorted(idx_shares)[:k]
    if len(ids) < k: raise ValueError(f"нужно {k} осколков, есть {len(ids)}")
    G = gen_matrix(n, k); Inv = mat_inv([G[i] for i in ids]); L = len(idx_shares[ids[0]])
    chunks = []
    for j in range(k):
        out = bytearray(L)
        for t_, i in enumerate(ids):
            coef = Inv[j][t_]
            if coef == 0: continue
            sh = idx_shares[i]; lc = LOG[coef]
            for t in range(L):
                b = sh[t]
                if b: out[t] ^= EXP[LOG[b] + lc]
        chunks.append(bytes(out))
    return b"".join(chunks)[:blob_len]

# ---------- осколки ----------
def make_shards(universe, blob, k=0):
    names = [u["name"] for u in universe]; n = len(names)
    k = k or -(-n // 3)
    payload = zlib.compress(blob, 9)
    shares, L = encode(payload, n, k)
    sh_hashes = [H(s) for s in shares]
    root = merkle(sh_hashes)
    low = [{"name": u["name"], "hash": rec_hash(u)} for u in universe]
    byname = {u["name"]: u for u in universe}
    meta = {"hologram": 2, "n": n, "k": k, "payload_len": len(payload), "blob_sha256": H(blob),
            "root": root, "share_hashes": sh_hashes, "low": low}
    return {names[i]: dict(meta, i=i, name=names[i], self=byname[names[i]],
                           share=base64.b64encode(shares[i]).decode()) for i in range(n)}

def check_share(s):
    sh = base64.b64decode(s["share"])
    return H(sh) == s["share_hashes"][s["i"]] and merkle(s["share_hashes"]) == s["root"]

def restore(shard_list):
    ok = [s for s in shard_list if check_share(s)]          # порченые отсеиваем
    if not ok: raise ValueError("нет годных осколков")
    m = ok[0]; n, k = m["n"], m["k"]
    ok = [s for s in ok if s["root"] == m["root"]]
    got = {s["i"]: base64.b64decode(s["share"]) for s in ok}
    payload = decode(got, n, k, m["payload_len"])
    blob = zlib.decompress(payload)
    if H(blob) != m["blob_sha256"]: raise ValueError("итог не сходится с blob_sha256")
    return blob

def low_res(shard):
    """Что даёт ОДИН осколок: целое в низком разрешении, проверяемое по хэшам."""
    return {l["name"]: l["hash"] for l in shard["low"]}

# ---------- команды ----------
def load_dir(d): return [json.load(open(os.path.join(d, f), encoding="utf-8")) for f in sorted(os.listdir(d)) if f.endswith(".json")]

def cmd_build(a):
    uni, src = load_universe()
    blob = open(a.blob, "rb").read() if a.blob else canon(uni)
    shards = make_shards(uni, blob, a.k)
    os.makedirs(a.out, exist_ok=True)
    for n, s in shards.items(): json.dump(s, open(os.path.join(a.out, n + ".json"), "w", encoding="utf-8"), ensure_ascii=False)
    s0 = next(iter(shards.values())); sz = sum(os.path.getsize(os.path.join(a.out, n + ".json")) for n in shards)//len(shards)
    print(f"источник={src} · n={s0['n']} · k={s0['k']} · blob={len(blob)} Б -> сжато {s0['payload_len']} Б · осколок≈{sz} Б · корень={s0['root'][:16]}…")

def cmd_restore(a):
    blob = restore(load_dir(a.dir)); open(a.out, "wb").write(blob); print(f"восстановлено {len(blob)} Б -> {a.out}")

def cmd_verify(a):
    sh = load_dir(a.dir); n, k = sh[0]["n"], sh[0]["k"]; rng = random.Random(31)
    ref = restore(sh)
    subsets = list(itertools.combinations(range(n), k)) if n <= 14 else [tuple(rng.sample(range(n), k)) for _ in range(500)]
    for sub in subsets: assert restore([sh[i] for i in sub]) == ref, f"провал на {sub}"
    # k-1 осколков не должны давать точное целое
    try: restore([sh[i] for i in range(k-1)]); raise SystemExit("k-1 осколков дали целое?!")
    except ValueError: pass
    # порча: испорченный осколок отсеивается, остальных k хватает, если запас есть
    bad = json.loads(json.dumps(sh[0])); b = bytearray(base64.b64decode(bad["share"])); b[0] ^= 0xFF
    bad["share"] = base64.b64encode(bytes(b)).decode(); assert not check_share(bad)
    assert restore([bad] + [sh[i] for i in range(1, k+1)]) == ref
    # один осколок: целое в низком разрешении
    lr = low_res(sh[7 % n]); assert len(lr) == n
    print(f"OK · n={n} k={k} · проверено подмножеств: {len(subsets)} (все дают ТОЧНО то же целое, побайтно) · k-1 не хватает · порча отсеяна · 1 осколок = {len(lr)} имён+хэшей")

def cmd_curve(a):
    uni, _ = load_universe(); n = len(uni); rng = random.Random(31)
    rows = []
    for k_ in sorted({max(1, n//6), max(1, n//4), -(-n//3), -(-n//2), -(-2*n//3)}):
        shards = make_shards(uni, canon(uni), k_); lst = list(shards.values())
        size = sum(len(json.dumps(s)) for s in lst)//n
        for kk in range(1, n+1):
            trials = 1 if kk == n else 40; okc = 0
            for _ in range(trials):
                sub = rng.sample(lst, kk)
                try: restore(sub); okc += 1
                except ValueError: pass
            rows.append((k_, kk, okc/trials, size))
    with open("curve_ec.csv", "w") as f:
        f.write("k_threshold,shards_present,exact_restore_rate,avg_shard_bytes\n")
        for r in rows: f.write("%d,%d,%.3f,%d\n" % r)
    for k_ in sorted({r[0] for r in rows}):
        first = next(r[1] for r in rows if r[0] == k_ and r[2] == 1.0); sz = next(r[3] for r in rows if r[0] == k_)
        print(f"k={k_}: точное целое с {first} осколков из {n}; осколок ≈{sz} Б")
    W, Hh, P = 720, 380, 50; col = ["#c0392b", "#d9a441", "#2e7d32", "#3498db", "#9b59b6"]
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {Hh}" font-family="sans-serif" font-size="12"><rect width="{W}" height="{Hh}" fill="#111"/>',
         f'<text x="{P}" y="22" fill="#eee" font-size="14">Точное целое из любых k осколков · n={n}</text>']
    for ci, k_ in enumerate(sorted({r[0] for r in rows})):
        pts = " ".join(f"{P+(kk-1)/(n-1)*(W-2*P):.1f},{Hh-P-rt*(Hh-2*P):.1f}" for kk0, kk, rt, _ in rows if kk0 == k_)
        s.append(f'<polyline fill="none" stroke="{col[ci%5]}" stroke-width="2.5" points="{pts}"/><text x="{W-P-90}" y="{50+16*ci}" fill="{col[ci%5]}">k={k_}</text>')
    s.append(f'<text x="{W//2-60}" y="{Hh-12}" fill="#999">осколков в наличии →</text></svg>'); open("curve_ec.svg", "w").write("\n".join(s))

if __name__ == "__main__":
    p = argparse.ArgumentParser(); sp = p.add_subparsers(dest="c", required=True)
    b = sp.add_parser("build"); b.add_argument("--k", type=int, default=0); b.add_argument("--blob"); b.add_argument("--out", default="hologram_ec")
    r = sp.add_parser("restore"); r.add_argument("--dir", default="hologram_ec"); r.add_argument("--out", default="restored.bin")
    v = sp.add_parser("verify"); v.add_argument("--dir", default="hologram_ec")
    c = sp.add_parser("curve")
    a = p.parse_args(); {"build": cmd_build, "restore": cmd_restore, "verify": cmd_verify, "curve": cmd_curve}[a.c](a)

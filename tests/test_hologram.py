"""Юнит-экзамены голограммы: мелкая вселенная, честная математика.

Слова не проверка — машина отвечает только на перебор: сборка воспроизводима,
подмена отвергается, EC собирает точное целое из любых k и отсеивает порчу.
"""
import base64
import json
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hologram as h  # noqa: E402
import hologram_ec as hec  # noqa: E402

UNI = [{"name": f"repo-{i}", "desc": f"тестовый репозиторий {i}", "lang": "Python",
        "cluster": "тест"} for i in range(9)]


def test_build_reproducible():
    s1, r1 = h.build(UNI, 2)
    s2, r2 = h.build(UNI, 2)
    assert r1 == r2, "одна вселенная — один корень"
    assert s1["repo-0"] == s2["repo-0"]


def test_holders_deterministic_and_exact_r():
    names = [u["name"] for u in UNI]
    for m in names:
        held = h.holders(m, names, 3)
        assert len(held) == 3
        assert held == h.holders(m, names, 3), "rendezvous обязан быть детерминированным"


def test_full_assembly_and_single_shard():
    shards, _ = h.build(UNI, 2)
    lst = [shards[n] for n in sorted(shards)]
    want, got = h.reconstruct(lst)
    assert len(got) == len(want) == len(UNI), "из всех осколков целое собирается полностью"
    w1, _ = h.reconstruct(lst[:1])
    assert len(w1) == len(UNI), "одиночный осколок знает имена+хэши целого"


def test_tamper_rejected():
    shards, _ = h.build(UNI, 2)
    lst = [shards[n] for n in sorted(shards)]
    src = next(s for s in lst if s["flesh"])  # у мелкой вселенной flesh бывает пуст
    bad = json.loads(json.dumps(src))
    bad["flesh"][0]["desc"] = "ПОДМЕНА"
    _, got = h.reconstruct([bad])
    name = bad["flesh"][0]["name"]
    assert name not in got or got[name]["desc"] != "ПОДМЕНА", "подмена плоти прошла!"
    bad2 = json.loads(json.dumps(lst[0]))
    bad2["index"][0]["hash"] = "0" * 64
    with pytest.raises(ValueError):
        h.reconstruct([bad2]), "подмена индекса не обнаружена"


# ---------- EC: точное целое из любых k ----------

def test_ec_roundtrip_any_k():
    rng = random.Random(7)
    blob = bytes(rng.randrange(256) for _ in range(1000))
    shards = hec.make_shards(UNI, blob)
    k = shards["repo-0"]["k"]
    assert k == -(-len(UNI) // 3), "конституция: k = ceil(n/3)"
    lst = [shards[n] for n in sorted(shards)]
    for _ in range(10):
        sub = rng.sample(lst, k)
        assert hec.restore(sub) == blob, "любые k осколков дают ТОЧНОЕ целое"
    with pytest.raises(ValueError):
        hec.restore(lst[:k - 1]), "k-1 осколков не должны давать целое"


def test_ec_corruption_filtered_and_healed():
    blob = "payload-целого".encode()
    shards = hec.make_shards(UNI, blob)
    lst = [shards[n] for n in sorted(shards)]
    bad = json.loads(json.dumps(lst[0]))
    raw = bytearray(base64.b64decode(bad["share"]))
    raw[0] ^= 0xFF
    bad["share"] = base64.b64encode(bytes(raw)).decode()
    assert not hec.check_share(bad), "порченый осколок обязан отсеиваться по хэшу"
    assert hec.restore([bad] + lst[1:1 + shards["repo-0"]["k"]]) == blob, \
        "после отсеивания порчи годных хватает"

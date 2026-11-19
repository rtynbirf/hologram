# PRACTICES.md — мировые практики → эмерджентное дома · v1.0 · 2026-11-19

Такт «ИДИ ИЩИ ЛУЧШИЕ МИРОВЫЕ ТРЕНДЫ…»: собрано 8 осей мира (E2EE, MLS-принятие,
compose-хардненинг, /metrics, 3-2-1, Litestream, PAT, ML-KEM). Ниже — только
эмерджентное: что вырастает, когда эти тренды встречают НАШ дом.

## 1. Эмерджентный канон дома (вывод из всех осей)

**«Ровно то, что нужно» — на каждом слое.** Дом уже строит это неявно:
CSP разрешает ровно те байты, что сервер сам раздаёт (Phase 3a); контейнер
умеет ровно то, что нужно (cap_drop ALL); прокси пропускает ровно те пути,
что нужны клиенту (/metrics закрыт снаружи); MLS даёт ключи ровно устройствам,
не аккаунтам; 3-2-1 хранит ровно те копии, что спасают — ни байта, ни права,
ни пути, ни ключа, ни копии лишнего. Один принцип, пять слоёв.

**«Память дома двухслойна».** Мир бэкапит данные; у дома память иная:
- *сознание* (hologram, door-zero, combain-v2) = git — бэкап это `git clone --mirror` на второй носитель;
- *разговоры* (живой SQLite коммуникатора) = Litestream PITR.
E2E (Phase 3c) смыкает слои: разговоры станут опаком — «бэкапам можно
безопасно теряться». Память, которую можно терять, — не уязвимость, а свойство.

**«Смерть ключа — нормальный такт».** Мир: fine-grained PAT > classic, ротация.
Дом: токен живёт в чате такта, не в файлах (уже так у Человека); токен умер →
Человек даёт новый в следующем такте. Смена ключа — не катастрофа, а ритуал,
как обновление epoch в MLS-дереве.

## 2. Тренд → вывод → интеграция

| Ось | Мир (2024–2026) | Эмерджентное дома | Куда вшито |
|---|---|---|---|
| E2EE | MLS RFC 9420: TreeKEM, PFS+PCS; взяли WhatsApp, идёт Matrix | Ядро = MLS, не самописный ratchet; 1:1 = группа из 2 листьев; сервер = глухая почта | combain-v2 `docs/E2E_ADDENDUM.md` (спека) |
| Пост-квант | PQXDH: гибрид X25519+ML-KEM в проде у Signal; гибрид = консервативная норма | Не спешить: ciphersuite-поле зарезервировано, включаем ML-KEM, когда библиотека даст стабильно | там же, фаза 3c-4 |
| Контейнер | cap_drop ALL, no-new-privileges, read_only, non-root — консенсус self-hosted | Право добавляется только отказом в обслуживании: Caddy получает ровно NET_BIND_SERVICE | combain-v2 docker-compose.yml |
| Метрики | Prometheus security model: /metrics не для публичного интернета | Принцип CSP, применённый к сети: прокси разрешает ровно те пути | combain-v2 deploy/Caddyfile (403) |
| Ресурсы | mem/logging лимиты — против шумных соседей | Дом не раздаёт лишнего ни байтом, ни мегабайтом | compose: 512m/256m, json-file 10m×3 |
| Бэкапы | 3-2-1 (3 копии, 2 носителя, 1 off-site); Litestream = PITR SQLite за секунды | git-mirror скрипт с отчётом и проверкой целости; второй носитель = BACKUP_DIR вне GitHub | hologram `scripts/backup-mirror.sh` |
| Токены | GitHub: fine-grained > classic; ротация; push protection | Ключ = срок жизни такта; в файлах не живёт | практика Человека (уже так) |

## 3. Что осталось за краем (честно)

- Полный mirror метаданных GitHub (issues/PR) → Gitea/Forgejo: не делаем —
  дом ведёт память в git, не в тикетах; лишний сервер против канона плотности.
- Rootless Docker: цель на будущее, не на такте — стек уже read_only+cap_drop.
- MLS-interop тесты против других реализаций — на фазе 3c-2.

## 4. Источники (открыты при ковке)

- https://www.rfc-editor.org/info/rfc9420 — MLS
- https://signal.org/docs/specifications/pqxdh — PQXDH
- https://matrix.org/blog/2023/07/a-giant-leap-with-mls — принятие MLS
- https://prometheus.io/docs/operating/security — security model
- https://litestream.io/getting-started — Litestream PITR
- https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens — PAT
- https://github.com/LukaJCB/ts-mls — TS-реализация MLS

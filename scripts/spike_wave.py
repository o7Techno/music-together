"""Спайк «Моей волны», лайков и плейлистов (SPEC-wave §2).

Запуск (из каталога backend, чтобы использовать его окружение):

    cd backend
    uv run python ../scripts/spike_wave.py read        # станции, настройки, сессии, фидбек
    uv run python ../scripts/spike_wave.py collection  # лайк/дизлайк с откатом, временный плейлист
    uv run python ../scripts/spike_wave.py session-age # жива ли сессия, созданная в `read`

Токен — из YM_TOKEN или `.env` в корне репозитория; не печатается и не пишется в отчёт.
В `collection` меняется только то, что сам спайк создал или сразу откатывает: выбираются треки вне
коллекции, плейлист создаётся приватным и удаляется в конце. Существующие плейлисты не затрагиваются.
Сырые результаты — в `scripts/.spike-out/` (в .gitignore).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from yandex_music import ClientAsync, SessionEvent, SessionFeedback
from yandex_music.exceptions import YandexMusicError
from yandex_music.utils.difference import Difference
from yandex_music.utils.request_async import Request

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scripts" / ".spike-out"
ENV_FILE = ROOT / ".env"
WAVE = "user:onyourwave"
CODECS = ["aac-mp4", "he-aac-mp4", "mp3", "aac", "he-aac"]
TEMP_PLAYLIST = "mt-spike-delete-me"


def load_token() -> str:
    token = os.environ.get("YM_TOKEN", "").strip()
    if not token and ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("YM_TOKEN="):
                token = line.split("=", 1)[1].strip()
    if not token:
        sys.exit("YM_TOKEN не найден: см. scripts/spike_yandex.py auth")
    return token


class Spike:
    def __init__(self, client: ClientAsync) -> None:
        self.client = client
        self.report: dict[str, Any] = {}
        self.last_status: int | None = None
        # Библиотека теряет код ответа в NetworkError — запоминаем его до перевода в исключение.
        request = client._request  # noqa: SLF001
        original = request._handle_error_response  # noqa: SLF001

        def recording(status_code: int, content: bytes) -> Any:
            self.last_status = status_code
            self.last_body = content[:300].decode("utf-8", "replace")
            return original(status_code, content)

        request._handle_error_response = recording  # noqa: SLF001
        self.last_body = ""

    async def step(self, name: str, op: Callable[[], Awaitable[Any]]) -> Any:
        """Выполнить шаг: время, результат или класс ошибки с HTTP-кодом. Сбой не обрывает прогон."""
        self.last_status = None
        started = time.perf_counter()
        try:
            value = await op()
        except YandexMusicError as e:
            ms = round((time.perf_counter() - started) * 1000)
            self.report[name] = {
                "ok": False,
                "ms": ms,
                "error": type(e).__name__,
                "status": self.last_status,
                "body": self.last_body if self.last_status else None,
            }
            print(f"[{name}] ОШИБКА {type(e).__name__} status={self.last_status} {ms} мс")
            return None
        ms = round((time.perf_counter() - started) * 1000)
        print(f"[{name}] ok {ms} мс")
        self.report[name] = {"ok": True, "ms": ms}
        return value

    def note(self, name: str, **fields: Any) -> None:
        self.report.setdefault(name, {}).update(fields)
        print(f"    {name}: {json.dumps(fields, ensure_ascii=False, default=str)[:400]}")

    def save(self, filename: str) -> None:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / filename).write_text(
            json.dumps(self.report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        print(f"Отчёт: scripts/.spike-out/{filename}")


def sequence_stats(sequence: list[Any] | None) -> dict[str, Any]:
    items = sequence or []
    tracks = [s.track for s in items if s.track is not None]
    return {
        "items": len(items),
        "types": dict(Counter(s.type for s in items)),
        "null_track": sum(1 for s in items if s.track is None),
        "unavailable": sum(1 for t in tracks if t.available is False),
        "no_album": sum(1 for t in tracks if not t.albums),
        "zero_duration": sum(1 for t in tracks if not t.duration_ms),
        "liked": sum(1 for s in items if s.liked),
        "duration_s_min_max": [
            round(min((t.duration_ms or 0) for t in tracks) / 1000),
            round(max((t.duration_ms or 0) for t in tracks) / 1000),
        ]
        if tracks
        else None,
    }


def track_ids(sequence: list[Any] | None) -> list[str]:
    return [str(s.track.id) for s in sequence or [] if s.track is not None]


def overlap(a: list[str], b: list[str]) -> float | None:
    if not a or not b:
        return None
    return round(len(set(a) & set(b)) / len(set(a) | set(b)), 3)


async def cmd_read(spike: Spike) -> None:
    c = spike.client

    status = await spike.step("account_status", c.rotor_account_status)
    if status is not None:
        spike.note(
            "account_status",
            has_plus=bool(status.plus and status.plus.has_plus),
            skips_per_hour=status.skips_per_hour,
        )

    stations = await spike.step("stations_list", c.rotor_stations_list)
    if stations:
        kinds = Counter(s.station.id.type for s in stations if s.station and s.station.id)
        samples: dict[str, str] = {}
        for s in stations:
            if s.station and s.station.id:
                samples.setdefault(s.station.id.type, f"{s.station.id.type}:{s.station.id.tag}")
        spike.note("stations_list", count=len(stations), kinds=dict(kinds), samples=samples)

    dashboard = await spike.step("dashboard", c.rotor_stations_dashboard)
    if dashboard is not None:
        spike.note("dashboard", stations=len(dashboard.stations or []))

    settings = await spike.step("wave_settings", lambda: c.rotor_wave_settings(WAVE))
    setting_seeds: dict[str, list[str]] = {}
    if settings is not None:
        restrictions = settings.setting_restrictions
        if restrictions is not None:
            raw = restrictions.to_dict()
            for key, value in raw.items():
                if not isinstance(value, dict):
                    continue
                possible = value.get("possible_values") or []
                seeds = [
                    v.get("serialized_seed") for v in possible if isinstance(v, dict)
                ]
                setting_seeds[key] = [s for s in seeds if s]
        blocks = [
            {
                "type": b.type,
                "items": [
                    f"{i.id.type}:{i.id.tag}" for i in (b.items or []) if i.id is not None
                ][:12],
            }
            for b in settings.blocks or []
        ]
        spike.note("wave_settings", setting_seeds=setting_seeds, blocks=blocks)

    session = await spike.step("session_new", lambda: c.rotor_session_new(WAVE))
    if session is None or not session.radio_session_id:
        spike.save("wave-read.json")
        return
    sid = session.radio_session_id
    spike.note(
        "session_new",
        has_batch=bool(session.batch_id),
        pumpkin=session.pumpkin,
        terminated=session.terminated,
        accepted=[f"{x.type}:{x.tag}" for x in session.accepted_seeds or []],
        stats=sequence_stats(session.sequence),
    )

    batches = [track_ids(session.sequence)]
    seen = list(batches[0])
    repeats = 0
    for i in range(4):
        batch = await spike.step(
            f"session_tracks_{i}", lambda: c.rotor_session_tracks(sid, queue=seen)
        )
        if batch is None:
            continue
        ids = track_ids(batch.sequence)
        repeats += len(set(ids) & set(seen))
        batches.append(ids)
        seen.extend(i for i in ids if i not in seen)
        spike.note(
            f"session_tracks_{i}",
            terminated=batch.terminated,
            unknown=batch.unknown_session,
            batch_changed=batch.batch_id != session.batch_id,
            stats=sequence_stats(batch.sequence),
        )
    spike.note("session_tracks_summary", sizes=[len(b) for b in batches], repeats_with_queue=repeats)

    # Параметр queue: без него та же сессия отдаёт ли повторы?
    no_queue = await spike.step(
        "session_tracks_no_queue", lambda: c.rotor_session_tracks(sid, queue=[])
    )
    if no_queue is not None:
        ids = track_ids(no_queue.sequence)
        spike.note("session_tracks_no_queue", repeats=len(set(ids) & set(seen)), size=len(ids))

    # Фидбек: минимальный набор, как в реальном воспроизведении.
    first = batches[0][0] if batches[0] else None
    batch_id = session.batch_id
    await spike.step(
        "fb_radio_started",
        lambda: c.rotor_session_feedback_radio_started(sid, batch_id=batch_id, from_="web-spike"),
    )
    if first:
        await spike.step(
            "fb_track_started",
            lambda: c.rotor_session_feedback_track_started(sid, first, batch_id=batch_id),
        )
        await spike.step(
            "fb_skip",
            lambda: c.rotor_session_feedback_skip(sid, first, 7.5, batch_id=batch_id),
        )
    # Без дробной записи и без batch_id: что обязательно.
    if len(batches[0]) > 1:
        second = batches[0][1]
        await spike.step(
            "fb_no_batch_id", lambda: c.rotor_session_feedback_track_started(sid, second)
        )
    after = await spike.step(
        "session_tracks_after_feedback", lambda: c.rotor_session_tracks(sid, queue=seen)
    )
    if after is not None:
        spike.note("session_tracks_after_feedback", stats=sequence_stats(after.sequence))

    # Несуществующая сессия.
    lost = await spike.step(
        "unknown_session", lambda: c.rotor_session_tracks("mt-spike-no-such-session", queue=[])
    )
    if lost is not None:
        spike.note("unknown_session", unknown=lost.unknown_session, terminated=lost.terminated)
    bad_fb = await spike.step(
        "unknown_session_feedback",
        lambda: c.rotor_session_feedback_radio_started("mt-spike-no-such-session"),
    )
    spike.note("unknown_session_feedback", result=bad_fb)

    # Инкогнито.
    incognito = await spike.step(
        "session_incognito", lambda: c.rotor_session_new(WAVE, incognito=True)
    )
    if incognito is not None:
        ids = track_ids(incognito.sequence)
        spike.note(
            "session_incognito",
            stats=sequence_stats(incognito.sequence),
            overlap_with_normal=overlap(ids, batches[0]),
        )
        if incognito.radio_session_id and ids:
            await spike.step(
                "session_incognito_feedback",
                lambda: c.rotor_session_feedback_track_started(
                    incognito.radio_session_id, ids[0], batch_id=incognito.batch_id
                ),
            )

    # Зёрна.
    sample = next((s.track for s in session.sequence or [] if s.track is not None), None)
    seeds: dict[str, str] = {"genre": "genre:rock", "mood": "mood:happy", "activity": "activity:workout"}
    if sample is not None:
        seeds["track"] = f"track:{sample.id}"
        if sample.artists:
            seeds["artist"] = f"artist:{sample.artists[0].id}"
        if sample.albums:
            seeds["album"] = f"album:{sample.albums[0].id}"
    for kind, seed in seeds.items():
        result = await spike.step(
            f"seed_{kind}", lambda seed=seed: c.rotor_session_new(seed)
        )
        if result is not None:
            spike.note(
                f"seed_{kind}",
                accepted=[f"{x.type}:{x.tag}" for x in result.accepted_seeds or []],
                size=len(track_ids(result.sequence)),
                terminated=result.terminated,
            )

    # Настройки как сиды: меняют ли выдачу.
    for key, values in setting_seeds.items():
        for value in values[:4]:
            result = await spike.step(
                f"setting_{value}", lambda value=value: c.rotor_session_new([WAVE, value])
            )
            if result is not None:
                ids = track_ids(result.sequence)
                spike.note(
                    f"setting_{value}",
                    group=key,
                    size=len(ids),
                    overlap_with_default=overlap(ids, batches[0]),
                    accepted=[f"{x.type}:{x.tag}" for x in result.accepted_seeds or []],
                )

    # Доступность аудио теми же параметрами, что и YandexProvider.get_stream.
    results = []
    for tid in seen[:6]:
        info = await spike.step(
            f"file_info_{tid}", lambda tid=tid: c.tracks_file_info(tid, "hq", CODECS, "raw")
        )
        d = info.download_info if info is not None else None
        if d is not None:
            results.append([d.quality, d.codec, d.transport, bool(d.key), len(d.urls or [])])
    spike.note("file_info_summary", checked=len(results), variants=dict(Counter(map(str, results))))

    # Классический API — запасной.
    classic = await spike.step("classic_tracks", lambda: c.rotor_station_tracks(WAVE))
    if classic is not None:
        spike.note(
            "classic_tracks",
            has_batch=bool(classic.batch_id),
            stats=sequence_stats(classic.sequence),
            overlap_with_session=overlap(track_ids(classic.sequence), batches[0]),
        )

    # Коллекция: только чтение.
    likes = await spike.step("likes_tracks", lambda: c.users_likes_tracks())
    if likes is not None:
        spike.note("likes_tracks", count=len(likes.tracks or []), revision=likes.revision)
    playlists = await spike.step("playlists_list", lambda: c.users_playlists_list())
    if playlists is not None:
        kinds_list = [p.kind for p in playlists if p.kind is not None]
        spike.note(
            "playlists_list",
            count=len(playlists),
            kinds=kinds_list[:20],
            mine=sum(1 for p in playlists if p.owner and p.owner.uid == c.account_uid),
        )
        if kinds_list:
            full = await spike.step("playlists_batch", lambda: c.users_playlists(kinds_list))
            if isinstance(full, list):
                spike.note(
                    "playlists_batch",
                    returned=len(full),
                    with_tracks=sum(1 for p in full if p.tracks),
                )

    (OUT / "wave-session.json").write_text(
        json.dumps({"session_id": sid, "created_at": time.time(), "queue": seen[:50]}),
        encoding="utf-8",
    )
    spike.save("wave-read.json")


async def cmd_session_age(spike: Spike) -> None:
    saved = json.loads((OUT / "wave-session.json").read_text(encoding="utf-8"))
    age_min = round((time.time() - saved["created_at"]) / 60, 1)
    batch = await spike.step(
        "session_age",
        lambda: spike.client.rotor_session_tracks(saved["session_id"], queue=saved["queue"]),
    )
    if batch is not None:
        spike.note(
            "session_age",
            age_min=age_min,
            unknown=batch.unknown_session,
            terminated=batch.terminated,
            size=len(track_ids(batch.sequence)),
        )
    with (OUT / "wave-session-age.log").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"age_min": age_min, **spike.report.get("session_age", {})}) + "\n")


async def cmd_collection(spike: Spike) -> None:
    c = spike.client
    uid = c.account_uid

    session = await spike.step("pick_tracks", lambda: c.rotor_session_new(WAVE, incognito=True))
    if session is None:
        spike.save("wave-collection.json")
        return
    extra = await spike.step(
        "pick_tracks_more",
        lambda: c.rotor_session_tracks(
            session.radio_session_id, queue=track_ids(session.sequence)
        ),
    )
    pool = [s.track for s in (session.sequence or []) + (extra.sequence if extra else []) or []]
    pool = [t for t in pool if t is not None and t.albums]

    likes = await spike.step("likes_before", lambda: c.users_likes_tracks())
    dislikes = await spike.step("dislikes_before", lambda: c.users_dislikes_tracks())
    liked_before = {str(s.track_id).split(":")[0] for s in (likes.tracks if likes else [])}
    disliked_before = {str(s.track_id).split(":")[0] for s in (dislikes.tracks if dislikes else [])}
    free = [t for t in pool if str(t.id) not in liked_before | disliked_before]
    spike.note("likes_before", count=len(liked_before), free_candidates=len(free))
    if len(free) < 3:
        spike.note("pick_tracks", abort="мало треков вне коллекции")
        spike.save("wave-collection.json")
        return

    # Лайк: добавить, проверить, идемпотентность, убрать, проверить.
    target = str(free[0].id)
    try:
        await spike.step("like_add", lambda: c.users_likes_tracks_add(target, user_id=uid))
        again = await spike.step("like_add_again", lambda: c.users_likes_tracks_add(target, user_id=uid))
        spike.note("like_add_again", result=again)
        now = await spike.step("like_visible", lambda: c.users_likes_tracks())
        ids = {str(s.track_id).split(":")[0] for s in (now.tracks if now else [])}
        spike.note("like_visible", visible=target in ids)
    finally:
        await spike.step("like_remove", lambda: c.users_likes_tracks_remove(target, user_id=uid))
    now = await spike.step("like_restored", lambda: c.users_likes_tracks())
    ids = {str(s.track_id).split(":")[0] for s in (now.tracks if now else [])}
    spike.note("like_restored", collection_unchanged=ids == liked_before)

    # Дизлайк: добавить и убрать.
    target2 = str(free[1].id)
    try:
        await spike.step("dislike_add", lambda: c.users_dislikes_tracks_add(target2, user_id=uid))
        now = await spike.step("dislike_visible", lambda: c.users_dislikes_tracks())
        ids = {str(s.track_id).split(":")[0] for s in (now.tracks if now else [])}
        spike.note("dislike_visible", visible=target2 in ids)
    finally:
        await spike.step(
            "dislike_remove", lambda: c.users_dislikes_tracks_remove(target2, user_id=uid)
        )
    now = await spike.step("dislike_restored", lambda: c.users_dislikes_tracks())
    ids = {str(s.track_id).split(":")[0] for s in (now.tracks if now else [])}
    spike.note("dislike_restored", unchanged=ids == disliked_before)

    # Временный приватный плейлист.
    playlist = await spike.step(
        "playlist_create",
        lambda: c.users_playlists_create(TEMP_PLAYLIST, visibility="private", user_id=uid),
    )
    if playlist is None or playlist.kind is None:
        spike.save("wave-collection.json")
        return
    kind = playlist.kind
    spike.note("playlist_create", visibility=playlist.visibility, revision=playlist.revision)
    try:
        await playlist_steps(spike, kind, playlist.revision or 1, free)
    finally:
        deleted = await spike.step(
            "playlist_delete", lambda: c.users_playlists_delete(kind, user_id=uid)
        )
        spike.note("playlist_delete", result=deleted)
        remaining = await spike.step("playlists_after", lambda: c.users_playlists_list())
        spike.note(
            "playlists_after",
            temp_left=sum(1 for p in remaining or [] if p.title == TEMP_PLAYLIST),
        )
    spike.save("wave-collection.json")


async def playlist_steps(spike: Spike, kind: int, revision: int, tracks: list[Any]) -> None:
    c = spike.client
    uid = c.account_uid
    first = tracks[0]
    album = first.albums[0].id

    inserted = await spike.step(
        "pl_insert",
        lambda: c.users_playlists_insert_track(kind, first.id, album, 0, revision, user_id=uid),
    )
    if inserted is None:
        return
    current = inserted.revision or revision + 1
    spike.note("pl_insert", revision=inserted.revision, count=inserted.track_count)

    # Устаревшая ревизия: главный вопрос спайка.
    stale = await spike.step(
        "pl_stale_revision",
        lambda: c.users_playlists_insert_track(kind, first.id, album, 0, revision, user_id=uid),
    )
    spike.note("pl_stale_revision", accepted=stale is not None)
    fresh = await spike.step("pl_read", lambda: c.users_playlists(kind, user_id=uid))
    if fresh is None:
        return
    current = fresh.revision or current
    spike.note("pl_read", revision=fresh.revision, count=fresh.track_count)

    # Дубликат того же трека при свежей ревизии.
    dup = await spike.step(
        "pl_duplicate",
        lambda: c.users_playlists_insert_track(
            kind, first.id, album, fresh.track_count or 0, current, user_id=uid
        ),
    )
    spike.note("pl_duplicate", accepted=dup is not None, count=dup.track_count if dup else None)
    current = dup.revision if dup and dup.revision else current

    # Несколько треков одной операцией.
    many = [{"id": t.id, "album_id": t.albums[0].id} for t in tracks[1:]]
    at = dup.track_count if dup and dup.track_count else 1
    diff = Difference().add_insert(at, many)
    batch = await spike.step(
        "pl_batch_insert",
        lambda: c.users_playlists_change(kind, diff.to_json(), current, user_id=uid),
    )
    spike.note(
        "pl_batch_insert",
        sent=len(many),
        count=batch.track_count if batch else None,
    )
    current = batch.revision if batch and batch.revision else current

    # Удаление по индексу.
    removed = await spike.step(
        "pl_delete_track",
        lambda: c.users_playlists_delete_track(kind, 0, 1, current, user_id=uid),
    )
    spike.note("pl_delete_track", count=removed.track_count if removed else None)

    # Несуществующий плейлист: какой код.
    await spike.step(
        "pl_missing_kind",
        lambda: c.users_playlists_insert_track(999_999_999, first.id, album, 0, 1, user_id=uid),
    )
    # Трек без альбома: можно ли вставить.
    current_read = await spike.step("pl_read_2", lambda: c.users_playlists(kind, user_id=uid))
    if current_read is not None:
        await spike.step(
            "pl_insert_no_album",
            lambda: c.users_playlists_change(
                kind,
                Difference().add_insert(0, {"id": first.id, "album_id": ""}).to_json(),
                current_read.revision,
                user_id=uid,
            ),
        )


async def cmd_skip_limit(spike: Spike) -> None:
    """Лимит пропусков и остальные типы событий — на инкогнито-сессии, чтобы не учить волну."""
    c = spike.client
    session = await spike.step("sl_session", lambda: c.rotor_session_new(WAVE, incognito=True))
    if session is None or not session.radio_session_id:
        spike.save("wave-skip-limit.json")
        return
    sid = session.radio_session_id
    queue = track_ids(session.sequence)
    batch_id = session.batch_id
    before = await spike.step("sl_status_before", c.rotor_account_status)
    spike.note("sl_status_before", skips_per_hour=before.skips_per_hour if before else None)

    skipped = 0
    for i in range(10):
        tid = queue[i % len(queue)]
        ok = await spike.step(
            f"sl_skip_{i}",
            lambda tid=tid: c.rotor_session_feedback_skip(sid, tid, 3, batch_id=batch_id),
        )
        skipped += 1 if ok else 0
        await asyncio.sleep(0.3)
    spike.note("sl_summary", sent=10, accepted=skipped)

    after = await spike.step("sl_status_after", c.rotor_account_status)
    spike.note("sl_status_after", skips_per_hour=after.skips_per_hour if after else None)
    more = await spike.step("sl_tracks_after", lambda: c.rotor_session_tracks(sid, queue=queue))
    if more is not None:
        spike.note(
            "sl_tracks_after",
            terminated=more.terminated,
            pumpkin=more.pumpkin,
            stats=sequence_stats(more.sequence),
        )
        queue.extend(track_ids(more.sequence))

    # Остальные события и отправка пачкой.
    now = "2026-01-01T00:00:00.000Z"
    tid = queue[0]
    for kind, fields in (
        ("like", {}),
        ("unlike", {}),
        ("dislike", {"total_played_seconds": 5}),
        ("undislike", {}),
        ("trackFinished", {"total_played_seconds": 120.5}),
    ):
        event = SessionEvent(kind, now, track_id=tid, **fields)
        await spike.step(
            f"sl_event_{kind}",
            lambda event=event: c.rotor_session_feedback(sid, event, batch_id),
        )
    feedbacks = [
        SessionFeedback(SessionEvent("trackStarted", now, track_id=tid), batch_id),
        SessionFeedback(SessionEvent("skip", now, track_id=tid, total_played_seconds=4), batch_id),
    ]
    await spike.step("sl_feedbacks_batch", lambda: c.rotor_session_feedbacks(sid, feedbacks))
    piggyback = await spike.step(
        "sl_tracks_with_feedbacks",
        lambda: c.rotor_session_tracks(sid, queue=queue, feedbacks=feedbacks),
    )
    if piggyback is not None:
        spike.note("sl_tracks_with_feedbacks", size=len(track_ids(piggyback.sequence)))
    spike.save("wave-skip-limit.json")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["read", "collection", "session-age", "skip-limit"])
    args = parser.parse_args()
    client = ClientAsync(load_token(), request=Request(timeout=15), report_unknown_fields=False)
    await client.init()
    spike = Spike(client)
    OUT.mkdir(parents=True, exist_ok=True)
    match args.command:
        case "read":
            await cmd_read(spike)
        case "collection":
            await cmd_collection(spike)
        case "session-age":
            await cmd_session_age(spike)
        case "skip-limit":
            await cmd_skip_limit(spike)


if __name__ == "__main__":
    asyncio.run(main())

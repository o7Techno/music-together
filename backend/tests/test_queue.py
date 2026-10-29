import random

import pytest

from app.core.errors import NotFoundError, ValidationError
from app.rooms.queue import HISTORY_LIMIT, Queue, QueueItem, RepeatMode
from tests.factories import item


def tid(i: QueueItem | None) -> str:
    assert i is not None
    return i.track.id


def ids(q: Queue) -> list[str]:
    return [i.track.id for i in q.upcoming]


def test_add_end_next_and_index() -> None:
    q = Queue()
    q.add([item(1), item(2)])
    q.add_next([item(3)])
    q.add([item(4)], index=1)
    assert ids(q) == ["t3", "t4", "t1", "t2"]


def test_every_change_bumps_version() -> None:
    q = Queue()
    v = q.version
    q.add([item(1)])
    q.shuffle(random.Random(1))
    q.set_repeat(RepeatMode.QUEUE)
    assert q.version == v + 3


def test_remove_returns_item_and_index() -> None:
    q = Queue()
    a, b = item(1), item(2)
    q.add([a, b])
    removed, index = q.remove(b.id)
    assert removed.id == b.id
    assert index == 1
    with pytest.raises(NotFoundError):
        q.remove(b.id)


@pytest.mark.parametrize(
    ("to_index", "expected"),
    [(0, ["t3", "t1", "t2"]), (1, ["t1", "t3", "t2"]), (99, ["t1", "t2", "t3"])],
)
def test_move(to_index: int, expected: list[str]) -> None:
    q = Queue()
    items = [item(1), item(2), item(3)]
    q.add(items)
    q.move(items[2].id, to_index)
    assert ids(q) == expected


def test_shuffle_keeps_items_and_current() -> None:
    q = Queue()
    q.add([item(i) for i in range(20)])
    q.advance(natural_end=False)
    current = q.current
    before = sorted(ids(q))
    q.shuffle(random.Random(42))
    assert sorted(ids(q)) == before
    assert q.current == current


def test_clear_only_upcoming() -> None:
    q = Queue()
    q.add([item(1), item(2), item(3)])
    q.advance(natural_end=False)
    assert q.clear() == 2
    assert q.upcoming == []
    assert q.current is not None


def test_advance_moves_current_to_history() -> None:
    q = Queue()
    q.add([item(1), item(2)])
    assert tid(q.advance(natural_end=False)) == "t1"
    assert tid(q.advance(natural_end=True)) == "t2"
    assert q.advance(natural_end=True) is None
    assert [h.track.id for h in q.history] == ["t2", "t1"]


def test_repeat_track_only_on_natural_end() -> None:
    q = Queue()
    q.add([item(1), item(2)])
    q.set_repeat(RepeatMode.TRACK)
    first = q.advance(natural_end=False)
    assert q.advance(natural_end=True) == first
    assert tid(q.advance(natural_end=False)) == "t2"


def test_repeat_queue_appends_finished_with_new_id() -> None:
    q = Queue()
    q.add([item(1), item(2)])
    q.set_repeat(RepeatMode.QUEUE)
    first = q.advance(natural_end=False)
    q.advance(natural_end=True)
    assert ids(q) == ["t1"]
    assert first is not None
    assert q.upcoming[0].id != first.id
    # Очередь из одного трека при повторе очереди играет его снова.
    q2 = Queue()
    q2.add([item(9)])
    q2.set_repeat(RepeatMode.QUEUE)
    q2.advance(natural_end=False)
    assert tid(q2.advance(natural_end=True)) == "t9"


def test_previous_restores_from_history() -> None:
    q = Queue()
    q.add([item(1), item(2)])
    q.advance(natural_end=False)
    q.advance(natural_end=False)
    prev = q.previous()
    assert prev is not None
    assert prev.track.id == "t1"
    assert ids(q) == ["t2"]
    assert q.previous() is None


def test_play_item_keeps_others_in_place() -> None:
    q = Queue()
    items = [item(1), item(2), item(3)]
    q.add(items)
    q.advance(natural_end=False)
    q.play_item(items[2].id)
    assert q.current is not None
    assert q.current.track.id == "t3"
    assert ids(q) == ["t2"]
    assert q.history[0].track.id == "t1"


def test_play_now_puts_rest_next() -> None:
    q = Queue()
    q.add([item(1)])
    q.play_now([item(7), item(8)])
    assert q.current is not None
    assert q.current.track.id == "t7"
    assert ids(q) == ["t8", "t1"]
    with pytest.raises(ValidationError):
        q.play_now([])


def test_history_is_limited() -> None:
    q = Queue()
    q.add([item(i) for i in range(HISTORY_LIMIT + 10)])
    for _ in range(HISTORY_LIMIT + 10):
        q.advance(natural_end=True)
    assert len(q.history) == HISTORY_LIMIT


def test_snapshot_roundtrip() -> None:
    q = Queue()
    q.add([item(1), item(2), item(3)])
    q.advance(natural_end=False)
    q.set_repeat(RepeatMode.QUEUE)
    restored = Queue(q.snapshot())
    assert restored.snapshot() == q.snapshot()

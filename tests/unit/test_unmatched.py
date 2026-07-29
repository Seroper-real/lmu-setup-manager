from domain.unmatched import UnmatchedTracker


def test_serialize_returns_none_when_empty():
    tracker = UnmatchedTracker()
    assert tracker.serialize() is None


def test_record_and_serialize_round_trips():
    tracker = UnmatchedTracker()
    tracker.record("Spa", "Porsche 963", track_matched=False, car_matched=False)

    assert tracker.serialize() == {"tracks": ["Spa"], "cars": ["Porsche 963"]}


def test_record_preserves_insertion_order():
    tracker = UnmatchedTracker()
    tracker.record("Spa", "Porsche 963", track_matched=False, car_matched=False)
    tracker.record("Imola", "BMW M4", track_matched=False, car_matched=False)

    assert tracker.serialize() == {"tracks": ["Spa", "Imola"], "cars": ["Porsche 963", "BMW M4"]}


def test_record_dedupes_identical_track():
    tracker = UnmatchedTracker()
    tracker.record("Spa", "Porsche 963", track_matched=False, car_matched=False)
    tracker.record("Spa", "Porsche 963", track_matched=False, car_matched=False)

    assert tracker.serialize() == {"tracks": ["Spa"], "cars": ["Porsche 963"]}


def test_record_dedupes_the_same_unmatched_track_across_many_different_cars():
    """The whole point of tracking unique values instead of unique setups:
    hundreds of setups sharing one unmatched track/car only ever need a
    single correction, not one per setup."""
    tracker = UnmatchedTracker()
    for car in [f"Car {i}" for i in range(400)]:
        tracker.record("Mystery Circuit", car, track_matched=False, car_matched=False)

    result = tracker.serialize()
    assert result["tracks"] == ["Mystery Circuit"]
    assert len(result["cars"]) == 400


def test_record_only_tracks_the_side_that_actually_failed_to_match():
    """A setup can be skipped with only one side unmatched (e.g. the car
    resolved fine, only the track didn't) - a side that already matched has
    nothing to correct, so it never shows up in either list."""
    tracker = UnmatchedTracker()
    tracker.record("Nordschleife", "Porsche 963", track_matched=False, car_matched=True)

    assert tracker.serialize() == {"tracks": ["Nordschleife"], "cars": []}


def test_record_keeps_track_and_car_dedup_independent():
    tracker = UnmatchedTracker()
    tracker.record("Nordschleife", "Porsche 963", track_matched=False, car_matched=True)
    tracker.record("Spa", "Porsche 963", track_matched=False, car_matched=False)

    assert tracker.serialize() == {"tracks": ["Nordschleife", "Spa"], "cars": ["Porsche 963"]}

from domain.unmatched import UnmatchedTracker


def test_serialize_returns_none_when_empty():
    tracker = UnmatchedTracker()
    assert tracker.serialize() is None


def test_record_and_serialize_round_trips():
    tracker = UnmatchedTracker()
    tracker.record("Spa", "Porsche 963", "tracktitan", track_matched=False, car_matched=False)

    assert tracker.serialize() == [
        {"track": "Spa", "car": "Porsche 963", "source": "tracktitan", "trackMatched": False, "carMatched": False},
    ]


def test_record_preserves_insertion_order():
    tracker = UnmatchedTracker()
    tracker.record("Spa", "Porsche 963", "tracktitan", track_matched=False, car_matched=False)
    tracker.record("Imola", "BMW M4", "dropbox", track_matched=False, car_matched=False)

    assert tracker.serialize() == [
        {"track": "Spa", "car": "Porsche 963", "source": "tracktitan", "trackMatched": False, "carMatched": False},
        {"track": "Imola", "car": "BMW M4", "source": "dropbox", "trackMatched": False, "carMatched": False},
    ]


def test_record_dedupes_identical_track_car_source():
    tracker = UnmatchedTracker()
    tracker.record("Spa", "Porsche 963", "tracktitan", track_matched=False, car_matched=False)
    tracker.record("Spa", "Porsche 963", "tracktitan", track_matched=False, car_matched=False)

    assert tracker.serialize() == [
        {"track": "Spa", "car": "Porsche 963", "source": "tracktitan", "trackMatched": False, "carMatched": False},
    ]


def test_record_keeps_entries_with_different_sources_separate():
    """The same raw (track, car) pair can legitimately show up from both
    TrackTitan and Dropbox in one run (e.g. Full mode) - each is its own
    correction target."""
    tracker = UnmatchedTracker()
    tracker.record("Spa", "Porsche 963", "tracktitan", track_matched=False, car_matched=False)
    tracker.record("Spa", "Porsche 963", "dropbox", track_matched=False, car_matched=False)

    assert tracker.serialize() == [
        {"track": "Spa", "car": "Porsche 963", "source": "tracktitan", "trackMatched": False, "carMatched": False},
        {"track": "Spa", "car": "Porsche 963", "source": "dropbox", "trackMatched": False, "carMatched": False},
    ]


def test_record_tracks_which_side_actually_failed_to_match():
    """A setup can be skipped with only one side unmatched (e.g. the car
    resolved fine, only the track didn't) - the correction dialog needs to
    know which, so it only asks for (and only persists) that field."""
    tracker = UnmatchedTracker()
    tracker.record("Nordschleife", "Porsche 963", "tracktitan", track_matched=False, car_matched=True)

    assert tracker.serialize() == [
        {
            "track": "Nordschleife", "car": "Porsche 963", "source": "tracktitan",
            "trackMatched": False, "carMatched": True,
        },
    ]

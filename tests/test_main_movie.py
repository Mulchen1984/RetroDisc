"""Main-movie heuristic on synthetic disc title structures."""
from src.services.main_movie import detect_main_movie, MainMovieConfig


def title(index, minutes, chapters=12, size=None):
    seconds = minutes * 60
    return {"index": index, "duration": seconds, "chapters": chapters,
            "size": size if size is not None else seconds * 1_000_000}


def test_no_titles_returns_none():
    assert detect_main_movie([]) is None


def test_clear_feature_among_extras_high_confidence():
    titles = [title(1, 2), title(2, 5), title(7, 117, chapters=24), title(8, 3)]
    r = detect_main_movie(titles)
    assert r.candidate == 7 and r.confidence >= 80
    assert r.duration == 117 * 60


def test_single_title_feature_length():
    r = detect_main_movie([title(1, 100)])
    assert r.candidate == 1 and r.confidence >= 80 and "einziger Titel" in r.reasons[0]


def test_single_title_below_feature_length_low_confidence():
    r = detect_main_movie([title(1, 5)])
    assert r.confidence <= 50 and any("Spielfilm" in x for x in r.reasons)


def test_episodic_equal_length_lowers_confidence():
    titles = [title(i, 45, chapters=6) for i in range(1, 7)]
    r = detect_main_movie(titles)
    assert r is not None and r.confidence <= 60
    assert any("gleich lange" in x for x in r.reasons)


def test_all_short_loops_flagged_below_feature():
    titles = [title(i, 1, chapters=1) for i in range(1, 20)]   # Menü-/Warnloops
    r = detect_main_movie(titles)
    assert r.confidence <= 40 and any("Spielfilm" in x for x in r.reasons)


def test_config_min_feature_length_is_respected():
    short_feature = [title(1, 30), title(2, 3)]
    strict = detect_main_movie(short_feature, MainMovieConfig(min_feature_seconds=2400))
    lenient = detect_main_movie(short_feature, MainMovieConfig(min_feature_seconds=1200))
    assert strict.confidence <= 40 and lenient.confidence > strict.confidence

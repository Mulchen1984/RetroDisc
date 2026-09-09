"""FFmpegProgressParser: normal, partial and end blocks."""
from src.services.transcode.progress import FFmpegProgressParser

BLOCK = """frame=120
fps=48.0
bitrate=5000.0kbits/s
total_size=1048576
out_time=00:00:05.00
speed=2.0x
progress=continue
"""


def test_normal_block_with_duration_gives_percent_and_eta():
    p = FFmpegProgressParser(total_duration=50.0)
    snaps = p.feed(BLOCK)
    assert len(snaps) == 1
    s = snaps[0]
    assert s.frame == 120 and s.fps == 48.0 and s.speed == 2.0
    assert s.out_time_seconds == 5.0 and s.percent == 10.0
    assert s.eta_seconds == round((50.0 - 5.0) / 2.0, 1)   # (45/2) = 22.5


def test_without_total_duration_no_percent_or_eta():
    s = FFmpegProgressParser().feed(BLOCK)[0]
    assert s.percent is None and s.eta_seconds is None and s.out_time_seconds == 5.0


def test_partial_and_unknown_lines_tolerated():
    p = FFmpegProgressParser(total_duration=10.0)
    assert p.feed_line("garbage-without-equals") is None
    assert p.feed_line("weird_key=whatever") is None       # unbekannter Key ok
    assert p.feed_line("out_time=00:00:02.00") is None     # noch kein Blockende
    snap = p.feed_line("progress=continue")
    assert snap is not None and snap.out_time_seconds == 2.0 and snap.percent == 20.0


def test_progress_end_is_100_percent():
    p = FFmpegProgressParser(total_duration=10.0)
    p.feed_line("out_time=00:00:09.00")
    snap = p.feed_line("progress=end")
    assert snap.status == "end" and snap.percent == 100.0


def test_out_time_us_fallback():
    p = FFmpegProgressParser(total_duration=10.0)
    p.feed_line("out_time_us=3000000")
    snap = p.feed_line("progress=continue")
    assert snap.out_time_seconds == 3.0


def test_na_speed_and_out_time_are_safe():
    p = FFmpegProgressParser(total_duration=10.0)
    p.feed_line("out_time=N/A"); p.feed_line("speed=N/A")
    snap = p.feed_line("progress=continue")
    assert snap.out_time_seconds == 0.0 and snap.speed == 0.0 and snap.eta_seconds is None

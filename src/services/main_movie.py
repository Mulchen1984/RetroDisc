"""Local main-movie heuristic. No DRM bypass — uses only title metadata.

Scores each title from legitimately available info (duration, size, chapters,
resolution) and returns a candidate with a confidence and human-readable
reasons. Confidence is deliberately conservative: near-equal long titles
(series/playlist decoys) and sub-feature-length discs lower it.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MainMovieConfig:
    min_feature_seconds: int = 2400          # 40 min: unter Spielfilmlänge -> niedrige Konfidenz
    weight_duration: float = 0.6
    weight_chapters: float = 0.2
    weight_size: float = 0.2
    near_equal_ratio: float = 0.90           # zwei Titel gelten als "gleich lang" ab 90 %


@dataclass
class MainMovieResult:
    candidate: int                           # title index/id
    confidence: int                          # 0..100
    duration: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"main_movie_candidate": self.candidate, "confidence": self.confidence,
                "duration": self.duration, "reasons": list(self.reasons)}


def _num(value) -> float:
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0


def detect_main_movie(titles: list[dict], config: MainMovieConfig | None = None):
    """Return a MainMovieResult or None if there are no titles."""
    config = config or MainMovieConfig()
    if not titles:
        return None

    durations = [_num(t.get("duration")) for t in titles]
    chapters = [_num(t.get("chapters")) for t in titles]
    sizes = [_num(t.get("size")) for t in titles]
    max_dur, max_ch, max_sz = max(durations) or 1, max(chapters) or 1, max(sizes) or 1

    scores = []
    for i, t in enumerate(titles):
        score = (config.weight_duration * durations[i] / max_dur
                 + config.weight_chapters * chapters[i] / max_ch
                 + config.weight_size * sizes[i] / max_sz)
        scores.append(score)

    order = sorted(range(len(titles)), key=lambda i: scores[i], reverse=True)
    best = order[0]
    best_id = titles[best].get("index", titles[best].get("id", best))
    best_dur = durations[best]
    reasons = [f"längster/größter Titel (Score {scores[best]:.2f})"]

    if len(titles) == 1:
        confidence = 90 if best_dur >= config.min_feature_seconds else 45
        reasons = ["einziger Titel"] + ([] if best_dur >= config.min_feature_seconds
                                        else ["unter Spielfilmlänge"])
        return MainMovieResult(best_id, confidence, best_dur, reasons)

    runner = order[1]
    margin = scores[best] - scores[runner]
    confidence = int(round(55 + 40 * min(1.0, margin * 2)))     # Abstand zum Zweitplatzierten

    if best_dur < config.min_feature_seconds:
        confidence = min(confidence, 40)
        reasons.append("unter Spielfilmlänge – evtl. kein Hauptfilm")

    # Mehrere gleich lange lange Titel -> Serie/Playlist-Decoys, Konfidenz senken.
    near_equal = [i for i in range(len(titles))
                  if i != best and best_dur > 0 and durations[i] >= best_dur * config.near_equal_ratio]
    if near_equal:
        confidence = min(confidence, 60)
        reasons.append(f"{len(near_equal)+1} etwa gleich lange Titel (evtl. Serie/Playlist)")

    confidence = max(5, min(99, confidence))
    return MainMovieResult(best_id, confidence, best_dur, reasons)

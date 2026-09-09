"""Platform-neutral Smart-Edit / Short models. No fake AI tracking or scores.

Reuses the shared DirectorModel base (extra='forbid') and MediaAsset so Smart
Edit stays consistent with Director/Restoration and never invents metadata.
"""
from typing import Literal
from pydantic import Field, model_validator
from src.models.director import DirectorModel, MediaAsset
import uuid


ASPECTS = {'9:16': (1080, 1920), '1:1': (1080, 1080), '16:9': (1920, 1080)}


class TimeRange(DirectorModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)

    @model_validator(mode='after')
    def _order(self):
        if self.end <= self.start:
            raise ValueError('Zeitbereich-Ende muss nach dem Start liegen.')
        return self

    @property
    def duration(self) -> float:
        return self.end - self.start


class SilenceSettings(DirectorModel):
    """Mission 12. Preset steuert die Mindestpausenlänge; nie Wörter anschneiden."""
    preset: Literal['off', 'natural', 'tight', 'compact'] = 'off'
    threshold_db: float = Field(default=-30.0, le=0, ge=-90)
    keep_padding: float = Field(default=0.15, ge=0, le=1.0)

    @property
    def min_silence(self) -> float:
        return {'off': 0.0, 'natural': 1.2, 'tight': 0.6, 'compact': 0.35}[self.preset]


class ReframeSettings(DirectorModel):
    """Mission 14/15. V1 = robuster Center-Crop; 'motion' braucht einen SubjectTracker-Provider."""
    mode: Literal['center', 'motion'] = 'center'
    smoothing: float = Field(default=0.85, ge=0, le=0.99)


class CaptionStyle(DirectorModel):
    """Mission 16. Plattformneutraler Stil; keine vorgetäuschte Wortanimation."""
    style: Literal['off', 'normal', 'modern'] = 'off'
    font_size: int = Field(default=28, ge=8, le=200)
    position: Literal['bottom', 'center', 'lower_third'] = 'bottom'
    max_words: int = Field(default=7, ge=1, le=40)
    outline: float = Field(default=2.0, ge=0, le=10)
    background: bool = False
    safe_margin: float = Field(default=0.08, ge=0, le=0.45)
    capitalization: Literal['none', 'upper'] = 'none'


class VoiceEnhanceSettings(DirectorModel):
    """Mission 17. FFmpeg-basiert, konservativ; keine ML-Abhängigkeit."""
    preset: Literal['off', 'natural', 'clear', 'strong'] = 'off'


class SmartEditProject(DirectorModel):
    """Mission 9/22. Editierbarer Short-/Smart-Edit-Plan über der Medienbibliothek."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex, pattern=r'^[a-f0-9]{32}$')
    title: str = 'RetroDisc Short'
    source_assets: list[MediaAsset] = Field(min_length=1, max_length=20)
    target_duration: float = Field(gt=0, le=600)
    aspect_ratio: Literal['9:16', '1:1', '16:9'] = '9:16'
    highlight_selection: list[TimeRange] = Field(default_factory=list, max_length=200)
    cuts: list[TimeRange] = Field(default_factory=list, max_length=1000)
    silence: SilenceSettings = Field(default_factory=SilenceSettings)
    remove_fillers: bool = False
    reframe: ReframeSettings = Field(default_factory=ReframeSettings)
    captions: CaptionStyle = Field(default_factory=CaptionStyle)
    audio_mode: Literal['keep', 'duck', 'mute'] = 'keep'
    voice_enhance: VoiceEnhanceSettings = Field(default_factory=VoiceEnhanceSettings)
    export_preset: Literal['youtube', 'youtube_shorts', 'tiktok', 'instagram_reels',
                           'tv_original', 'archive'] = 'youtube_shorts'
    planner: Literal['deterministic', 'ollama'] = 'deterministic'
    outputs: list[str] = Field(default_factory=list)
    report: dict = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    version: int = 1

    @model_validator(mode='after')
    def _within_sources(self):
        durations = {a.id: a.duration for a in self.source_assets}
        if len(durations) != len(self.source_assets):
            raise ValueError('Asset-IDs müssen eindeutig sein.')
        longest = max(durations.values()) if durations else 0.0
        for group, ranges in (('Highlight', self.highlight_selection), ('Schnitt', self.cuts)):
            for r in ranges:
                if r.end > longest + 0.05:
                    raise ValueError(f'{group}-Bereich liegt außerhalb der Quelldauer.')
        return self

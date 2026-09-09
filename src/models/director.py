"""Editable, validated production plans; paths refer to the existing media library."""
from __future__ import annotations
import math
import uuid
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class DirectorModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class MediaAsset(DirectorModel):
    id: str
    path: str
    kind: str
    duration: float = Field(ge=0)
    container: str = ''
    video_codec: str | None = None
    audio_codec: str | None = None
    width: int | None = None
    height: int | None = None
    origin: str = 'manual'
    title: str = ''
    transcript: dict | None = None
    description: str = ''


class Scene(DirectorModel):
    asset_id: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    position: float = Field(ge=0)
    transition: Literal['cut','fade','dip_black'] = 'cut'
    zoom: Literal['off','subtle','dynamic'] = 'off'


class Voiceover(DirectorModel):
    text: str = Field(min_length=1, max_length=10000)
    position: float = Field(ge=0)
    voice: str = ''
    language: str = 'de'
    max_duration: float | None = Field(default=None, gt=0)


class DubbingCue(DirectorModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    source_text: str
    translated_text: str | None = None
    speaker: str = 'speaker_1'
    voice: str = ''

    @model_validator(mode='after')
    def valid_range(self):
        if self.end <= self.start:
            raise ValueError('Dubbing-Ende muss nach Start liegen.')
        return self


class DubbingPlan(DirectorModel):
    asset_id: str
    source_language: str
    target_language: str
    cues: list[DubbingCue] = Field(default_factory=list, max_length=1000)
    original_audio: Literal['keep', 'duck', 'mute'] = 'duck'


class AudioPlacement(DirectorModel):
    asset_id: str
    position: float = Field(default=0,ge=0)
    start: float = Field(default=0,ge=0)
    duration: float = Field(gt=0)
    volume: float = Field(default=0.2,ge=0,le=2)
    fade_in: float = Field(default=0.2,ge=0,le=10)
    fade_out: float = Field(default=0.5,ge=0,le=10)
    duck: bool = True


class ProductionProject(DirectorModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex, pattern=r'^[a-f0-9]{32}$')
    prompt: str = Field(min_length=1, max_length=20000)
    title: str = 'RetroDisc Produktion'
    target_duration: float = Field(gt=0, le=600)
    planner: Literal['metadata', 'ollama'] = 'metadata'
    assets: list[MediaAsset] = Field(min_length=1, max_length=20)
    story: list[str] = Field(default_factory=list)
    timeline: list[Scene] = Field(min_length=1, max_length=100)
    voiceover: list[Voiceover] = Field(default_factory=list, max_length=30)
    original_audio: Literal['keep', 'duck', 'mute'] = 'duck'
    atmosphere: str = ''  # Creative intent only; no generated music implied.
    dubbing: DubbingPlan | None = None
    music: list[AudioPlacement] = Field(default_factory=list, max_length=8)
    sound_effects: list[AudioPlacement] = Field(default_factory=list, max_length=20)
    voiceover_enabled: bool = True
    original_volume: float = Field(default=1,ge=0,le=2)
    outputs: list[str] = Field(default_factory=list)
    generated_audio: list[str] = Field(default_factory=list)
    subtitle_paths: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_timeline(self):
        assets = {a.id:a for a in self.assets}
        if len(assets) != len(self.assets):
            raise ValueError('Asset-IDs müssen eindeutig sein.')
        if self.dubbing:
            asset=assets.get(self.dubbing.asset_id)
            if not asset or any(c.end > asset.duration for c in self.dubbing.cues):
                raise ValueError('Dubbing verweist auf ungültige Quelle/Zeitbereiche.')
        position = 0.0
        for scene in self.timeline:
            asset = assets.get(scene.asset_id)
            if not asset or asset.kind not in ('video','image'):
                raise ValueError('Szenen müssen auf ausgewählte Video-Assets verweisen.')
            if scene.end <= scene.start or (asset.kind!='image' and scene.end > asset.duration + 0.001):
                raise ValueError('Schnittbereich liegt außerhalb der Quelldauer.')
            if not math.isclose(scene.position, position, abs_tol=0.001):
                raise ValueError('Timeline muss ohne Lücken/Überlappungen angeordnet sein.')
            position += scene.end - scene.start
        for track in self.music+self.sound_effects:
            asset=assets.get(track.asset_id)
            if not asset or not asset.audio_codec or track.start+track.duration>asset.duration+0.001:
                raise ValueError('Audiotrack liegt außerhalb der Quelle.')
            if track.position+track.duration>position+0.001:
                raise ValueError('Audiotrack liegt außerhalb der Timeline.')
        if position > self.target_duration + 0.05:
            raise ValueError('Timeline überschreitet die Zieldauer.')
        if any(c.position >= position for c in self.voiceover):
            raise ValueError('Voiceover liegt außerhalb der Timeline.')
        return self

    @property
    def duration(self):
        return sum(s.end-s.start for s in self.timeline)


class PlanProposal(DirectorModel):
    """Only creative edits; source paths, metadata and output paths are immutable."""
    title: str
    story: list[str]
    timeline: list[Scene] = Field(min_length=1, max_length=100)
    voiceover: list[Voiceover] = Field(default_factory=list, max_length=30)
    atmosphere: str = ''

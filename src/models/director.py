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


class Transition(DirectorModel):
    type: Literal['cut','dissolve','fade','fade_from_black','fade_to_black','dip_black','fade_black','wipe_left','wipe_right','slide_left','slide_right','zoom','blur'] = 'cut'
    duration: float = Field(default=0.5,ge=0.25,le=3)
    easing: Literal['linear'] = 'linear'


class ClipEffects(DirectorModel):
    brightness: float = Field(default=0,ge=-0.2,le=0.2)
    contrast: float = Field(default=1,ge=0.5,le=1.5)
    saturation: float = Field(default=1,ge=0,le=2)
    warmth: float = Field(default=0,ge=-1,le=1)
    sharpen: float = Field(default=0,ge=0,le=1)
    blur: float = Field(default=0,ge=0,le=5)
    vignette: bool = False
    grayscale: bool = False
    sepia: bool = False


class Scene(DirectorModel):
    asset_id: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    position: float = Field(ge=0)
    transition: Transition | Literal['cut','fade','dip_black'] = 'cut'
    zoom: Literal['off','subtle','dynamic'] = 'off'
    effects: ClipEffects = Field(default_factory=ClipEffects)
    rotate: Literal[0,90,180,270] = 0
    flip_horizontal: bool = False
    flip_vertical: bool = False
    crop: Literal['original','16:9','9:16','1:1','4:3'] = 'original'
    speed: float = Field(default=1,ge=0.25,le=4)
    freeze_duration: float = Field(default=0,ge=0,le=60)
    volume: float = Field(default=1,ge=0,le=2)
    muted: bool = False
    locked: bool = False
    visible: bool = True
    audio_fade_in: float = Field(default=0,ge=0,le=10)
    audio_fade_out: float = Field(default=0,ge=0,le=10)

    @property
    def duration(self):return self.freeze_duration or (self.end-self.start)/self.speed

    @property
    def overlap(self):
        return self.transition.duration if isinstance(self.transition,Transition) and self.transition.type not in ('cut','fade_from_black','fade_to_black','dip_black') else 0



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


class TextClip(DirectorModel):
    text: str = Field(min_length=1,max_length=2000)
    start: float = Field(ge=0)
    duration: float = Field(gt=0)
    position: Literal['top','center','bottom','bottom_left','bottom_right'] = 'bottom'
    alignment: Literal['left','center','right'] = 'center'
    font_size: int = Field(default=40,ge=12,le=160)
    opacity: float = Field(default=1,ge=0,le=1)
    fade_in: float = Field(default=0,ge=0,le=3)
    fade_out: float = Field(default=0,ge=0,le=3)
    visible: bool = True
    locked: bool = False


class OverlayClip(DirectorModel):
    asset_id: str
    start: float = Field(ge=0)
    duration: float = Field(gt=0)
    source_start: float = Field(default=0,ge=0)
    x: int = Field(default=20,ge=0,le=1279)
    y: int = Field(default=20,ge=0,le=719)
    width: int = Field(default=320,ge=2,le=1280)
    height: int = Field(default=180,ge=2,le=720)
    opacity: float = Field(default=1,ge=0,le=1)
    volume: float = Field(default=0,ge=0,le=2)
    visible: bool = True
    muted: bool = False
    locked: bool = False


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
    text_clips: list[TextClip] = Field(default_factory=list,max_length=30)
    overlays: list[OverlayClip] = Field(default_factory=list,max_length=12)

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
        for index,scene in enumerate(self.timeline):
            if isinstance(scene.transition,Transition) and scene.transition.type!='cut' and scene.transition.duration>scene.duration:
                raise ValueError('Übergang ist länger als der Clip.')
            if scene.overlap:
                if index==0 or scene.overlap>min(scene.duration,self.timeline[index-1].duration)/2:
                    raise ValueError("Übergang ist länger als die verfügbare halbe Cliplänge oder hat keinen Vorgänger.")
                position-=scene.overlap
            asset = assets.get(scene.asset_id)
            if not asset or asset.kind not in ('video','image'):
                raise ValueError('Szenen müssen auf ausgewählte Video-Assets verweisen.')
            if scene.end <= scene.start or (asset.kind!='image' and scene.end > asset.duration + 0.001):
                raise ValueError('Schnittbereich liegt außerhalb der Quelldauer.')
            if not math.isclose(scene.position, position, abs_tol=0.001):
                raise ValueError('Timeline muss ohne Lücken/Überlappungen angeordnet sein.')
            position += scene.duration
        for item in self.text_clips+self.overlays:
            if item.start+item.duration>position+0.001:raise ValueError('Einblendung liegt außerhalb der Timeline.')
        for item in self.overlays:
            asset=assets.get(item.asset_id)
            if not asset or asset.kind not in ('video','image'):raise ValueError('Overlay-Asset fehlt oder ist ungeeignet.')
            if item.x+item.width>1280 or item.y+item.height>720:raise ValueError('Overlay liegt außerhalb des Bildes.')
            if asset.kind=='video' and item.source_start+item.duration>asset.duration+.001:raise ValueError('PIP ist länger als die Quelle.')
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
        return sum(s.duration-s.overlap for s in self.timeline)


class PlanProposal(DirectorModel):
    """Only creative edits; source paths, metadata and output paths are immutable."""
    title: str
    story: list[str]
    timeline: list[Scene] = Field(min_length=1, max_length=100)
    voiceover: list[Voiceover] = Field(default_factory=list, max_length=30)
    atmosphere: str = ''

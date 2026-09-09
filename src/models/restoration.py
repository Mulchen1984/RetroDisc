"""Conservative, reproducible restoration plans; optional providers are explicit."""
from typing import Literal
from pydantic import Field, model_validator
from src.models.director import DirectorModel, MediaAsset
import uuid


class RestorationAnalysis(DirectorModel):
    asset: MediaAsset
    source_size: int = 0
    source_mtime_ns: int = 0
    sample_seconds: float
    field_order: Literal['tff','bff','progressive','unknown']
    fps: float = Field(gt=0)
    sample_aspect_ratio: str
    display_aspect_ratio: str
    pixel_format: str
    color_space: str
    color_range: str
    bitrate: int | None = None
    levels: dict[str,float] = Field(default_factory=dict)
    noise_proxy: dict[str,float] = Field(default_factory=dict)
    idet: dict[str,int] = Field(default_factory=dict)
    uncertain: list[str] = Field(default_factory=list)


class RestorationOptions(DirectorModel):
    deinterlace: bool = False
    field_order: Literal['auto','tff','bff'] = 'auto'
    deinterlacer: Literal['bwdif','yadif'] = 'bwdif'
    denoise: bool = True
    stabilize: bool = False
    color: bool = True
    sharpen: bool = True
    size: Literal['original','720p','1080p'] = 'original'
    audio: bool = False


class RestorationSceneAnalysis(DirectorModel):
    brightness: float | None = None
    contrast: float | None = None
    noise_indicator: float | None = None
    movement: float | None = None
    dark: bool = False
    note: str = 'Stichprobe; Bewegung/Textur können den Rauschindikator beeinflussen.'


class SceneRestoration(DirectorModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    options: RestorationOptions
    analysis: RestorationAnalysis | None = None
    metrics: RestorationSceneAnalysis | None = None
    denoise_strength: tuple[float, float, float, float] | None = None
    sharpen_amount: float = Field(default=0.15, ge=0, le=0.35)

    @model_validator(mode='after')
    def valid_interval(self):
        if self.end<=self.start:raise ValueError('Szenenende muss nach dem Start liegen.')
        if self.denoise_strength and any(not 0 <= x <= 6 for x in self.denoise_strength):
            raise ValueError('Rauschfilter außerhalb des konservativen Bereichs.')
        return self


class RestorationPlan(DirectorModel):
    id: str = Field(default_factory=lambda:uuid.uuid4().hex,pattern=r'^[a-f0-9]{32}$')
    analysis: RestorationAnalysis
    preset: Literal['natural','balanced','strong'] = 'natural'
    options: RestorationOptions = Field(default_factory=RestorationOptions)
    scenes: list[SceneRestoration] = Field(default_factory=list)
    capabilities: dict = Field(default_factory=dict)
    provider: Literal['ffmpeg'] = 'ffmpeg'
    version: int = 1
    preview: list[str] = Field(default_factory=list)
    preview_signature: str = ''
    outputs: list[str] = Field(default_factory=list)
    filters: list[str] = Field(default_factory=list)
    tool_version: str = ''
    source_sha256: str = ''
    output_sha256: dict[str,str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)

    report: dict = Field(default_factory=dict)
    archives: list[dict] = Field(default_factory=list)

    @model_validator(mode='after')
    def scene_bounds(self):
        if len(self.scenes)>30:raise ValueError('Maximal 30 Restaurationsabschnitte.')
        position=0.0
        for scene in self.scenes:
            if abs(scene.start-position)>0.001 or scene.end>self.analysis.asset.duration+0.001:
                raise ValueError('Szenen müssen die Quelle lückenlos und ohne Überlappung abdecken.')
            position=scene.end
        if self.scenes and abs(position-self.analysis.asset.duration)>0.001:
            raise ValueError('Szenen müssen die gesamte Quelle abdecken.')
        return self

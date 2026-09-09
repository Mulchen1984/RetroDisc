"""Smart Edit / Short: pure planning helpers, validated models, persistence, safety."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from pydantic import ValidationError
from src.models.director import MediaAsset
from src.models.smart_edit import (
    ASPECTS, CaptionStyle, ReframeSettings, SilenceSettings, SmartEditProject,
    TimeRange, VoiceEnhanceSettings,
)
from src.services.smart_edit import SmartEditor, _SOCIAL_PROFILES


def asset(duration=30.0, audio='aac', transcript=None):
    return MediaAsset(id='vid', path='clip.mp4', kind='video', duration=duration,
                      width=1920, height=1080, video_codec='h264', audio_codec=audio, transcript=transcript)


def project(**kw):
    base = dict(source_assets=[asset()], target_duration=15.0, aspect_ratio='9:16')
    base.update(kw)
    return SmartEditProject(**base)


# ── Models ───────────────────────────────────────────────────────────────────
def test_timerange_and_project_reject_out_of_bounds():
    with pytest.raises(ValidationError):
        TimeRange(start=5, end=5)
    with pytest.raises(ValidationError):
        project(highlight_selection=[TimeRange(start=0, end=40)])  # beyond 30s source
    with pytest.raises(ValidationError):
        SmartEditProject(source_assets=[asset()], target_duration=0, aspect_ratio='9:16')
    with pytest.raises(ValidationError):
        SmartEditProject.model_validate(project().model_dump() | {'aspect_ratio': '4:3'})


def test_silence_preset_maps_to_min_length():
    assert SilenceSettings(preset='off').min_silence == 0.0
    assert SilenceSettings(preset='natural').min_silence == 1.2
    assert SilenceSettings(preset='compact').min_silence == 0.35


# ── Reframe (Mission 14) ───────────────────────────────────────────────────────
@pytest.mark.parametrize('aspect', ['9:16', '1:1', '16:9'])
def test_reframe_targets_canonical_size_with_even_center_crop(aspect):
    chain, size = SmartEditor.reframe_filter(aspect)
    assert size == ASPECTS[aspect]
    assert chain.startswith('crop=') and f'scale={size[0]}:{size[1]}' in chain and chain.endswith('setsar=1')
    assert '/2)*2' in chain  # even dimensions guaranteed


# ── Silence planning (Mission 12) ──────────────────────────────────────────────
def test_silence_off_keeps_whole_clip():
    keep = SmartEditor.plan_silence_segments(30, [(5, 10)], SilenceSettings(preset='off'))
    assert [(k.start, k.end) for k in keep] == [(0.0, 30)]


def test_silence_only_cuts_long_gaps_and_keeps_padding():
    keep = SmartEditor.plan_silence_segments(
        30, [(5, 7), (12, 12.4), (20, 23)], SilenceSettings(preset='natural', keep_padding=0.2))
    spans = [(round(k.start, 2), round(k.end, 2)) for k in keep]
    assert spans == [(0.0, 5.2), (6.8, 20.2), (22.8, 30.0)]  # short 12–12.4 gap survives


def test_silence_never_produces_empty_or_negative_segments():
    keep = SmartEditor.plan_silence_segments(4, [(0, 4)], SilenceSettings(preset='compact', keep_padding=0.0))
    assert keep and all(k.end > k.start for k in keep)


# ── Caption retiming + fillers (Missionen 13/16) ───────────────────────────────
def test_retime_drops_captions_that_fall_into_cuts():
    keep = [TimeRange(start=0, end=5), TimeRange(start=10, end=15)]
    out = SmartEditor.retime_segments([(1, 2, 'a'), (6, 7, 'gap'), (11, 12, 'b')], keep)
    # 'a' stays at 1–2; 'gap' (6–7) was cut; 'b' (11–12) shifts to 6–7 on the cut timeline.
    assert out == [(1.0, 2.0, 'a'), (6.0, 7.0, 'b')]


def test_strip_fillers_only_removes_pure_filler_segments():
    segs = [(0, 1, 'ähm'), (1, 2, 'also gut'), (2, 3, 'UH'), (3, 4, 'echtes Wort')]
    assert SmartEditor.strip_fillers(segs) == [(1, 2, 'also gut'), (3, 4, 'echtes Wort')]


# ── Highlight fallback + LLM validation (Mission 11) ───────────────────────────
def test_highlight_fallback_stays_within_media():
    ranges = SmartEditor.highlight_fallback([(0, 1, 'x')], target=15, duration=30)
    assert len(ranges) == 1 and 0 <= ranges[0].start and ranges[0].end <= 30
    assert abs(ranges[0].duration - 15) < 0.01
    empty = SmartEditor.highlight_fallback([], target=100, duration=30)
    assert empty[0].end == 30  # target clamped to duration


def test_validate_ranges_clamps_and_rejects_llm_hallucinations():
    out = SmartEditor.validate_ranges([(-5, 10), (25, 999), (8, 8.01)], duration=30)
    assert [(r.start, r.end) for r in out] == [(0.0, 10.0), (25.0, 30.0)]  # padded + clamped, tiny dropped


# ── Voice enhance (Mission 17) ─────────────────────────────────────────────────
def test_voice_enhance_presets_are_conservative_and_off_is_empty():
    assert SmartEditor.voice_enhance_af(VoiceEnhanceSettings(preset='off')) == ''
    for preset in ('natural', 'clear', 'strong'):
        chain = SmartEditor.voice_enhance_af(VoiceEnhanceSettings(preset=preset))
        assert 'highpass' in chain and 'loudnorm' in chain


# ── ASS captions (Mission 16) ──────────────────────────────────────────────────
def test_build_ass_chunks_words_and_applies_style():
    style = CaptionStyle(style='modern', max_words=3, capitalization='upper', position='lower_third')
    ass = SmartEditor.build_ass([(0, 3, 'one two three four five')], style, (1080, 1920))
    assert 'ScriptType: v4.00+' in ass and 'PlayResY: 1920' in ass
    assert ass.count('Dialogue:') == 2  # 5 words / 3 per chunk
    assert 'ONE TWO THREE' in ass and 'FOUR FIVE' in ass


def test_build_ass_off_style_and_braces_are_escaped():
    ass = SmartEditor.build_ass([(0, 1, 'a {b} c')], CaptionStyle(style='normal', max_words=10), (1080, 1920))
    assert '{b}' not in ass and '(b)' in ass  # no ASS override injection


# ── Social profiles (Mission 19) ──────────────────────────────────────────────
def test_export_profiles_cover_platforms_and_shorts_are_vertical():
    assert {'youtube', 'youtube_shorts', 'tiktok', 'instagram_reels', 'tv_original', 'archive'} <= set(_SOCIAL_PROFILES)
    preset = SmartEditor.export_preset('tiktok', (1080, 1920))
    assert preset.resolution == '1080:1920' and preset.video_codec == 'libx264' and preset.audio_codec == 'aac'
    archive = SmartEditor.export_preset('archive', None)
    assert archive.video_codec == 'ffv1' and archive.container == 'mkv'


# ── Subject tracker (Mission 15) ───────────────────────────────────────────────
def test_subject_tracker_is_architecture_only():
    assert SmartEditor.subject_tracker_capability()['level'] == 'unavailable'


# ── Caption-burn capability, both states (Mission 4) ──────────────────────────
@pytest.mark.asyncio
async def test_capabilities_enable_caption_burn_only_with_libass(tmp_path):
    editor = SmartEditor(SimpleNamespace(db_path=tmp_path / 'l.db'), None, tmp_path / 'o', tmp_path / 't')
    editor.ffmpeg = SimpleNamespace(ffmpeg_path='ffmpeg',
        available_video_encoders=AsyncMock(return_value={'libx264', 'h264_videotoolbox'}))
    editor._run = AsyncMock(return_value=(
        ' ... subtitles     V->V\n ... silencedetect A->A\n ... afftdn A->A\n'
        ' ... loudnorm A->A\n ... acompressor A->A', ''))
    caps = await editor.capabilities()
    assert caps['captions'] is True and caps['silence_detection'] is True
    assert 'h264_videotoolbox' in caps['hardware_encode']
    assert caps['reframe']['subject_tracker']['level'] == 'unavailable'

    editor._run = AsyncMock(return_value=(' ... silencedetect A->A\n ... loudnorm A->A', ''))
    caps_no_ass = await editor.capabilities()
    assert caps_no_ass['captions'] is False        # burn must be reported unavailable up front
    assert caps_no_ass['silence_detection'] is True


# ── Persistence + safety (Mission 22) ──────────────────────────────────────────
def test_save_load_roundtrip_and_id_guard(tmp_path):
    editor = SmartEditor(SimpleNamespace(db_path=tmp_path / 'library.db'), None, tmp_path / 'out', tmp_path / 'temp')
    p = project(captions=CaptionStyle(style='modern'), silence=SilenceSettings(preset='tight'))
    editor.save(p)
    assert editor.load(p.id) == p
    with pytest.raises(ValueError):
        editor.load('../../secrets')


def test_select_expr_uses_only_real_ranges():
    keep = [TimeRange(start=0, end=2), TimeRange(start=5, end=7)]
    assert SmartEditor._select_expr(keep) == 'between(t,0.0,2.0)+between(t,5.0,7.0)'


# ── Robustness + LLM reuse (Missionen 11/28) ──────────────────────────────────
@pytest.mark.asyncio
async def test_render_short_missing_source_fails_before_ffmpeg(tmp_path):
    editor = SmartEditor(SimpleNamespace(db_path=tmp_path / 'l.db'), None, tmp_path / 'out', tmp_path / 'temp')
    gone = asset()
    gone.path = str(tmp_path / 'does_not_exist.mp4')
    with pytest.raises(FileNotFoundError):
        await editor.render_short(project(source_assets=[gone]))
    assert not (tmp_path / 'out').exists()  # nothing created on the failure path


@pytest.mark.asyncio
async def test_select_highlights_deterministic_without_transcript(tmp_path):
    editor = SmartEditor(SimpleNamespace(db_path=tmp_path / 'l.db'), None, tmp_path / 'o', tmp_path / 't')
    ranges = await editor.select_highlights(project())  # no transcript, no director
    assert len(ranges) == 1 and 0 <= ranges[0].start and ranges[0].end <= 30


@pytest.mark.asyncio
async def test_select_highlights_uses_llm_and_rejects_hallucinated_times(tmp_path):
    editor = SmartEditor(SimpleNamespace(db_path=tmp_path / 'l.db'), None, tmp_path / 'o', tmp_path / 't')
    a = asset(transcript={'segments': [{'start': 0, 'end': 5, 'text': 'hi'}, {'start': 5, 'end': 10, 'text': 'yo'}]})
    p = project(source_assets=[a], planner='ollama')

    class GoodDirector:
        async def select_time_ranges(self, asset, segments, target, wish='', model=''):
            return [(2, 8), (100, 200)]  # second range is outside the 30s media → must be dropped

    ranges = await editor.select_highlights(p, director=GoodDirector())
    assert [(r.start, r.end) for r in ranges] == [(2.0, 8.0)]


@pytest.mark.asyncio
async def test_select_highlights_falls_back_when_llm_offline(tmp_path):
    editor = SmartEditor(SimpleNamespace(db_path=tmp_path / 'l.db'), None, tmp_path / 'o', tmp_path / 't')
    a = asset(transcript={'segments': [{'start': 0, 'end': 5, 'text': 'hi'}]})
    p = project(source_assets=[a], planner='ollama')

    class Offline:
        async def select_time_ranges(self, *args, **kwargs):
            raise RuntimeError('Ollama offline')

    ranges = await editor.select_highlights(p, director=Offline())
    assert len(ranges) == 1 and ranges[0].end <= 30  # deterministic fallback, never fatal

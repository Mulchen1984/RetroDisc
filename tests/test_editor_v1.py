import pytest
from src.models.director import MediaAsset,Scene,ProductionProject,Transition,OverlayClip,TextClip
from src.services.timeline import edit,TimelineHistory
from src.services.editor_filters import tempo,join_graph


def project():
    return ProductionProject(prompt='edit',target_duration=20,assets=[MediaAsset(id='v',path='v.mp4',kind='video',duration=10,audio_codec='aac')],
        timeline=[Scene(asset_id='v',start=0,end=4,position=0),Scene(asset_id='v',start=4,end=8,position=4)])


def test_transition_audio_same_overlap():
    p=edit(project(),'transition',1,{'value':{'type':'dissolve','duration':.5}})
    assert p.duration==7.5 and p.timeline[1].position==3.5
    graph,_,_=join_graph(p.timeline)
    assert any('acrossfade=d=0.5' in f for f in graph)
    assert any('offset=3.5' in f for f in graph)


@pytest.mark.parametrize('value',[{'type':'bogus'},{'type':'dissolve','duration':3},{'type':'zoom','duration':-1}])
def test_invalid_transition(value):
    with pytest.raises(ValueError):edit(project(),'transition',1,{'value':value})


@pytest.mark.parametrize('speed',[.25,.5,2,4])
def test_speed_split(speed):
    p=edit(project(),'speed',0,{'value':speed});length=p.duration
    p=edit(p,'split',0,{'time':2})
    assert p.duration==length and p.timeline[1].position==2/speed


def test_freeze_lock_undo():
    h=TimelineHistory(project());p=h.apply('freeze',0,{'time':2,'duration':2})
    assert p.duration==10 and p.timeline[1].freeze_duration==2
    assert h.undo().duration==8 and h.redo().duration==10
    h.apply('lock',0,{'value':True})
    with pytest.raises(ValueError,match='gesperrt'):h.apply('trim',0,{'end':1})
    assert h.current().timeline[0].end==2


def test_overlay_text_bounds_and_persistence():
    p=project();p=edit(p,'add_text',values={'text':'Ä & <title>','start':0,'duration':2})
    p=edit(p,'add_overlay',values={'asset':p.assets[0].model_dump(),'overlay':{'asset_id':'v','start':0,'duration':2}})
    assert ProductionProject.model_validate_json(p.model_dump_json())==p
    removed=edit(p,'text_control',0,{'remove':True})
    assert not removed.text_clips and p.text_clips
    p=edit(p,'overlay_control',0,{'locked':True})
    with pytest.raises(ValueError):edit(p,'overlay_control',0,{'visible':False})
    with pytest.raises(ValueError):edit(p,'add_text',values={'text':'Too long','start':7,'duration':3})


def test_atempo_chain():
    assert tempo(4)=='atempo=2,atempo=2.0'
    assert tempo(.25)=='atempo=0.5,atempo=0.5'


def test_effects_transform_and_lock_protects_position():
    from src.services.editor_filters import clip_filters
    p=edit(project(),'effects',0,{'preset':'warm'})
    p=edit(p,'transform',0,{'crop':'1:1','rotate':90,'flip_horizontal':True})
    filters=clip_filters(p.timeline[0])
    assert filters[0]=='transpose=1' and 'hflip' in filters
    assert any(f.startswith('crop=') for f in filters)
    assert any(f.startswith('colorbalance=') for f in filters)
    p=edit(p,'lock',1,{'value':True})
    with pytest.raises(ValueError,match='gesperrten'):edit(p,'trim',0,{'end':2})


@pytest.mark.asyncio
async def test_cancel_cleans_editor_staging(tmp_path,monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from src.services.director import Director
    from src.services.converter import Converter
    p=project()
    lib=SimpleNamespace(db_path=tmp_path/'db',asset=AsyncMock(return_value=p.assets[0]))
    director=Director(lib,None,None,tmp_path/'out',tmp_path/'audio',tmp_path/'temp')
    monkeypatch.setattr(Converter,'convert_file',AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):await director.render(p)
    assert not list((tmp_path/'out').iterdir())
    assert not list((tmp_path/'temp').iterdir())


def test_suggestions_are_explicit_and_undoable():
    from src.services.timeline import suggestions
    p=project();before=p.model_dump()
    rows=suggestions(p)
    assert p.model_dump()==before and rows[0]['profile']=='gentle'
    h=TimelineHistory(p);changed=h.apply('suggestion',values={'profile':'gentle'})
    assert changed.timeline[1].overlap==.5 and changed.timeline[0].effects.warmth==.2
    assert h.undo()==p


def test_text_preset_and_local_fade_duration():
    p=edit(project(),'add_text',values={'text':'Titel','start':0,'duration':2})
    p=edit(p,'text_control',0,{'preset':'lower_third'})
    assert p.text_clips[0].alignment=='left' and p.text_clips[0].font_size==32
    p=edit(p,'transition',0,{'value':{'type':'fade_to_black','duration':1}})
    assert p.timeline[0].overlap==0 and p.duration==8

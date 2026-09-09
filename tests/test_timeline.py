import pytest
from pydantic import ValidationError
from src.models.director import MediaAsset,ProductionProject,Scene
from src.services.timeline import edit,TimelineHistory


def project():
    return ProductionProject(prompt='test',target_duration=8,assets=[MediaAsset(id='v',path='v.mp4',kind='video',duration=10)],
        timeline=[Scene(asset_id='v',start=0,end=4,position=0),Scene(asset_id='v',start=5,end=9,position=4)])


def test_split_trim_move_delete():
    p=project();p=edit(p,'split',0,{'time':2})
    assert [(s.start,s.end,s.position) for s in p.timeline]==[(0,2,0),(2,4,2),(5,9,4)]
    p=edit(p,'trim',1,{'start':2.5});assert p.timeline[2].position==3.5
    p=edit(p,'move',2,{'target':0});assert p.timeline[0].start==5
    p=edit(p,'delete',1);assert len(p.timeline)==2 and p.timeline[1].position==4


@pytest.mark.parametrize('operation,values',[('split',{'time':0}),('trim',{'end':20}),('move',{'target':9})])
def test_invalid_edits_preserve_original(operation,values):
    p=project();before=p.model_dump()
    with pytest.raises(ValueError):edit(p,operation,0,values)
    assert p.model_dump()==before


def test_audio_controls_and_image_duration():
    p=edit(project(),'audio',values={'original_volume':.3,'voiceover_enabled':False})
    assert p.original_volume==.3 and not p.voiceover_enabled
    data=p.model_dump();data['assets'][0].update(kind='image',duration=0)
    assert ProductionProject.model_validate(data).duration==8


def test_history_undo_redo_roundtrip():
    h=TimelineHistory(project())
    assert not h.can_undo and not h.can_redo
    h.apply('split',0,{'time':2})
    h.apply('delete',0)
    assert [(s.start,s.end) for s in h.current().timeline]==[(2,4),(5,9)]
    assert h.can_undo and not h.can_redo
    # undo delete, then undo split -> zurück am Original
    h.undo(); assert len(h.current().timeline)==3
    h.undo(); assert [(s.start,s.end) for s in h.current().timeline]==[(0,4),(5,9)]
    assert not h.can_undo and h.can_redo
    # redo split
    h.redo(); assert len(h.current().timeline)==3


def test_new_edit_after_undo_discards_redo_branch():
    h=TimelineHistory(project())
    h.apply('split',0,{'time':2})
    h.apply('trim',0,{'end':1})
    h.undo()                      # zurück nach split, redo verfügbar
    assert h.can_redo
    h.apply('delete',0)           # neue Änderung -> Redo-Zweig verworfen
    assert not h.can_redo
    st=h.state()
    assert st['can_undo'] and not st['can_redo'] and 'plan' in st


def test_invalid_edit_leaves_history_intact():
    h=TimelineHistory(project())
    h.apply('split',0,{'time':2})
    before=h.state()
    with pytest.raises(ValueError):
        h.apply('trim',0,{'end':999})   # außerhalb Quelldauer
    assert h.state()==before             # History unverändert, Projekt bleibt valide


def test_history_is_bounded():
    h=TimelineHistory(project(),limit=5)
    for _ in range(20):
        h.apply('trim',0,{'end':4})
    assert h.state()['depth']<=5

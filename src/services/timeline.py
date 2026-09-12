"""Pure project edits: no rendering, no second persisted timeline format."""
from src.models.director import ProductionProject,Scene


def edit(project,operation,index=0,values=None):
    data=project.model_dump();scenes=data['timeline'];values=values or {}
    if operation in ('trim','split','delete','move','transition','zoom','speed','freeze','clip_audio','visibility','lock','effects','transform'):
        if not 0<=index<len(scenes):raise ValueError('Clip nicht gefunden.')
        scene=scenes[index]
        if scene.get("freeze_duration") and operation in ("split","speed","freeze"):
            raise ValueError("Standbild kann nicht erneut geteilt oder beschleunigt werden.")
        if scene.get("locked") and operation!="lock":raise ValueError("Clip ist gesperrt.")
        if operation=='trim':
            scene['start']=float(values.get('start',scene['start']))
            scene['end']=float(values.get('end',scene['end']))
        elif operation=='split':
            cut=float(values['time'])
            if not scene['start']<cut<scene['end']:raise ValueError('Teilpunkt muss innerhalb des Clips liegen.')
            scenes[index:index+1]=[scene|{'end':cut},scene|{'start':cut,'transition':'cut'}]
        elif operation=='effects':
            from src.services.editor_filters import EFFECT_PRESETS
            scene['effects']=EFFECT_PRESETS[values['preset']] if 'preset' in values else values
        elif operation=='transform':
            for key in ('rotate','flip_horizontal','flip_vertical','crop'):
                if key in values:scene[key]=values[key]
        elif operation=='speed':scene['speed']=float(values['value'])
        elif operation=='freeze':
            cut=float(values['time']);length=float(values.get('duration',2))
            if not scene['start']<cut<scene['end']:raise ValueError('Standbild-Zeitpunkt muss innerhalb des Clips liegen.')
            scenes[index:index+1]=[scene|{'end':cut},scene|{'start':cut,'freeze_duration':length,'transition':'cut'},scene|{'start':cut,'transition':'cut'}]
        elif operation=='clip_audio':
            for key in ('volume','muted','audio_fade_in','audio_fade_out'):
                if key in values:scene[key]=values[key]
        elif operation=='visibility':scene['visible']=bool(values['value'])
        elif operation=='lock':scene['locked']=bool(values['value'])
        elif operation=='delete':
            if len(scenes)==1:raise ValueError('Mindestens ein Clip muss erhalten bleiben.')
            scenes.pop(index)
        elif operation=='move':
            target=int(values['target'])
            if not 0<=target<len(scenes):raise ValueError('Ungültige Zielposition.')
            scenes.insert(target,scenes.pop(index))
        else:scene[operation]=values['value']
    elif operation=='suggestion':
        profile=values['profile']
        if profile not in ('slideshow','gentle','cuts'):raise ValueError('Unbekannter Vorschlag.')
        for i,scene in enumerate(scenes):
            if scene.get('locked'):continue
            overlap=min(.5,Scene.model_validate(scene).duration/2,Scene.model_validate(scenes[i-1]).duration/2) if i else 0
            scene['transition']={'type':'dissolve','duration':overlap} if profile!='cuts' and overlap>=.25 else 'cut'
            if profile=='slideshow':scene['zoom']='subtle'
            if profile=='gentle':scene['effects']={'warmth':.2,'saturation':1.03}
    elif operation=='add_text':data['text_clips'].append(values)
    elif operation=='add_overlay':
        asset=values['asset']
        if not any(a['id']==asset['id'] for a in data['assets']):data['assets'].append(asset)
        data['overlays'].append(values['overlay'])
    elif operation in ('text_control','overlay_control'):
        collection=data['text_clips'] if operation=='text_control' else data['overlays']
        if not 0<=index<len(collection):raise ValueError('Track nicht gefunden.')
        item=collection[index]
        if item.get('locked') and any(k!='locked' for k in values):raise ValueError('Track ist gesperrt.')
        if operation=='text_control' and 'preset' in values:
            from src.services.editor_filters import TEXT_PRESETS
            values=TEXT_PRESETS[values['preset']]
        if values.get('remove'):collection.pop(index)
        else:item.update(values)
    elif operation=='audio':
        for key in ('original_volume','original_audio','voiceover_enabled'):
            if key in values:data[key]=values[key]
    else:raise ValueError('Unbekannte Timeline-Aktion.')
    position=0
    for scene in scenes:
        model=Scene.model_validate(scene)
        position-=model.overlap
        scene['position']=position;position+=model.duration
    # Tracks stay at their explicit absolute positions. Never silently drop speech/music.
    data['target_duration']=max(data['target_duration'],position)
    for old_index,old in enumerate(project.timeline):
        if old.locked and not (operation=='lock' and old_index==index) and old.model_dump() not in scenes:
            raise ValueError('Änderung würde einen gesperrten Clip verschieben.')
    return ProductionProject.model_validate(data)


class TimelineHistory:
    """Bounded snapshot undo/redo over ProductionProject states. No media is touched.

    Snapshot-based (not event sourcing): each edit stores the full validated
    project, so every field (trim, split, move, delete, audio, caption, …) is
    covered automatically. A new edit after undo discards the redo branch.
    """

    def __init__(self, project, limit=50):
        self._limit = max(2, int(limit))
        self._states = [self._dump(project)]
        self._index = 0

    @staticmethod
    def _dump(project):
        # Accept a model or an already-validated dict/JSON; always store a plain dict.
        if isinstance(project, ProductionProject):
            return project.model_dump()
        if isinstance(project, str):
            return ProductionProject.model_validate_json(project).model_dump()
        return ProductionProject.model_validate(project).model_dump()

    def current(self):
        return ProductionProject.model_validate(self._states[self._index])

    @property
    def can_undo(self):
        return self._index > 0

    @property
    def can_redo(self):
        return self._index < len(self._states) - 1

    def apply(self, operation, index=0, values=None):
        # edit() validates and raises on invalid input; on failure the history
        # is left untouched so the project stays valid.
        new = edit(self.current(), operation, index, values)
        del self._states[self._index + 1:]          # drop redo branch
        self._states.append(new.model_dump())
        if len(self._states) > self._limit:
            self._states.pop(0)
        self._index = len(self._states) - 1
        return new

    def undo(self):
        if self.can_undo:
            self._index -= 1
        return self.current()

    def redo(self):
        if self.can_redo:
            self._index += 1
        return self.current()

    def state(self):
        """UI-facing snapshot: current plan plus button-enable flags."""
        return {'plan': self._states[self._index],
                'can_undo': self.can_undo, 'can_redo': self.can_redo,
                'depth': len(self._states), 'index': self._index}


def suggestions(project):
    images=all(next(a for a in project.assets if a.id==s.asset_id).kind=='image' for s in project.timeline)
    if images:
        return [{'profile':'slideshow','title':'Ruhige Slideshow','detail':'Dezenter Zoom und kurze Überblendungen; keine Motiverkennung.'}]
    if project.duration/len(project.timeline)<3:
        return [{'profile':'cuts','title':'Kurze Clips klar schneiden','detail':'Cuts statt langer Übergänge. Begründung: kurze Cliplängen, keine Action-Erkennung.'}]
    return [{'profile':'gentle','title':'Sanfter Schnitt','detail':'Kurze Dissolves und leichter Warm-Look. Vorschlag nur anhand der Cliplängen.'}]

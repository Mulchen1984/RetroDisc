"""Pure project edits: no rendering, no second persisted timeline format."""
from src.models.director import ProductionProject


def edit(project,operation,index=0,values=None):
    data=project.model_dump();scenes=data['timeline'];values=values or {}
    if operation in ('trim','split','delete','move','transition','zoom'):
        if not 0<=index<len(scenes):raise ValueError('Clip nicht gefunden.')
        scene=scenes[index]
        if operation=='trim':
            scene['start']=float(values.get('start',scene['start']))
            scene['end']=float(values.get('end',scene['end']))
        elif operation=='split':
            cut=float(values['time'])
            if not scene['start']<cut<scene['end']:raise ValueError('Teilpunkt muss innerhalb des Clips liegen.')
            scenes[index:index+1]=[scene|{'end':cut},scene|{'start':cut,'transition':'cut'}]
        elif operation=='delete':
            if len(scenes)==1:raise ValueError('Mindestens ein Clip muss erhalten bleiben.')
            scenes.pop(index)
        elif operation=='move':
            target=int(values['target'])
            if not 0<=target<len(scenes):raise ValueError('Ungültige Zielposition.')
            scenes.insert(target,scenes.pop(index))
        else:scene[operation]=values['value']
    elif operation=='audio':
        for key in ('original_volume','original_audio','voiceover_enabled'):
            if key in values:data[key]=values[key]
    else:raise ValueError('Unbekannte Timeline-Aktion.')
    position=0
    for scene in scenes:
        scene['position']=position;position+=scene['end']-scene['start']
    # Tracks stay at their explicit absolute positions. Never silently drop speech/music.
    data['target_duration']=max(data['target_duration'],position)
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

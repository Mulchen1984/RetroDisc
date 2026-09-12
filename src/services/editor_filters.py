"""Small FFmpeg helpers for the existing Director renderer."""
TRANSITIONS={'dissolve':'fade','fade':'fade','fade_black':'fadeblack','wipe_left':'wipeleft',
             'wipe_right':'wiperight','slide_left':'slideleft','slide_right':'slideright',
             'zoom':'zoomin','blur':'hblur'}


def tempo(speed):
    values=[]
    while speed>2:values.append('atempo=2');speed/=2
    while speed<.5:values.append('atempo=0.5');speed/=.5
    values.append(f'atempo={speed}')
    return ','.join(values)


def join_graph(scenes):
    """Normalise all inputs; overlap video and audio by the same duration."""
    graph=[]
    for i,s in enumerate(scenes):
        graph += [f'[{2*i}:v]fps=30,settb=AVTB,setpts=PTS-STARTPTS,format=yuv420p[v{i}]',
                  f'[{2*i+1}:a]atrim=duration={s.duration},asetpts=PTS-STARTPTS[a{i}]']
    video,audio='v0','a0';elapsed=scenes[0].duration
    for i,s in enumerate(scenes[1:],1):
        if s.overlap:
            graph += [f'[{video}][v{i}]xfade=transition={TRANSITIONS[s.transition.type]}:duration={s.overlap}:offset={elapsed-s.overlap}[jv{i}]',
                      f'[{audio}][a{i}]acrossfade=d={s.overlap}:c1=tri:c2=tri[ja{i}]']
        else:
            graph += [f'[{video}][v{i}]concat=n=2:v=1:a=0[jv{i}]',f'[{audio}][a{i}]concat=n=2:v=0:a=1[ja{i}]']
        video,audio=f'jv{i}',f'ja{i}';elapsed+=s.duration-s.overlap
    return graph,video,audio


EFFECT_PRESETS={
    'clean':{},'warm':{'warmth':.3,'saturation':1.05},
    'cinema':{'contrast':1.1,'saturation':.9,'vignette':True},
    'vintage':{'warmth':.2,'saturation':.7,'contrast':.9},
    'black_white':{'grayscale':True},'soft':{'blur':.5},
    'punchy':{'contrast':1.15,'saturation':1.15},
}


def clip_filters(scene):
    filters=[]
    if scene.rotate==90:filters.append('transpose=1')
    elif scene.rotate==270:filters.append('transpose=2')
    elif scene.rotate==180:filters+=['hflip','vflip']
    if scene.flip_horizontal:filters.append('hflip')
    if scene.flip_vertical:filters.append('vflip')
    if scene.crop!='original':
        a,b=map(int,scene.crop.split(':'));ratio=a/b
        filters.append(f'crop=w=trunc(min(iw\\,ih*{ratio})/2)*2:h=trunc(min(ih\\,iw/{ratio})/2)*2')
    e=scene.effects
    if e.brightness or e.contrast!=1 or e.saturation!=1:
        filters.append(f'eq=brightness={e.brightness}:contrast={e.contrast}:saturation={e.saturation}')
    if e.warmth:filters.append(f'colorbalance=rs={e.warmth*.1}:bs={-e.warmth*.1}')
    if e.blur:filters.append(f'gblur=sigma={e.blur}')
    if e.sharpen:filters.append(f'unsharp=5:5:{e.sharpen}:5:5:0')
    if e.vignette:filters.append('vignette=PI/5')
    if e.grayscale:filters.append('hue=s=0')
    if e.sepia:filters.append('colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131')
    return filters


TEXT_PRESETS={
    'title':{'position':'center','font_size':64,'alignment':'center'},
    'subtitle':{'position':'center','font_size':36,'alignment':'center'},
    'lower_third':{'position':'bottom_left','font_size':32,'alignment':'left'},
    'caption':{'position':'bottom','font_size':38,'alignment':'center'},
    'credits':{'position':'bottom','font_size':30,'alignment':'center'},
}

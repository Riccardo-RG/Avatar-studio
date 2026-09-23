"""Local multi-scene production: immutable cast, voiceovers, formats and music."""
import array
import math
from pathlib import Path
import re
import wave
import media
import platform_store as store
import providers
import languages

def prepare(data,voices):
    presentation=data.get('presentation','character')
    if presentation not in ('character','visuals'):raise ValueError('Scegli un montaggio con personaggi oppure sole immagini e voce.')
    raw=data.get('scenes')
    if not isinstance(raw,list) or not 1<=len(raw)<=4:raise ValueError('Prepara da una a quattro scene.')
    if data.get('format','portrait') not in ('portrait','landscape','square'):raise ValueError('Formato non valido.')
    scenes=[]
    for scene in raw:
        if not isinstance(scene,dict):raise ValueError('Scena non valida.')
        script=store.text(scene.get('script',''),1200,True)
        config=languages.apply(store.render_settings(providers.settings(),scene.get('character_id')),scene)
        if scene.get('voice'):
            if scene['voice'] not in voices:raise ValueError('Voce non disponibile.')
            config['voice']=scene['voice']
        image=scene.get('image','')
        if presentation=='visuals' and not image:raise ValueError('Nel montaggio con sole immagini, ogni scena richiede un’immagine.')
        if image and not store.asset_file(image):raise ValueError('Immagine della scena non valida.')
        scenes.append({'script':script,'settings':config,'image':image})
    if sum(len(s['script']) for s in scenes)>2400:raise ValueError('Il progetto può contenere fino a 2400 caratteri in totale.')
    music=data.get('music','')
    if music not in ('','soft-original'):raise ValueError('Musica non disponibile.')
    config={**scenes[0]['settings'],'format':data.get('format','portrait'),'presentation':presentation}
    return {'scenes':scenes,'config':config,'title':store.text(data.get('title','Una storia, più voci'),80,True),'music':music,'presentation':presentation}

def synthesize(production,folder,progress,cancelled):
    chunks=[];captions=[];phonemes=[];scenes=[];duration=0
    for index,scene in enumerate(production['scenes']):
        if cancelled():raise ValueError('Produzione annullata.')
        part=folder/f'scene-{index+1:02d}';part.mkdir(exist_ok=True)
        timeline=media.synthesize(scene['script'],scene['settings'],part,lambda p,m:progress(2+int((index+p/100)*22/len(production['scenes'])),f'Scena {index+1}: {m}'))
        with wave.open(str(part/'voice.wav')) as audio:
            if (audio.getnchannels(),audio.getsampwidth(),audio.getframerate())!=(1,2,22050):raise ValueError('Formato audio inatteso.')
            chunks.append(audio.readframes(audio.getnframes()))
        for c in timeline['captions']:captions.append({**c,'start':c['start']+duration,'end':c['end']+duration})
        for p in timeline['phonemes']:phonemes.append({**p,'start':p['start']+duration,'end':p['end']+duration})
        scenes.append({**scene,'start':duration,'end':duration+timeline['duration']})
        duration+=timeline['duration']
    if duration>180:raise ValueError('Accorcia le scene: il limite è tre minuti.')
    raw=b''.join(chunks)
    with wave.open(str(folder/'voice.wav'),'wb') as dest:dest.setparams((1,2,22050,0,'NONE','not compressed'));dest.writeframes(raw)
    values=array.array('h',raw);envelope=[]
    for offset in range(0,len(values),735):
        block=values[offset:offset+735];envelope.append(round(min(1,math.sqrt(sum(x*x for x in block)/len(block))/32768*9),4))
    (folder/'captions.srt').write_text('\n\n'.join(f"{i+1}\n{media.srt_time(c['start'])} --> {media.srt_time(c['end'])}\n{c['text']}" for i,c in enumerate(captions))+'\n')
    return {'duration':duration,'captions':captions,'phonemes':phonemes,'envelope':envelope,'envelope_fps':30,'scenes':scenes,'voice_engine':'per-scene','caption_alignment':['per-scene'],'music':production['music'],'presentation':production.get('presentation','character')}

def music_file(identity):
    if identity!='soft-original':return None
    path=store.ROOT/'static/music/soft-original.wav'
    return path if path.is_file() else None

def create_original_music():
    """An original quiet pad, generated mathematically; no sampled recordings."""
    path=store.ROOT/'static/music/soft-original.wav'
    if path.exists():return path
    path.parent.mkdir(exist_ok=True,parents=True);rate=22050;seconds=8;samples=array.array('h')
    # Integer frequencies over eight seconds make the waveform loop continuously.
    for i in range(rate*seconds):
        t=i/rate;envelope=.7+.3*math.sin(math.pi*t/seconds)**2
        value=sum(math.sin(2*math.pi*f*t)/(j+2) for j,f in enumerate((130.875,164.875,196.0,261.625)))
        samples.append(int(4800*envelope*value))
    with wave.open(str(path),'wb') as out:out.setparams((1,2,rate,0,'NONE','not compressed'));out.writeframes(samples.tobytes())
    return path

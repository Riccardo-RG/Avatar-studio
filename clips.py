"""Local recordings and deterministic clips. No speech transcription or external calls."""
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import uuid
import media
import platform_store
import providers

ROOT=Path(__file__).resolve().parent
LOCK=threading.RLock()
MAX_BYTES=2_000_000_000

def number(value):
    try:value=float(value)
    except (TypeError,ValueError):raise ValueError('Tempo o posizione non validi.') from None
    if not math.isfinite(value):raise ValueError('Tempo o posizione non validi.')
    return value

def probe(path):
    r=subprocess.run([media.ffmpeg_path(),'-hide_banner','-protocol_whitelist','file,pipe','-format_whitelist','mov,matroska,webm','-i',str(path)],capture_output=True,text=True,timeout=45)
    duration=re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)',r.stderr)
    video=re.search(r'Video: ([^, ]+).*?, (\d{2,5})x(\d{2,5})(?:[ ,])',r.stderr)
    if not video:raise ValueError('Registrazione non leggibile: usa un video MP4, MOV, MKV o WebM valido.')
    if duration:seconds=sum(float(v)*m for v,m in zip(duration.groups(),(3600,60,1)))
    else:
        # MediaRecorder WebM commonly has no duration header. Scan packet timestamps without decoding.
        scan=subprocess.run([media.ffmpeg_path(),'-v','error','-nostdin','-protocol_whitelist','file,pipe','-format_whitelist','mov,matroska,webm','-i',str(path),'-map','0:v:0','-c','copy','-progress','pipe:1','-f','null','-'],capture_output=True,text=True,timeout=90)
        times=re.findall(r'out_time_us=(\d+)',scan.stdout)
        if scan.returncode or not times:raise ValueError('Durata della registrazione non disponibile.')
        seconds=int(times[-1])/1_000_000
    if int(video[2])*int(video[3])>20_000_000:raise ValueError('Risoluzione della sorgente troppo grande: massimo 20 megapixel per fotogramma.')
    if not 1<=seconds<=8*3600:raise ValueError('Sono supportate registrazioni da un secondo a otto ore.')
    return {'duration':seconds,'width':int(video[2]),'height':int(video[3]),'codec':video[1],'audio':bool(re.search(r'Stream .*Audio:',r.stderr))}

def recording_path(identity,name='source.mp4'):
    if not re.fullmatch(r'[a-f0-9]{12}',identity):raise ValueError('Registrazione non valida.')
    return ROOT/'data/recordings'/identity/name

def import_stream(stream,size,filename):
    if not 0<size<=MAX_BYTES:raise ValueError('Importa un video fino a 2 GB.')
    name=Path(filename).name
    if Path(name).suffix.lower() not in ('.mp4','.mov','.mkv','.webm'):raise ValueError('Usa MP4, MOV, MKV o WebM.')
    identity=uuid.uuid4().hex[:12];folder=recording_path(identity).parent;folder.mkdir(parents=True)
    target=folder/('source'+Path(name).suffix.lower());digest=hashlib.sha256();remaining=size
    try:
        with target.open('wb') as out:
            while remaining:
                chunk=stream.read(min(1024*1024,remaining))
                if not chunk:raise ValueError('Importazione interrotta: riprova con il file completo.')
                remaining-=len(chunk);out.write(chunk);digest.update(chunk)
        details=probe(target)
        item={'id':identity,'title':name[:100],'created':time.time(),'bytes':size,'sha256':digest.hexdigest(),'file':target.name,**details,'captions':[]}
        providers.atomic_json(folder/'recording.json',item)
        return public_recording(item)
    except Exception:
        shutil.rmtree(folder);raise

def public_recording(item):
    return {**{k:v for k,v in item.items() if k!='captions'},'source_id':'recording:'+item['id'],
            'url':'/recordings/'+item['id']+'/'+item.get('file','source.mp4'),'subtitle_count':len(item.get('captions',[]))}

def catalog():
    result=[]
    for f in (ROOT/'data/recordings').glob('*/recording.json'):
        result.append(public_recording(json.loads(f.read_text())))
    for f in (ROOT/'output').glob('*/status.json'):
        job=json.loads(f.read_text());project=f.parent/'project.json'
        if job.get('state')!='done' or not project.exists():continue
        p=json.loads(project.read_text());result.append({'id':job['id'],'source_id':'job:'+job['id'],'title':job['title'],
            'duration':p['duration'],'url':f'/output/{job["id"]}/video.mp4','created':job['created'],'subtitle_count':len(p.get('captions',[]))})
    return sorted(result,key=lambda x:x['created'],reverse=True)

def source(identity):
    if not isinstance(identity,str) or not re.fullmatch(r'(job|recording):[a-f0-9]{12}',identity):raise ValueError('Scegli una sorgente locale.')
    kind,key=identity.split(':')
    if kind=='recording':
        metadata=recording_path(key,'recording.json')
        if not metadata.exists():raise ValueError('Registrazione non trovata.')
        item=json.loads(metadata.read_text());filename=item.get('file','source.mp4')
        if filename not in ('source.mp4','source.mov','source.mkv','source.webm'):raise ValueError('File sorgente non valido.')
        return metadata.parent/filename,item,{}
    folder=ROOT/'output'/key
    if not (folder/'status.json').exists() or not (folder/'project.json').exists():raise ValueError('Video sorgente non trovato.')
    state=json.loads((folder/'status.json').read_text())
    if state['state']!='done':raise ValueError('La sorgente deve essere completata.')
    project=json.loads((folder/'project.json').read_text())
    return folder/'video.mp4',{'duration':project['duration'],'captions':project.get('captions',[])},project

def parse_srt(text,duration):
    if not isinstance(text,str) or len(text)>1_000_000:raise ValueError('Sottotitoli troppo grandi.')
    rows=[]
    for block in re.split(r'\n\s*\n',text.lstrip('\ufeff').replace('\r\n','\n').strip()):
        lines=block.splitlines()
        if lines and lines[0].strip().isdigit():lines=lines[1:]
        if not lines:continue
        match=re.fullmatch(r'(\d{2,3}):(\d{2}):(\d{2})[,.](\d{3})\s+-->\s+(\d{2,3}):(\d{2}):(\d{2})[,.](\d{3})',lines[0].strip())
        if not match or len(lines)<2:raise ValueError('SRT non valido: usa tempi completi e un testo per segmento.')
        values=list(map(int,match.groups()))
        if any(values[i]>=60 for i in (1,2,5,6)):raise ValueError('Tempi SRT non validi.')
        start=values[0]*3600+values[1]*60+values[2]+values[3]/1000;end=values[4]*3600+values[5]*60+values[6]+values[7]/1000
        if not 0<=start<end<=duration+.1:raise ValueError('Un sottotitolo supera la durata della registrazione.')
        content=re.sub(r'<[^>]*>','',' '.join(lines[1:])).strip()
        if not content or len(content)>500:raise ValueError('Segmento SRT vuoto o troppo lungo.')
        rows.append({'start':start,'end':min(end,duration),'text':content})
    if not rows or len(rows)>10000:raise ValueError('SRT vuoto o con troppi segmenti.')
    return sorted(rows,key=lambda c:c['start'])

def subtitles(data):
    path=recording_path(data.get('id',''),'recording.json')
    with LOCK:
        item=json.loads(path.read_text());item['captions']=parse_srt(data.get('text'),item['duration']);providers.atomic_json(path,item)
    return public_recording(item)

def trim_captions(captions,start,end):
    return [{**c,'start':round(max(start,c['start'])-start,3),'end':round(min(end,c['end'])-start,3)}
            for c in captions if c['end']>start and c['start']<end]

def prepare(data):
    path,info,project=source(data.get('source_id'));start=number(data.get('start'));end=number(data.get('end'));position=number(data.get('position',.5))
    if not 0<=start<end<=info['duration']+.02 or not 1<=end-start<=180:raise ValueError('Scegli un intervallo da 1 a 180 secondi dentro la registrazione.')
    if not 0<=position<=1:raise ValueError('Posizione del ritaglio non valida.')
    fmt=data.get('format','portrait');fit=data.get('fit','contain')
    if fmt not in ('portrait','square','landscape') or fit not in ('contain','cover'):raise ValueError('Formato o inquadratura non validi.')
    title=str(data.get('title','')).strip()
    if not 1<=len(title)<=80:raise ValueError('Dai alla clip un titolo fino a 80 caratteri.')
    ids=data.get('character_ids',[])
    if not isinstance(ids,list) or len(ids)>8:raise ValueError('Personaggi non validi.')
    for identity in ids:platform_store.snapshot(identity)
    scenes=trim_captions(project.get('scenes',[]),start,end)
    if project:
        ids=sorted({scene.get('settings',{}).get('character',{}).get('id') for scene in scenes} - {None}) if project.get('scenes') else project.get('character_ids') or ([project['settings']['character']['id']] if project.get('settings',{}).get('character') else [])
    burned=bool(project.get('captions_burned', bool(project.get('captions')))) if project else data.get('source_captions_burned') is True
    burn=data.get('burn_captions', True) is True and not burned and bool(info.get('captions'))
    config=copy.deepcopy(project.get('settings') or providers.settings());config.update(format=fmt,name=project.get('settings',{}).get('name','Registrazione'))
    if scenes:config={**config,**scenes[0]['settings'],'format':fmt}
    if not project:config.pop('character',None)
    if project.get('scenes') and not scenes:config.pop('character',None)
    return {'source_id':data['source_id'],'start':start,'end':end,'position':position,'format':fmt,'fit':fit,'title':title,'character_ids':ids,
            'config':config,'source_bytes':path.stat().st_size,'source_mtime_ns':path.stat().st_mtime_ns,'captions':trim_captions(info.get('captions',[]),start,end),'source_project':project,'scenes':scenes,'captions_burned':burned,'burn_captions':burn}

def suggest(data):
    _,info,_=source(data.get('source_id'));seconds=number(data.get('seconds',30))
    if not 5<=seconds<=90:raise ValueError('Scegli una durata da 5 a 90 secondi.')
    result=[];last=-1
    for c in info.get('captions',[]):
        start=c['start']
        if start<last or info['duration']-start<3:continue
        end=min(start+seconds,info['duration']);result.append({'start':round(start,2),'end':round(end,2),'label':c['text'][:100]});last=end
        if len(result)==8:break
    if not result:
        result=[{'start':round(i*info['duration']/min(4,max(1,int(info['duration']//seconds))),2),'end':round(min(info['duration'],i*info['duration']/min(4,max(1,int(info['duration']//seconds)))+seconds),2),'label':'Intervallo da rivedere'} for i in range(min(4,max(1,int(info['duration']//seconds))))]
    return {'items':result,'method':'Inizi dei sottotitoli e durata' if info.get('captions') else 'Intervalli distribuiti sulla registrazione','note':'Proposte temporali, non una valutazione AI dei momenti migliori. Rivedi tagli e significato prima di produrre.'}

def filters(clip):
    w,h={'portrait':(720,1280),'square':(720,720),'landscape':(1280,720)}[clip['format']]
    if clip['fit']=='contain':return f'scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x101710,setsar=1'
    return f'scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}:(iw-ow)*{clip["position"]:.6f}:(ih-oh)/2,setsar=1'

def render(clip,folder,cancelled,progress,set_process):
    path,_,_=source(clip['source_id'])
    if path.stat().st_size!=clip['source_bytes'] or path.stat().st_mtime_ns!=clip['source_mtime_ns']:raise ValueError('La sorgente è cambiata: prepara nuovamente la clip.')
    if cancelled():raise ValueError('Produzione annullata.')
    length=clip['end']-clip['start'];project={'version':3,'title':clip['title'],'settings':clip['config'],'duration':length,'captions':clip['captions'],
        'script':' '.join(c['text'] for c in clip['captions']),'source_reference':{k:clip[k] for k in ('source_id','start','end','fit','position')},'captions_burned':clip['captions_burned'] or clip['burn_captions'],'clip':True,'character_ids':clip['character_ids']}
    if clip['scenes']:project['scenes']=clip['scenes']
    write_srt(folder,clip['captions'])
    info=probe(path)
    audio_input=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo'] if not info['audio'] else []
    vf=filters(clip)
    if clip['burn_captions']:
        font={'portrait':9,'square':14,'landscape':15}[clip['format']]
        vf+=f",subtitles=filename=captions.srt:force_style='Fontname=Arial,Fontsize={font},Outline=1,Shadow=0,BorderStyle=3,OutlineColour=&H80000000,BackColour=&H80000000,MarginV=46'"
    args=[media.ffmpeg_path(),'-hide_banner','-nostdin','-y','-protocol_whitelist','file,pipe','-ss',str(clip['start']),'-i',str(path),*audio_input,'-t',str(length),'-map','0:v:0','-map','0:a:0' if info['audio'] else '1:a:0',
          '-vf',vf,'-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-r','24','-c:a','aac','-ar','48000','-ac','2','-movflags','+faststart','-progress','pipe:1',str(folder/'video.mp4')]
    with (folder/'clip-render.log').open('w') as log:
        proc=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=log,text=True,cwd=folder);set_process(proc)
        try:
            for line in proc.stdout:
                if cancelled():proc.terminate();raise ValueError('Produzione annullata.')
                if re.fullmatch(r'out_time_us=\d+\s*',line):
                    progress(5+int(min(1,number(line.strip().split('=')[1])/1_000_000/length)*85),'Esportazione della clip sul Mac')
            if proc.wait()!=0:raise ValueError('Esportazione della clip non riuscita. Controlla clip-render.log.')
        finally:
            proc.stdout.close()
            if proc.poll() is None:
                proc.terminate()
                try:proc.wait(timeout=5)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
    if cancelled():raise ValueError('Produzione annullata.')
    for name in ('poster.png','cover.png'):
        result=subprocess.run([media.ffmpeg_path(),'-v','error','-y','-i',str(folder/'video.mp4'),'-frames:v','1',str(folder/name)],capture_output=True,timeout=40)
        if result.returncode:raise ValueError('Anteprima della clip non riuscita.')
    providers.atomic_json(folder/'project.json',project)
    return project


def write_srt(folder,captions):
    (folder/'captions.srt').write_text('\n\n'.join(f'{i+1}\n{media.srt_time(c["start"])} --> {media.srt_time(c["end"])}\n{c["text"]}' for i,c in enumerate(captions))+'\n')

def details(identity):
    path,info,project=source(identity)
    return {'source_id':identity,'duration':info['duration'],'captions':info.get('captions',[]),
            'captions_burned':bool(project.get('captions_burned',bool(project.get('captions')))),
            'character_ids':project.get('character_ids') or sorted({c['settings']['character']['id'] for c in project.get('scenes',[]) if c.get('settings',{}).get('character')} or ({project['settings']['character']['id']} if project.get('settings',{}).get('character') else set()))}

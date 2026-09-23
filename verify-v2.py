"""Decode every frame of the ten current starter episodes and validate local packages."""
import array
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import zipfile

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'deps'))
import imageio_ffmpeg
from PIL import Image,ImageDraw

report=[];jobs=[]
reuse='--changed' in sys.argv
old_report=json.loads((ROOT/'output/verification-v2.json').read_text()) if reuse else []
previous={r['id']:r for r in old_report}
sheet=Image.open(ROOT/'output/qa-contact-sheet-v2.jpg').copy() if reuse else Image.new('RGB',(1080,10*410),'#111811')
draw=ImageDraw.Draw(sheet)
for row in range(10):
    episode_id=f's01e{row+1:02}'
    deadline=time.time()+1500
    while True:
        doc=json.loads((ROOT/'data/studio.json').read_text())
        episode=next(e for e in doc['episodes'] if e['id']==episode_id)
        if episode['status']=='ready':break
        if episode['status'] not in ('rendering','approved') or time.time()>deadline:
            raise RuntimeError(f"Production not completed: {episode_id} {episode['status']}")
        time.sleep(5)
    folder=ROOT/'output'/episode['job_id']
    job=json.loads((folder/'status.json').read_text());jobs.append(job)
    if job['id'] in previous:
        report.append(previous[job['id']]);continue
    project=json.loads((folder/'project.json').read_text())
    assert job['state']=='done'
    assert project['episode']['revision']==episode['revision']
    assert project['voice_engine']=='piper'
    assert project['settings']['monthly_budget_usd']==0
    assert project['script']==episode['script']
    reader=imageio_ffmpeg.read_frames(str(folder/'video.mp4'));meta=next(reader)
    assert meta['size']==(720,1280),meta
    assert meta['codec']=='h264' and meta['fps']==24
    duration=meta['duration'];assert abs(duration-project['duration'])<.2
    targets=[round(t*24) for t in [.65,duration*.5,max(.65,duration-.8)]]
    chosen={};count=0
    for index,frame in enumerate(reader):
        count+=1
        if index in targets:chosen[index]=Image.frombytes('RGB',meta['size'],frame)
    assert count>=(duration-.2)*24 and len(chosen)==3
    assert chosen[targets[0]].tobytes()!=chosen[targets[-1]].tobytes()
    raw=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-i',str(folder/'video.mp4'),'-vn','-f','s16le','-acodec','pcm_s16le','-ac','1','-ar','22050','pipe:1'],capture_output=True,check=True).stdout
    samples=array.array('h',raw);rms=math.sqrt(sum(x*x for x in samples)/len(samples))/32768
    assert rms>.005 and abs(len(samples)/22050-duration)<.2
    assert max(abs(x) for x in samples)<32768
    captions=project['captions'];phonemes=project['phonemes']
    for timeline in [captions,phonemes]:
        assert timeline and all(0<=c['start']<c['end']<=duration+.1 for c in timeline)
        assert all(a['end']<=b['start']+.00001 for a,b in zip(timeline,timeline[1:]))
    assert len(set(p['shape'] for p in phonemes))>=4
    assert ' '.join(c['text'] for c in captions)==' '.join(project['script'].split())
    descriptions=set();media_digest=hashlib.sha256((folder/'video.mp4').read_bytes()).hexdigest()
    for platform in ['youtube','tiktok','instagram']:
        with zipfile.ZipFile(folder/f'{platform}.zip') as z:
            assert z.testzip() is None
            assert {'video.mp4','cover.png','captions.srt','script.txt','post.txt','metadata.json','LEGGIMI.txt'}<=set(z.namelist())
            assert hashlib.sha256(z.read('video.mp4')).hexdigest()==media_digest
            assert z.read('cover.png')==(folder/'cover.png').read_bytes()
            info=json.loads(z.read('metadata.json'));descriptions.add(info['description'])
            assert 'Voce sintetica' in info['description']
    assert len(descriptions)==3
    cover=Image.open(folder/'cover.png');assert cover.size==(720,1280)
    draw.text((15,row*410+8),f'{row+1:02}. {job["title"]}',fill='#d4f7ba')
    for col,img in enumerate([cover]+[chosen[t] for t in targets]):sheet.paste(img.resize((198,352)),(col*270+14,row*410+32))
    item={'id':job['id'],'episode_id':episode_id,'title':job['title'],'duration':duration,'frames':count,'resolution':list(meta['size']),'audio_rms':round(rms,4),'captions':len(captions),'phonemes':len(phonemes),'alignment':project['caption_alignment'],'decoded_all_frames':True,'three_packages_verified':True}
    report.append(item);print(json.dumps(item,ensure_ascii=False),flush=True)
    (ROOT/'output/verification-v2.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
assert len(report)==10
(ROOT/'output/verification-v2.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
sheet.save(ROOT/'output/qa-contact-sheet-v2.jpg',quality=92)
(ROOT/'output/acceptance-v2.json').write_text(json.dumps(jobs,ensure_ascii=False,indent=2))
print('Ten episodes verified; contact sheet saved.',flush=True)

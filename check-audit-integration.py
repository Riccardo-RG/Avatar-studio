"""Relocated application smoke test with copied data and no external credentials."""
import hashlib
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import media

ROOT=Path(__file__).resolve().parent


def main():
    report={}
    original_data={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'data').rglob('*') if p.is_file()}
    with tempfile.TemporaryDirectory(prefix='avatar audit ') as tmp:
        target=Path(tmp)
        for p in ROOT.iterdir():
            if p.is_file() and (p.suffix in ('.py','.cjs','.js','.md') or p.name=='policy_catalog.json'):shutil.copy2(p,target/p.name)
        for name in ('static','models','deps','voice-deps','runtime','node_modules'):
            if (ROOT/name).exists():(target/name).symlink_to(ROOT/name,target_is_directory=True)
        (target/'data').mkdir();(target/'output').mkdir()
        for p in (ROOT/'data').glob('*.json'):shutil.copy2(p,target/'data'/p.name)
        if (ROOT/'data/character-assets').exists():shutil.copytree(ROOT/'data/character-assets',target/'data/character-assets')
        env={k:v for k,v in os.environ.items() if not k.startswith(('AVATAR_YOUTUBE_','AVATAR_INSTAGRAM_','AVATAR_TIKTOK_','AVATAR_TAVUS_','AVATAR_R2_','AVATAR_OBS_')) and k not in ('OPENAI_API_KEY','HEYGEN_API_KEY','BRAVE_SEARCH_API_KEY')}
        log=(target/'server.log').open('w')
        proc=subprocess.Popen([sys.executable,'app.py','--port','0'],cwd=target,env=env,stdout=log,stderr=log,start_new_session=True)
        try:
            end=time.monotonic()+35;base=''
            while time.monotonic()<end:
                content=(target/'server.log').read_text()
                for line in content.splitlines():
                    if line.startswith('Avatar Studio pronto: '):base=line.split(': ',1)[1]
                if base:break
                if proc.poll() is not None:raise RuntimeError(content[-2000:])
                time.sleep(.1)
            assert base,'Server non pronto entro 35 secondi'
            def req(path,data=None,token=None):
                headers={'Content-Type':'application/json'}
                if token:headers['X-Avatar-Token']=token
                request=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),headers=headers)
                with urllib.request.urlopen(request,timeout=390) as response:return json.load(response)
            bootstrap=req('/api/bootstrap');token=bootstrap['token']
            assert not bootstrap['has_openai_key']
            assert not req('/api/publications')['armed']
            assert not req('/api/insights')['enabled']
            assert all(not s['connected'] for s in req('/api/connections').values())
            import runtime_config
            browser_env={**env,'AVATAR_TEST_URL':base,'AVATAR_ISOLATED_TEST':'1'}
            subprocess.run([runtime_config.node(),'check-business-ui.cjs'],cwd=target,env=browser_env,check=True,timeout=100)
            shutil.copy2(target/'output/business-ui-verification.json',ROOT/'output/business-ui-verification.json')
            try:req('/api/render',{'script':'Unauthorized'})
            except urllib.error.HTTPError as exc:assert exc.code==403
            else:raise AssertionError('POST privo di token accettato')
            try:req('/api/youtube-analytics',{})
            except urllib.error.HTTPError as exc:assert exc.code==403
            else:raise AssertionError('Analytics privo di token accettato')
            before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (target/'data').glob('*.json')}
            second=subprocess.run([sys.executable,'app.py','--port',base.rsplit(':',1)[1]],cwd=target,env=env,capture_output=True,text=True,timeout=8)
            assert second.returncode!=0 and 'porta già occupata' in second.stderr
            after={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (target/'data').glob('*.json')}
            assert before==after,'Il secondo avvio ha modificato dati'
            script_started=time.monotonic()
            draft=req('/api/script',{'topic':'Come organizzare i file sul proprio computer','seconds':15,'language':'it','character_id':'lumo'},token)
            assert draft['provider']=='local' and draft['reserved_usd']==0 and len(draft['script'])>30,draft
            report['native_script']={'seconds':round(time.monotonic()-script_started,2),'script':draft['script']}
            print('Copione nativo verificato.',flush=True)
            voice=next(v['id'] for v in bootstrap['voice_catalog'] if v['language']=='it' and not v['id'].startswith('piper:'))
            job=req('/api/render',{'script':'Ciao! Questa è una prova di funzionamento.','title':'Verifica isolata prima del collaudo','character_id':'lumo','language':'it','voice':voice},token)
            deadline=time.monotonic()+150
            while time.monotonic()<deadline:
                current=req('/api/jobs/'+job['id'])
                if current['state'] in ('done','error','cancelled'):break
                time.sleep(.25)
            assert current['state']=='done',current
            folder=target/'output'/job['id'];project=json.loads((folder/'project.json').read_text())
            assert project['settings']['character']['id']=='lumo' and project['settings']['language']=='it'
            result=subprocess.run([media.ffmpeg_path(),'-v','error','-i',str(folder/'video.mp4'),'-map','0:v:0','-map','0:a:0','-f','null','-'],capture_output=True,text=True,timeout=30)
            assert result.returncode==0,result.stderr
            assert (folder/'captions.srt').stat().st_size>0
            shutil.copy2(folder/'poster.png',ROOT/'output/audit-render-poster.png')
            samples=ROOT/'output/local-verification';samples.mkdir(exist_ok=True)
            shutil.copy2(folder/'video.mp4',samples/'lumo.mp4')
            report.update({'relocated_path_with_spaces':True,'data_isolated':True,'credentials_removed':True,'publishing_disarmed':True,'metrics_disabled':True,'post_without_token_rejected':True,'duplicate_launch_rejected_without_data_changes':True,'real_local_mp4':True,'video_audio_fully_decoded':True,'character':'lumo','language':'it','voice':voice,'duration':project['duration'],'bytes':(folder/'video.mp4').stat().st_size,'sha256':hashlib.sha256((folder/'video.mp4').read_bytes()).hexdigest()})
            # Real Piper + image-only production; use existing portable art in the isolated copy.
            image='/character-assets/'+next((target/'data/character-assets').glob('*.png')).name
            visual=req('/api/production',{'title':'Immagini e voce · verifica locale','presentation':'visuals','format':'landscape','scenes':[{'script':'Una scena illustrata, una voce locale e i sottotitoli.','character_id':'lumo','language':'it','voice':'piper:paola','image':image}]},token)
            deadline=time.monotonic()+150
            while time.monotonic()<deadline:
                current=req('/api/jobs/'+visual['id'])
                if current['state'] in ('done','error','cancelled'):break
                time.sleep(.25)
            assert current['state']=='done',current
            visual_folder=target/'output'/visual['id'];visual_project=json.loads((visual_folder/'project.json').read_text())
            assert visual_project['presentation']=='visuals' and visual_project['captions']
            decoded=subprocess.run([media.ffmpeg_path(),'-v','error','-i',str(visual_folder/'video.mp4'),'-map','0:v:0','-map','0:a:0','-f','null','-'],capture_output=True,text=True,timeout=30)
            assert decoded.returncode==0,decoded.stderr
            for source,dest in [('video.mp4','immagini-e-voce.mp4'),('poster.png','immagini-e-voce.png'),('captions.srt','immagini-e-voce.srt')]:shutil.copy2(visual_folder/source,samples/dest)
            report['image_only_piper_mp4']={'duration':visual_project['duration'],'video_audio_fully_decoded':True,'subtitles':True}
            print('Rendering avatar, immagini, voce Piper e sottotitoli verificati.',flush=True)
            # Simulated published posts remain inside this temporary directory.
            post=req('/api/publication-save',{'job_id':job['id'],'platform':'youtube','title':'Post di prova A','visibility':'private','due_at':dt.datetime.fromtimestamp(time.time()+3600,dt.timezone.utc).isoformat()},token)
            posts=[]
            for identity,title in [('a'*12,'Post di prova A'),('b'*12,'Post di prova B')]:
                posts.append({**post,'id':identity,'title':title,'state':'published','actual_visibility':'public','published_at':time.time()-25*3600,'published_at_source':'remote_verified','account_id':'channel-test','remote_id':'video-'+identity,'metrics':[]})
            (target/'data/publications.json').write_text(json.dumps({'items':posts,'events':[]}))
            for script_name in ('check-analytics-ui.cjs','check-growth-flows.cjs','check-project-workflow.cjs'):
                subprocess.run([runtime_config.node(),script_name],cwd=target,env=browser_env,check=True,timeout=240)
                name=script_name.replace('check-','').replace('.cjs','-verification.json')
                shutil.copy2(target/'output'/name,ROOT/'output'/name)
            shutil.copy2(target/'output/analytics-mobile-verification.png',ROOT/'output/analytics-mobile-verification.png')
            for name in ('project-workflow-mobile.png', 'project-workflow-guide-mobile.png'):
                shutil.copy2(target/'output'/name, ROOT/'output'/name)
        finally:
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)
                try:proc.wait(timeout=15)
                except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
            log.close()
    assert original_data=={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'data').rglob('*') if p.is_file()},'I dati originali sono cambiati durante il test'
    report['original_data_hashes_unchanged']=True
    (ROOT/'output/audit-integration-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

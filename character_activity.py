"""Compact character references. Original media and scripts stay in their own files."""
import json
from pathlib import Path
import threading
import time
import uuid
from urllib.parse import urlparse
import providers

LOCK=threading.RLock()

def read(path,default):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return default

def character_ids(settings):
    c=settings.get('character',{})
    if c.get('id'):return {c['id']}
    # The shipped editions 1/2 had only NOVA, before profiles had stable IDs.
    return {'nova'} if str(settings.get('name','')).casefold()=='nova' else set()

class Activity:
    def __init__(self,root):self.root=Path(root);self.path=self.root/'data/activity.json'
    def load(self):return read(self.path,{'live':[],'references':[]})
    def recover(self):
        with LOCK:
            doc=self.load()
            for s in doc['live']:
                if s['state']=='active':s.update(state='interrupted',ended=None)
            providers.atomic_json(self.path,doc)
    def start(self,title,settings):
        c=settings.get('character',{})
        entry={'id':uuid.uuid4().hex[:12],'title':title,'character_id':c.get('id'),'character_name':c.get('name'),
               'revision':c.get('revision'),'at':time.time(),'state':'active','kind':'live','platform':'regia locale','url':'#live'}
        with LOCK:
            doc=self.load();doc['live'].append(entry);providers.atomic_json(self.path,doc)
        return entry['id']
    def end(self,identity,state,duration):
        if not identity:return
        with LOCK:
            doc=self.load();entry=next((s for s in doc['live'] if s['id']==identity),None)
            if entry:entry.update(state=state,ended=time.time(),duration=round(duration,2));providers.atomic_json(self.path,doc)
    def add(self,data):
        character=data.get('character_id');profiles=read(self.root/'data/platform.json',{}).get('characters',[])
        if character not in {c['id'] for c in profiles}:raise ValueError('Scegli un personaggio salvato.')
        title=str(data.get('title','')).strip();url=str(data.get('url','')).strip();platform=data.get('platform')
        if not title or len(title)>100 or len(url)>2000:raise ValueError('Inserisci un titolo breve e un riferimento.')
        hosts={'youtube':{'youtube.com','www.youtube.com','youtu.be'},'tiktok':{'www.tiktok.com','tiktok.com'},'instagram':{'instagram.com','www.instagram.com'},'twitch':{'twitch.tv','www.twitch.tv'}}
        u=urlparse(url)
        if platform not in hosts or u.scheme!='https' or u.hostname not in hosts[platform] or u.username or u.password or u.port not in (None,443):raise ValueError('Usa il link HTTPS del contenuto sulla piattaforma scelta.')
        entry={'id':uuid.uuid4().hex[:12],'kind':'reference','title':title,'character_id':character,'platform':platform,'url':url,'state':'manual','at':time.time()}
        with LOCK:
            doc=self.load()
            if any(r['url']==url and r['character_id']==character for r in doc['references']):raise ValueError('Riferimento già presente.')
            doc['references'].append(entry);providers.atomic_json(self.path,doc)
        return entry
    def remove(self,identity):
        with LOCK:
            doc=self.load();doc['references']=[r for r in doc['references'] if r['id']!=identity];providers.atomic_json(self.path,doc)
        return {'removed':True}
    def snapshot(self,identity):
        rows=[];jobs=set()
        for folder in (self.root/'output').glob('*'):
            if not folder.is_dir() or len(folder.name)!=12:continue
            status=read(folder/'status.json',{});project=read(folder/'project.json',{})
            cast=set(status.get('character_ids',[]))|character_ids(project.get('settings',{}))
            for scene in project.get('scenes',[]):cast|=character_ids(scene.get('settings',{}))
            if identity not in cast:continue
            jobs.add(folder.name)
            rows.append({'id':folder.name,'kind':'video','title':status.get('title',project.get('title','Video')),'state':status.get('state','unknown'),
                         'at':status.get('created',folder.stat().st_mtime),'platform':'Mac','url':f'/output/{folder.name}/video.mp4' if status.get('state')=='done' else '#create'})
        for p in read(self.root/'data/publications.json',{'items':[]})['items']:
            if p['job_id'] in jobs:
                rows.append({'id':p['id'],'kind':'publication','title':p['title'],'state':p['state'],'platform':p['platform'],
                             'at':p.get('published_at',p.get('attempted_at',p['created'])),'url':p.get('url') or '#publishing' if p['state']=='published' else '#publishing','job_id':p['job_id'],'remote_id':p.get('remote_id','')})
        doc=self.load();rows.extend(r for r in doc['live']+doc['references'] if r.get('character_id')==identity)
        for session in read(self.root/'data/broadcast.json',{'sessions':[]})['sessions']:
            if session.get('character_id')==identity:
                rows.append({'id':session['id'],'kind':'conversation','title':'Conversazione · '+session.get('character_name',identity),
                    'state':session['state'],'platform':'Tavus','at':session['created'],'url':'#live'})
        for c in read(self.root/'data/platform.json',{}).get('campaigns',[]):
            if c.get('character_id')==identity:rows.append({'id':c['id'],'kind':'campaign','title':c['name'],'state':'brief','platform':'Studio','at':c.get('updated',c.get('created',0)),'url':'#campaigns'})
        return {'character_id':identity,'items':sorted(rows,key=lambda r:r['at'],reverse=True),'note':'Riferimenti locali e stati dei servizi. Le dirette locali non confermano una trasmissione; i link aggiunti a mano sono dichiarati dall’utente.'}

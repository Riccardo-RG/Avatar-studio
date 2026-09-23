"""Local live director. Playback is leased to one scene; no publishing code here."""
import languages
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import threading
import time
import unicodedata
import uuid

import media
import providers
import platform_store
import studio
from character_activity import Activity
from live_catalog import DEFAULTS


def clean(value, limit, minimum=1):
    if not isinstance(value,str):raise ValueError('Testo non valido.')
    value=unicodedata.normalize('NFKC',value).strip()
    if not minimum<=len(value)<=limit or any(ord(c)<32 and c not in '\n\t' for c in value):
        raise ValueError(f'Usa da {minimum} a {limit} caratteri, senza caratteri di controllo.')
    return value


def classify(text, replies):
    normalized=unicodedata.normalize('NFKC',text).casefold()
    if re.search(r'https?://|www\.|\b\S+@\S+\.\S+|\d[\d ()+-]{7,}\d|\[\[|<[^>]+>|ignora|ignore|system|prompt|password|token|api.?key|esegui|sudo|suicid|ammazz|uccid|nazist|porn|farmac|diagnos|investiment|vaffanc|cazz|merda',normalized):
        return None,'Da rivedere: link, dati personali o tema non previsto.'
    for reply in replies:
        if any(re.search(r'(?<!\w)'+re.escape(t.casefold())+r'(?!\w)',normalized) for t in reply['triggers']):
            return reply,None
    return None,'Domanda nuova: prepara una risposta e rileggila.'


class LiveDirector:
    def __init__(self, root, clock=time.monotonic, start_thread=True):
        self.root=Path(root);self.path=self.root/'data/live.json';self.assets=self.root/'output/live'
        self.assets.mkdir(parents=True,exist_ok=True);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.clock=clock;self.executor=ThreadPoolExecutor(max_workers=1)
        self.config=copy.deepcopy(DEFAULTS)
        self.session_settings=None
        self.activity=Activity(self.root);self.activity.recover();self.session_id=None
        if self.path.exists():self.config.update(json.loads(self.path.read_text()))
        if not self.config.get('character_id'):
            self.config['character_id'] = platform_store.snapshot()['id']
            providers.atomic_json(self.path,self.config)
        self.phase='idle';self.queue=[];self.current=None;self.history=[];self.messages=[];self.error=''
        self.epoch=0;self.lease=None;self.lease_seen=0;self.scene_status='Assente';self.position=0
        self.started=None;self.elapsed=0;self.last_tick=clock();self.next_at=0;self.cursor=0;self.playlist=[]
        self.seen={};self.users={};self.reply_times={};self.running=True
        self.thread=None
        if start_thread:
            self.thread=threading.Thread(target=self._loop,daemon=True,name='avatar-live');self.thread.start()

    def _loop(self):
        while self.running:
            try:self.tick()
            except Exception:
                with self.lock:self.phase='paused';self.error='La regia si è fermata. Controlla scaletta e audio prima di riprendere.'
            time.sleep(.2)

    def close(self):
        self.activity.end(self.session_id,'interrupted',self.elapsed);self.session_id=None
        self.running=False;self.executor.shutdown(wait=False,cancel_futures=True)

    def catalog(self):
        doc=studio.load();result=[]
        for e in doc['episodes']:
            if e['status']!='ready' or not e.get('job_id'):continue
            file=self.root/'output'/e['job_id']/'project.json'
            if not file.exists():continue
            project=json.loads(file.read_text())
            result.append({'id':e['id'],'title':e['title'],'job_id':e['job_id'],
                'script':e['script'],'duration':project['duration'],'rubric':project.get('rubric',{}),
                'project':project})
        return result

    def save_config(self,data):
        with self.lock:
            updated=copy.deepcopy(self.config)
            if 'character_id' in data:
                if self.phase in ('running','paused') and data['character_id']!=self.config.get('character_id'):raise ValueError('Ferma la diretta prima di cambiare personaggio.')
                if self.queue and data['character_id']!=self.config.get('character_id'):raise ValueError('Premi Stop per svuotare gli interventi preparati prima di cambiare personaggio.')
                platform_store.snapshot(data['character_id'])
                updated['character_id']=data['character_id']
            if 'language' in data:
                language=languages.code(data['language'])
                if language!=self.config.get('language','it'):
                    if self.phase in ('running','paused') or self.queue:raise ValueError('Ferma la regia prima di cambiare lingua.')
                    updated['language']=language;updated['auto_replies']=False
            for k,n in [('title',80),('tagline',140)]:
                if k in data:updated[k]=clean(data[k],n)
            for k in ['autopilot','loop','auto_replies','defer_render']:
                if k in data:
                    if not isinstance(data[k],bool):raise ValueError('Opzione non valida.')
                    updated[k]=data[k]
            for k,lo,hi in [('gap_seconds',1,30),('max_minutes',1,120)]:
                if k in data:
                    value=int(data[k])
                    if not lo<=value<=hi:raise ValueError(f'{k}: scegli un valore fra {lo} e {hi}.')
                    updated[k]=value
            if 'playlist' in data:
                ids=data['playlist'];available={e['id'] for e in self.catalog()}
                if not isinstance(ids,list) or len(ids)>30 or any(i not in available for i in ids):raise ValueError('Scaletta non valida: scegli episodi completati.')
                updated['playlist']=ids
            if 'replies' in data:
                replies=data['replies']
                if not isinstance(replies,list) or not 1<=len(replies)<=12:raise ValueError('Prepara da una a dodici risposte.')
                parsed=[]
                for r in replies:
                    triggers=r.get('triggers',[])
                    if not isinstance(triggers,list) or not 1<=len(triggers)<=8:raise ValueError('Ogni risposta richiede da uno a otto segnali.')
                    text=clean(r.get('text'),600)
                    if '[[' in text or ']]' in text:raise ValueError('I comandi vocali non sono ammessi.')
                    parsed.append({'id':clean(r.get('id'),32),'name':clean(r.get('name'),60),
                                   'triggers':[clean(t,50) for t in triggers],'text':text})
                updated['replies']=parsed
            if updated['autopilot'] and 'playlist' in data and not updated['playlist']:
                raise ValueError('Scegli almeno un episodio per la scaletta automatica.')
            if updated.get('language','it')!=self.config.get('language','it'):updated['auto_replies']=False
            self.config=updated;providers.atomic_json(self.path,updated)
            return copy.deepcopy(updated)

    def snapshot(self):
        with self.lock:
            current=copy.deepcopy(self.current)
            return {'phase':self.phase,'config':copy.deepcopy(self.config),'current':current,
                'character_settings':copy.deepcopy(self.session_settings) if self.session_settings else languages.apply(platform_store.render_settings(providers.settings(),self.config.get('character_id')),{'language':self.config.get('language','it')}),
                'queue':copy.deepcopy(self.queue),'history':copy.deepcopy(self.history[-20:]),
                'messages':copy.deepcopy(self.messages[-60:]),'position':self.position,'elapsed':round(self.elapsed,2),
                'scene':self.scene_status,'scene_connected':bool(self.lease and self.clock()-self.lease_seen<4),
                'owner':self.lease,'error':self.error,'playlist_position':self.cursor,'playlist_length':len(self.playlist)}

    def claim(self,client,force=False):
        client=clean(client,64)
        with self.lock:
            active=self.lease and self.clock()-self.lease_seen<4
            if active and self.lease!=client and not force:return {'owner':False}
            if self.lease and self.lease!=client and self.phase in ('running','paused'):
                self.phase='paused';self.error='Uscita audio trasferita. Premi Riprendi per continuare.'
            self.lease=client;self.lease_seen=self.clock();self.scene_status='Collegata'
            return {'owner':True}

    def heartbeat(self,data):
        with self.lock:
            if data.get('client')!=self.lease:return {'owner':False}
            self.lease_seen=self.clock()
            self.scene_status={'ready':'Pronta','playing':'Voce in corso','paused':'In pausa','blocked':'Audio da attivare','error':'Errore audio'}.get(data.get('status'),'Collegata')
            if self.current and data.get('item')==self.current['id']:
                p=float(data.get('position',0))
                if p==p:self.position=max(0,min(p,self.current.get('duration',0)))
                if data.get('status') in ('blocked','error'):
                    self.phase='paused';self.error='Attiva o ripristina l’audio nella scena, poi premi Riprendi.'
                if data.get('ended') and self.phase=='running':self._finish('played')
            return {'owner':True}

    def _finish(self,state):
        if self.current:
            self.history.append({'title':self.current['title'],'kind':self.current['kind'],'state':state,'at':time.time()})
            self._message_state(self.current,'answered' if state=='played' else 'review',
                'Risposta pronunciata nella scena locale.' if state=='played' else 'Intervento interrotto o saltato: verifica quanto è già stato pronunciato prima di ripeterlo.')
        self.current=None;self.position=0;self.next_at=self.clock()+self.config['gap_seconds']
        self.history=self.history[-100:]

    def _message_state(self,item,state,reason):
        message=next((m for m in self.messages if m['id']==item.get('message_id')),None)
        if message:message.update(state=state,reason=reason)

    def _cancel_queue(self):
        for item in self.queue:self._message_state(item,'review','Intervento annullato prima della riproduzione. Puoi preparare una nuova risposta.')
        self.epoch+=1;self.queue.clear()

    def control(self,action):
        with self.lock:
            if action in ('start','resume'):
                if not self.lease or self.clock()-self.lease_seen>=4:raise ValueError('Apri prima la scena e attiva l’audio.')
                if action=='start':
                    if self.phase in ('running','paused'):raise ValueError('La sessione è già aperta. Usa Riprendi oppure Stop.')
                    available={e['id']:e for e in self.catalog()}
                    ids=self.config['playlist'] or list(available)
                    self.playlist=[copy.deepcopy(available[i]) for i in ids if i in available]
                    if self.config['autopilot'] and not self.playlist:raise ValueError('La scaletta non contiene episodi completati.')
                    self.session_settings=languages.apply(platform_store.render_settings(providers.settings(),self.config.get('character_id')),{'language':self.config.get('language','it')})
                    self.session_id=self.activity.start(self.config['title'],self.session_settings)
                    self.cursor=0;self.elapsed=0;self.started=self.clock();self.next_at=0
                elif self.phase!='paused':raise ValueError('Non c’è una sessione in pausa.')
                self.phase='running';self.last_tick=self.clock();self.error=''
            elif action=='pause':
                if self.phase=='running':self.phase='paused'
            elif action=='skip':self._finish('skipped')
            elif action in ('stop','emergency'):
                self.activity.end(self.session_id,'stopped' if action=='stop' else 'emergency',self.elapsed);self.session_id=None
                self.session_settings=None
                self._cancel_queue();self._finish('stopped');self.phase='idle' if action=='stop' else 'emergency'
                self.error='Voce e coda interrotte.' if action=='emergency' else ''
            else:raise ValueError('Comando della regia non valido.')
            return self.snapshot()

    def tick(self):
        with self.lock:
            now=self.clock();dt=max(0,now-self.last_tick);self.last_tick=now
            if self.phase!='running':return
            if not self.lease or now-self.lease_seen>=4:
                self.phase='paused';self.scene_status='Disconnessa';self.error='Scena disconnessa: la regia è in pausa.';return
            self.elapsed+=dt
            if self.elapsed>=self.config['max_minutes']*60:
                self.activity.end(self.session_id,'finished',self.elapsed);self.session_id=None
                self.session_settings=None
                self._cancel_queue();self._finish('limit');self.phase='finished';return
            if self.current or now<self.next_at:return
            ready=next((q for q in self.queue if q['state']=='ready'),None)
            if ready:
                self.queue.remove(ready);self.current=ready;self.position=0;return
            if self.queue:return
            if self.config['autopilot'] and self.playlist:
                if self.cursor>=len(self.playlist):
                    if self.config['loop']:self.cursor=0
                    else:
                        self.activity.end(self.session_id,'finished',self.elapsed);self.session_id=None
                        self.session_settings=None
                        self.phase='finished';return
                episode=self.playlist[self.cursor];self.cursor+=1
                self.enqueue(episode['title'],episode['script'],'episode',episode=episode)

    def enqueue(self,title,text,kind='manual',episode=None,message_id=None):
        title=clean(title,80);text=clean(text,2400 if kind=='episode' else 600)
        if '[[' in text or ']]' in text:raise ValueError('I comandi vocali non sono ammessi.')
        with self.lock:
            if len(self.queue)>=12:raise ValueError('La coda contiene già dodici interventi.')
            item={'id':uuid.uuid4().hex[:16],'title':title,'text':text,'kind':kind,'state':'preparing'}
            if message_id:item['message_id']=message_id
            epoch=self.epoch;config=copy.deepcopy(self.session_settings) if self.session_settings else languages.apply(platform_store.render_settings(providers.settings(),self.config.get('character_id')),{'language':self.config.get('language','it')})
            if episode:config=languages.apply(config,{'language':episode['project']['settings'].get('language','it')})
            self.queue.append(item)
            self.executor.submit(self._prepare,item,epoch,config,episode)
            return copy.deepcopy(item)

    def _prepare(self,item,epoch,config,episode):
        try:
            if episode and all(episode['project']['settings'].get(k)==config[k] for k in ('voice','rate')):
                project=episode['project'];base='/output/'+episode['job_id']
            else:
                identity=hashlib.sha256(json.dumps([item['text'],config['voice'],config['rate'],3]).encode()).hexdigest()[:16]
                folder=self.assets/identity;folder.mkdir(exist_ok=True);project_file=folder/'project.json'
                if project_file.exists():project=json.loads(project_file.read_text())
                else:
                    def progress(p,m):
                        with self.lock:
                            if self.epoch!=epoch:raise ValueError('Preparazione annullata.')
                    timeline=media.synthesize(item['text'],config,folder,progress)
                    project={**timeline,'script':item['text'],'settings':config};providers.atomic_json(project_file,project)
                base='/live-assets/'+identity
            with self.lock:
                if epoch!=self.epoch or item not in self.queue:return
                item.update(state='ready',audio=base+'/voice.wav',timeline=base+'/project.json',duration=project['duration'],settings=config)
        except Exception as exc:
            with self.lock:
                if epoch!=self.epoch or item not in self.queue:return
                self.queue.remove(item)
                self._message_state(item,'review','Voce non preparata. Correggi il problema prima di riprovare.')
                self.error='Intervento non preparato: '+str(exc)[:160]
                self.history.append({'title':item['title'],'kind':item['kind'],'state':'error','at':time.time()})

    def remove(self,identity):
        with self.lock:
            for item in self.queue:
                if item['id']==identity:self._message_state(item,'review','Intervento rimosso dalla coda. Puoi correggere la risposta e prepararla di nuovo.')
            self.queue=[q for q in self.queue if q['id']!=identity]
            return {'ok':True}

    def receive(self,author,text,source='test',event_id=None,user_id=None):
        text=clean(text,400);author=clean(author,40)
        author=re.sub(r'[^\w .-]','',author)[:32] or 'Spettatore'
        with self.lock:
            now=self.clock();self.seen={k:v for k,v in self.seen.items() if now-v<300}
            self.users={k:v for k,v in self.users.items() if now-v<60}
            key=source+':'+str(event_id or hashlib.sha256((author+text).encode()).hexdigest())
            if key in self.seen:return {'duplicate':True}
            self.seen[key]=now
            # Bound memory even under a burst of unique events.
            self.seen=dict(list(self.seen.items())[-500:])
            user=source+':'+str(user_id or author)
            recent=user in self.users and now-self.users[user]<10
            self.users[user]=now;self.users=dict(list(self.users.items())[-300:])
            reply,reason=classify(text,self.config['replies'])
            m={'id':uuid.uuid4().hex[:16],'author':author,'text':text,'source':source,'state':'review','reason':reason or '', 'at':time.time()}
            if recent:m['reason']='Messaggio ravvicinato: risposta automatica limitata.'
            elif reply:
                m['suggested']=reply['text'];m['reason']='Risposta prevista: '+reply['name']
                cooldown=now-self.reply_times.get(reply['id'],-1000)<30
                if self.config['auto_replies'] and self.phase=='running' and not cooldown:
                    try:
                        self.enqueue(reply['name'],reply['text'],'reply',message_id=m['id'])
                        m['state']='queued';self.reply_times[reply['id']]=now
                    except ValueError:m['reason']='Coda piena. Rispondi più tardi.'
                elif cooldown:m['reason']='Risposta già usata negli ultimi trenta secondi.'
            self.messages.append(m);self.messages=self.messages[-60:]
            return copy.deepcopy(m)

    def respond(self,data):
        with self.lock:
            message=next((m for m in self.messages if m['id']==data.get('id')),None)
            if not message:raise ValueError('Messaggio non trovato.')
            if data.get('dismiss'):
                message['state']='dismissed';return {'ok':True}
            if message['state'] in ('queued','answered'):raise ValueError('Una risposta a questo messaggio è già in coda o è stata pronunciata.')
            item=self.enqueue('Risposta alla chat',data.get('text'),'reply',message_id=message['id'])
            message['state']='queued';return item

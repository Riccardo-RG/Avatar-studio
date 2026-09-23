"""Durable editorial approval and delivery queue. Real delivery is disarmed on every boot."""
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import subprocess
import threading
import time
import uuid
from zoneinfo import ZoneInfo
import media
import providers
import service_connections as services
import social_adapters as adapters

ROOT=Path(__file__).resolve().parent
PATH=ROOT/'data/publications.json'
LOCK=threading.RLock()
BUSY=set()
ARMED=False
STOP=threading.Event()
TERMINAL={'published','handed_off','cancelled'}
FROZEN=('job_id','platform','title','description','visibility','made_for_kids','source_url','due_at','timezone','media_sha256','media_bytes','account_id','connection_id','language')

def load():
    doc=json.loads(PATH.read_text()) if PATH.exists() else {'items':[],'events':[]}
    for item in doc['items']:
        if 'connection_id' not in item or 'language' not in item:
            legacy_digest=hashlib.sha256(json.dumps({k:item[k] for k in FROZEN if k in item},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            item.setdefault('connection_id','default');item.setdefault('connection_name','Principale');item.setdefault('language','it')
            # Extend only a valid existing approval: its remote account and content stay unchanged.
            if item.get('approval') and item['approval']['digest']==legacy_digest and item['approval']['revision']==item['revision']:
                item['approval']['digest']=digest(item)
    doc['version']=2
    return doc

def write(doc):providers.atomic_json(PATH,doc)
def event(doc,kind,ids):doc['events']=(doc['events']+[{'at':time.time(),'type':kind,'ids':ids}])[-500:]
def find(doc,identity):
    item=next((p for p in doc['items'] if p['id']==identity),None)
    if not item:raise ValueError('Post non trovato.')
    return item
def digest(item):return hashlib.sha256(json.dumps({k:item[k] for k in FROZEN},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def file(item):return ROOT/'output/publish-media'/item['job_id']/item['platform']/'video.mp4'

def due(value):
    try:
        when=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
        if when.tzinfo is None:raise ValueError()
        if not 2020<=when.year<=2100:raise ValueError()
        return when.timestamp()
    except (ValueError,TypeError,AttributeError):raise ValueError('Scegli un orario valido con fuso orario.') from None

def week(item):
    local=dt.datetime.fromtimestamp(due(item['due_at']),ZoneInfo(item['timezone']));y,w,_=local.isocalendar()
    return f'{y}-W{w:02d}'

def wall_time(value,zone):
    try:
        local=dt.datetime.fromisoformat(value)
        if local.tzinfo is not None:raise ValueError()
        timezone=ZoneInfo(zone)
        candidates={local.replace(tzinfo=timezone,fold=fold).timestamp() for fold in (0,1)
                    if dt.datetime.fromtimestamp(local.replace(tzinfo=timezone,fold=fold).timestamp(),timezone).replace(tzinfo=None)==local}
        if len(candidates)!=1:raise ValueError()
        return dt.datetime.fromtimestamp(candidates.pop(),dt.timezone.utc).isoformat()
    except Exception:raise ValueError('Orario inesistente o ambiguo per il cambio dell’ora. Scegli un altro orario nel fuso indicato.') from None

def prepare_media(job_id,platform):
    if not re.fullmatch(r'[a-f0-9]{12}',job_id):raise ValueError('Video non valido.')
    folder=ROOT/'output'/job_id
    if not (folder/'status.json').exists() or json.loads((folder/'status.json').read_text()).get('state')!='done':raise ValueError('Scegli un video completato.')
    source=folder/'video.mp4';project=json.loads((folder/'project.json').read_text())
    dest=ROOT/'output/publish-media'/job_id/platform/'video.mp4';dest.parent.mkdir(parents=True,exist_ok=True)
    if not dest.exists():
        # Instagram asks for AAC at 48 kHz; keep the reviewed original unchanged.
        temp=dest.with_name('preparing.mp4')
        result=subprocess.run([media.ffmpeg_path(),'-v','error','-y','-i',str(source),'-map','0:v:0','-map','0:a:0','-c:v','copy','-c:a','aac','-ar','48000','-b:a','128k','-movflags','+faststart',str(temp)],capture_output=True,timeout=180)
        if result.returncode:raise ValueError('Preparazione del file social non riuscita.')
        temp.replace(dest)
    if not 0<dest.stat().st_size<=150_000_000:raise ValueError('Il file social supera il limite locale di 150 MB.')
    return dest,project,json.loads((folder/'platforms.json').read_text())[platform]

def save(data):
    platform=data.get('platform');job_id=data.get('job_id','')
    if platform not in ('youtube','tiktok','instagram'):raise ValueError('Piattaforma non valida.')
    with LOCK:
        doc=load();old=find(doc,data['id']) if data.get('id') else None
        if old and (old['id'] in BUSY or old['state'] not in ('draft','approved','missed')):raise ValueError('Questo post ha già un tentativo di invio: non può essere modificato.')
        if old and data.get('revision')!=old['revision']:raise ValueError('Post modificato in un’altra scheda. Ricarica.')
        profile_id=data.get('connection_id') or (old['connection_id'] if old and old['platform']==platform else None)
        connection=services.config(platform,profile_id);profile_id=connection['id']
        if any(p['id']!=data.get('id') and p['job_id']==job_id and p['platform']==platform and p['state']!='cancelled' and
               (p['connection_id']==profile_id or (connection.get('account_id') and p.get('account_id')==connection['account_id'])) for p in doc['items']):
            raise ValueError('Questo video è già nella coda per lo stesso account. Puoi scegliere un altro account.')
        path,project,meta=prepare_media(job_id,platform)
        item={'id':old['id'] if old else uuid.uuid4().hex[:12],'revision':(old['revision'] if old else 0)+1,'created':old['created'] if old else time.time(),
              'job_id':job_id,'platform':platform,'title':str(data.get('title') or meta['title']).strip(),'description':str(data.get('description',meta['description'])).strip(),
              'visibility':data.get('visibility',''),'made_for_kids':data.get('made_for_kids') is True,'source_url':str(data.get('source_url','')).strip(),
              'due_at':data.get('due_at',''),'timezone':str(data.get('timezone','Europe/Rome')),'state':'draft','account_id':connection.get('account_id',''),'connection_id':profile_id,'connection_name':connection.get('nickname','Principale'),
              'media_sha256':sha(path),'media_bytes':path.stat().st_size,'duration':project['duration'],'language':project.get('settings',{}).get('language','' if project.get('clip') else 'it'),'approval':None,'metrics':[],'message':'Da revisionare.'}
        if data.get('due_local'):item['due_at']=wall_time(data['due_local'],item['timezone'])
        due(item['due_at'])
        try:ZoneInfo(item['timezone'])
        except Exception:raise ValueError('Fuso orario non valido.') from None
        if not 1<=len(item['title'])<=100 or len(item['description'])>5000 or len(item['source_url'])>2000:raise ValueError('Titolo, descrizione o URL troppo lunghi.')
        if platform=='instagram' and len(item['description'])>2200:raise ValueError('Instagram: riduci il testo a 2200 caratteri prima di approvarlo.')
        if item['visibility'] not in {'youtube':('private','unlisted','public'),'tiktok':('inbox',),'instagram':('public',)}[platform]:raise ValueError('Scegli esplicitamente la destinazione/visibilità.')
        if item['source_url']:
            from web_sources import public_url
            public_url(item['source_url'])
            if not item['source_url'].startswith('https://'):raise ValueError('Usa un URL HTTPS pubblico.')
        if old:doc['items'][doc['items'].index(old)]=item
        else:doc['items'].append(item)
        event(doc,'saved',[item['id']]);write(doc);return item

def approve(data):
    entries=data.get('items',[]);mode=data.get('mode','single')
    if mode not in ('single','weekly') or not entries or len(entries)>50 or (mode=='single' and len(entries)!=1):raise ValueError('Scegli un post oppure un gruppo settimanale.')
    if len({e['id'] for e in entries})!=len(entries):raise ValueError('Post duplicati nella selezione.')
    with LOCK:
        doc=load();selected=[]
        for entry in entries:
            p=find(doc,entry['id'])
            if p['revision']!=entry.get('revision') or p['state'] not in ('draft','approved','missed') or p['id'] in BUSY:raise ValueError('Un post è cambiato o non è approvabile. Rivedi la selezione.')
            if due(p['due_at'])<time.time()-60:raise ValueError('Un orario è già passato. Aggiornalo prima di approvare.')
            if sha(file(p))!=p['media_sha256']:raise ValueError('Il file è cambiato: prepara nuovamente il post.')
            selected.append(p)
        if mode=='weekly' and len({(week(p),p['timezone']) for p in selected})!=1:raise ValueError('Il gruppo deve appartenere alla stessa settimana e allo stesso fuso.')
        batch=uuid.uuid4().hex[:12]
        for p in selected:
            p.update(state='approved',message='Approvato. L’invio reale resta separato dalla simulazione.')
            p['approval']={'at':time.time(),'mode':mode,'batch':batch,'digest':digest(p),'revision':p['revision']}
        event(doc,'approved_'+mode,[p['id'] for p in selected]);write(doc)
        return {'approved':len(selected),'batch':batch}

def valid(p):return bool(p.get('approval') and p['approval']['digest']==digest(p) and p['approval']['revision']==p['revision'])

def simulate(data):
    ids=data.get('ids',[])
    if not ids or len(ids)>50:raise ValueError('Scegli i post da simulare.')
    with LOCK:
        doc=load();report=[]
        for identity in ids:
            p=find(doc,identity)
            if not valid(p) or p['state']!='approved':raise ValueError('Approva il contenuto prima della simulazione.')
            if sha(file(p))!=p['media_sha256']:raise ValueError('Il file è cambiato dopo l’approvazione.')
            steps=['Approvazione e impronta del file verificate','Orario: '+p['due_at'],{'youtube':'Upload riprendibile → elaborazione → controllo visibilità','tiktok':'Caricamento → posta TikTok → completamento manuale nell’app','instagram':'Verifica file pubblico → container → elaborazione → pubblicazione'}[p['platform']]]
            p['simulation']={'at':time.time(),'steps':steps,'external_requests':0,'readiness':adapters.preflight(p)};report.append({'id':identity,**p['simulation']})
        event(doc,'simulated',ids);write(doc);return {'simulated':report,'published':False}

def set_armed(data):
    global ARMED
    if type(data.get('enabled')) is not bool:raise ValueError('Stato invio non valido.')
    with LOCK:ARMED=data['enabled']
    return snapshot()

def cancel(data):
    with LOCK:
        doc=load();p=find(doc,data['id'])
        if p['state'] in ('published','handed_off'):raise ValueError('Il contenuto è già sul servizio; gestiscilo dalla piattaforma.')
        p['cancel_requested']=True
        p.update(state='uncertain' if p['id'] in BUSY or p.get('remote_id') or p.get('container_id') else 'cancelled',message='Stop locale richiesto. Un invio già iniziato può completarsi sul servizio.')
        event(doc,'stopped',[p['id']]);write(doc);return p

def patch(identity,fields):
    with LOCK:
        doc=load();p=find(doc,identity)
        if fields.get('state')=='published' and not p.get('published_at'):fields={**fields,'published_at':time.time()}
        p.update(fields);write(doc);return copy.deepcopy(p)

def stopped(identity):
    with LOCK:return STOP.is_set() or not ARMED or find(load(),identity).get('cancel_requested',False)

def deliver(identity,automatic=False):
    with LOCK:
        doc=load();p=find(doc,identity)
        if not ARMED:raise ValueError('Invio reale disattivato. Usa la simulazione oppure abilitalo dopo il collaudo dei collegamenti.')
        if BUSY:raise ValueError('Un invio è già in corso.')
        if p['state']!='approved' or not valid(p):raise ValueError('Serve una nuova approvazione prima dell’invio.')
        if due(p['due_at'])>time.time()+1:raise ValueError('Il post è programmato per un orario futuro.')
        if time.time()-due(p['due_at'])>3600:
            p.update(state='missed',message='Orario superato di oltre un’ora: riprogramma e approva nuovamente.');write(doc);return p
        errors=adapters.preflight(p)
        if errors:raise ValueError(' '.join(errors))
        if sha(file(p))!=p['media_sha256']:raise ValueError('File diverso da quello approvato.')
        if not p['account_id']:raise ValueError('Post approvato prima del collegamento del canale. Salvalo e approvalo nuovamente con l’account verificato.')
        BUSY.add(identity);p.update(state='sending',message='Verifica del canale e invio in corso.',attempted_at=time.time());event(doc,'send_started',[identity]);write(doc)
        snapshot=copy.deepcopy(p)
    threading.Thread(target=_send,args=(snapshot,),daemon=True).start();return snapshot

def _send(p):
    identity=p['id']
    try:
        with services.bound(p['platform'],p['connection_id']):
            current=services.verify(p['platform'],p['connection_id'])
            if current['account_id']!=p['account_id']:raise ValueError('Il canale collegato è diverso da quello approvato.')
            result=adapters.send(p,file(p),lambda fields:patch(identity,fields),lambda:stopped(identity))
            patch(identity,result)
    except Exception as exc:patch(identity,{'state':'uncertain','message':str(exc)[:400]+' Nessun reinvio automatico.'})
    finally:
        with LOCK:BUSY.discard(identity)

def check(data):
    identity=data['id']
    with LOCK:
        p=copy.deepcopy(find(load(),identity))
        if BUSY:raise ValueError('Un controllo o invio è già in corso.')
        if not p.get('attempted_at'):raise ValueError('Nessun invio remoto da controllare.')
        BUSY.add(identity)
    def checkpoint(fields):
        with LOCK:
            current=find(load(),identity)
            if fields.get('stage')=='publish_requested':
                # Polling can take time. Recheck the stop switch atomically with
                # the durable intent, immediately before the non-idempotent call.
                if STOP.is_set() or not ARMED or current.get('cancel_requested') or not valid(current) or current.get('stage')=='publish_requested':
                    raise ValueError('Pubblicazione fermata prima dell’invio. Nessuna nuova richiesta di pubblicazione è stata inviata.')
            return patch(identity,fields)
    try:
        with services.bound(p['platform'],p['connection_id']):
            who=services.verify(p['platform'],p['connection_id'])
            if who['account_id']!=p['account_id']:raise ValueError('Canale diverso da quello del post.')
            allow=ARMED and valid(p) and not p.get('cancel_requested') and p.get('stage')!='publish_requested'
            result=adapters.reconcile(p,checkpoint,allow_publish=allow)
            return patch(identity,result)
    except Exception as exc:
        patch(identity,{'state':'uncertain','message':str(exc)[:400]});raise
    finally:
        with LOCK:BUSY.discard(identity)

def collect_metrics(data):
    with LOCK:p=copy.deepcopy(find(load(),data['id']))
    if p['state']!='published':raise ValueError('Le metriche richiedono una pubblicazione confermata.')
    with services.bound(p['platform'],p['connection_id']):
        who=services.verify(p['platform'],p['connection_id'])
        if who['account_id']!=p['account_id']:raise ValueError('Canale diverso da quello del post.')
        result=adapters.metrics(p)
    with LOCK:
        doc=load();item=find(doc,p['id']);item['metrics']=(item.get('metrics',[])+[result])[-30:];write(doc)
    return result

def snapshot():
    with LOCK:
        doc=load()
        for p in doc['items']:
            p['week']=week(p);p['preview_url']=f'/publish-media/{p["job_id"]}/{p["platform"]}/video.mp4';p['readiness']=adapters.preflight(p)
            p['poster_url']=f'/output/{p["job_id"]}/cover.png'
        return {**doc,'armed':ARMED,'busy':bool(BUSY),'server_must_remain_on':True,'late_window_minutes':60}

def recover():
    with LOCK:
        doc=load()
        for p in doc['items']:
            if p['state']=='sending':p.update(state='uncertain',message='Invio interrotto dal riavvio: controlla il servizio prima di qualsiasi nuovo tentativo.')
        write(doc)

def scheduler_tick():
    if not ARMED or BUSY:return
    for p in sorted(load()['items'],key=lambda p:due(p['due_at'])):
        if STOP.is_set() or not ARMED or BUSY:return
        if p['state']=='approved' and due(p['due_at'])<=time.time():
            try:deliver(p['id'],automatic=True)
            except ValueError as exc:patch(p['id'],{'message':str(exc)[:400]})
        elif p['state']=='processing' and not p.get('cancel_requested'):
            try:check({'id':p['id']})
            except ValueError:pass

def scheduler():
    while not STOP.wait(15):
        try:scheduler_tick()
        except Exception:continue

def start():recover();STOP.clear();threading.Thread(target=scheduler,daemon=True).start()
def close():
    global ARMED
    ARMED=False;STOP.set()

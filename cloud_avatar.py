"""HeyGen v3 image+audio adapter. Explicit quotes, no automatic submissions/retries."""
import languages
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import threading
import time
import urllib.request
import uuid
import media
import platform_store as store
import providers
import runtime_config
from web_sources import read_public

LOCK=threading.RLock()
QUOTES={}
BASE='https://api.heygen.com/v3'

def status():
    return {'heygen':bool(os.environ.get('HEYGEN_API_KEY')),'brave':bool(os.environ.get('BRAVE_SEARCH_API_KEY'))}

def keys(data):
    for key,env in [('heygen','HEYGEN_API_KEY'),('brave','BRAVE_SEARCH_API_KEY')]:
        if key in data:
            value=store.text(data[key],500)
            if value:os.environ[env]=value
            else:os.environ.pop(env,None)
    return status()

def quote(data, config=None):
    planning=data.get('planning') is True
    if not planning and not status()['heygen']:raise ValueError('Collega prima la chiave API HeyGen nella sezione Servizi.')
    script=store.text(data.get('script',''),2400,True)
    config=config if config is not None else languages.apply(store.render_settings(providers.settings(),data.get('character_id')),data)
    if config['character']['kind']=='robot':raise ValueError('Scegli un personaggio con immagine per il motore realistico.')
    price=store.load()['prices']['heygen_eur_minute']
    if not planning and price<=0:raise ValueError('Inserisci il costo stimato in euro per minuto del tuo piano HeyGen.')
    identity=uuid.uuid4().hex[:24];folder=store.ROOT/'data/cloud-previews'/identity;folder.mkdir(parents=True)
    timeline=media.synthesize(script,config,folder,lambda p,m:None)
    amount=round(math.ceil(timeline['duration']/60)*price,4)
    if planning:
        return {'duration':timeline['duration'],'estimated_eur':amount if price>0 else None,'character':config['character']['name'],'engine':'HeyGen Avatar IV','external_requests':0,
                'ready':bool(status()['heygen'] and price>0),'missing':[name for name,ok in [('chiave HeyGen',status()['heygen']),('tariffa euro/minuto',price>0)] if not ok],
                'note':'Voce preparata localmente. Nessuna immagine o traccia inviata al servizio.'}
    q={'id':identity,'expires':time.time()+600,'script':script,'title':store.text(data.get('title','Prova avatar realistico'),80,True),'config':config,'timeline':timeline,'folder':str(folder),'amount_eur':amount,'campaign_id':data.get('campaign_id','')}
    if amount>store.budget_summary()['remaining_eur']:raise ValueError('La stima supera il budget mensile residuo.')
    with LOCK:
        for k,v in list(QUOTES.items()):
            if v['expires']<time.time():QUOTES.pop(k)
        QUOTES[identity]=q
    return {'quote_id':identity,'duration':timeline['duration'],'estimated_eur':amount,'expires':q['expires'],'character':config['character']['name'],'engine':'HeyGen Avatar IV','uploads':['immagine del personaggio','traccia vocale sintetica'],'note':'Stima arrotondata al minuto. Verifica la tariffa del tuo piano; non è un preventivo del fornitore.'}

def consume(identity):
    with LOCK:
        q=QUOTES.get(identity)
        if not q or q['expires']<time.time():raise ValueError('Preventivo scaduto o già usato. Preparane uno nuovo.')
        q['reservation_id']=store.reserve('heygen',q['amount_eur'],q['campaign_id'],q['title']);QUOTES.pop(identity)
        return q

def request(route,payload=None,content_type='application/json',idempotency=None,timeout=90):
    key=os.environ.get('HEYGEN_API_KEY')
    if not key:raise ValueError('La chiave HeyGen non è più disponibile.')
    body=json.dumps(payload).encode() if isinstance(payload,dict) else payload
    headers={'x-api-key':key,'Content-Type':content_type}
    if idempotency:headers['Idempotency-Key']=idempotency
    req=urllib.request.Request(BASE+route,data=body,headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=timeout,context=runtime_config.ssl_context()) as response:result=json.load(response)
    except Exception:raise ValueError('HeyGen non ha confermato la richiesta. Nessun reinvio automatico; verifica il dashboard prima di riprovare.') from None
    if not isinstance(result.get('data'),dict):raise ValueError('Risposta HeyGen non riconosciuta.')
    return result['data']

def upload(path,kind):
    raw=Path(path).read_bytes()
    if len(raw)>32_000_000:raise ValueError('File oltre il limite di caricamento HeyGen.')
    boundary='avatar-'+uuid.uuid4().hex
    body=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="source.{"png" if kind=="image/png" else "wav"}"\r\nContent-Type: {kind}\r\n\r\n').encode()+raw+f'\r\n--{boundary}--\r\n'.encode()
    return request('/assets',body,'multipart/form-data; boundary='+boundary)['asset_id']

def payload(image_id,audio_id,title):
    return {'type':'image','image':{'type':'asset_id','asset_id':image_id},'audio_asset_id':audio_id,'title':title,'aspect_ratio':'9:16','resolution':'720p','output_format':'mp4','engine':{'type':'avatar_iv'}}

def generate(q,folder,cancelled,progress):
    config=q['config'];source=Path(q['folder'])
    for name in ('voice.wav','captions.srt'):shutil.copy2(source/name,folder/name)
    providers.atomic_json(folder/'cloud-recovery.json',{'title':q['title'],'script':q['script'],'settings':q['config'],**q['timeline']})
    progress(10,'Invio dell’immagine e della voce a HeyGen')
    image_id=upload(store.asset_file(config['character']['image']),'image/png')
    if cancelled():raise ValueError('Produzione fermata prima dell’invio del video.')
    audio_id=upload(folder/'voice.wav','audio/wav')
    if cancelled():raise ValueError('Produzione fermata prima dell’invio del video.')
    response=request('/videos',payload(image_id,audio_id,q['title']),idempotency=q['id'])
    remote_id=response.get('video_id','')
    if not re.fullmatch(r'[A-Za-z0-9_-]{5,128}',remote_id):raise ValueError('Identificatore del video HeyGen non valido.')
    providers.atomic_json(folder/'external.json',{'provider':'heygen','video_id':remote_id,'reservation_id':q['reservation_id'],'estimated_eur':q['amount_eur']})
    wait_video(remote_id,folder,cancelled,progress)

def wait_video(remote_id,folder,cancelled,progress):
    deadline=time.monotonic()+900
    for attempt in range(90):
        if cancelled():raise ValueError('Controllo locale fermato. La generazione già inviata può continuare ed essere addebitata da HeyGen.')
        remaining=deadline-time.monotonic()
        if remaining<=0:break
        state=request('/videos/'+remote_id,timeout=min(90,remaining))
        if state.get('status')=='failed':raise ValueError('HeyGen ha segnalato un errore di generazione. Controlla il suo dashboard.')
        if state.get('status')=='completed':
            url=state.get('video_url','');raw,mime,final=read_public(url,maximum=150_000_000)
            if len(raw)<12 or raw[4:8]!=b'ftyp':raise ValueError('Il risultato HeyGen non è un MP4 valido.')
            (folder/'external.mp4').write_bytes(raw);return
        progress(min(85,20+attempt),'Animazione realistica in preparazione su HeyGen')
        for second in range(10):
            remaining=deadline-time.monotonic()
            if cancelled() or remaining<=0:break
            time.sleep(min(1,remaining))
    raise ValueError('Il video non è pronto entro 15 minuti. Usa l’ID in external.json per verificarlo senza creare un secondo addebito.')

def recovery(folder):
    if not (folder/'external.json').exists() or not (folder/'cloud-recovery.json').exists():raise ValueError('Mancano i dati per recuperare questa generazione. Controlla il pannello HeyGen.')
    external=json.loads((folder/'external.json').read_text());remote=external.get('video_id','')
    if not re.fullmatch(r'[A-Za-z0-9_-]{5,128}',remote):raise ValueError('ID HeyGen non valido.')
    if not status()['heygen']:raise ValueError('Collega HeyGen prima del recupero.')
    return remote,json.loads((folder/'cloud-recovery.json').read_text())

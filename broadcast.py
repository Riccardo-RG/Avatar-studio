"""Local OBS controls and an optional bounded Tavus conversation, disabled until configured."""
import json
import math
from pathlib import Path
import re
import subprocess
import threading
import time
import uuid
from urllib.parse import urlencode
import platform_store as store
import providers
import languages
import runtime_config
import service_connections as services

ROOT=Path(__file__).resolve().parent
PATH=ROOT/'data/broadcast.json'
LOCK=threading.RLock()
QUOTES={}
ROOMS={}

def obs(data,base):
    action=data.get('action','status')
    if action not in ('status','setup','start_record','stop_record','start_stream','stop_stream'):raise ValueError('Comando OBS non valido.')
    if action in ('start_record','start_stream') and data.get('confirmed') is not True:raise ValueError('Conferma esplicitamente l’avvio in OBS.')
    cfg=services.config('obs');port=int(cfg.get('port') or 4455)
    if not 1024<=port<=65535:raise ValueError('Porta OBS non valida.')
    payload={'action':action,'port':port,'password':services.secret('obs','password'),'scene_url':base+'/live-scene.html?obs=1'}
    # stdin avoids credentials in argv, process listings or persistent files.
    proc=subprocess.run([runtime_config.node(),str(ROOT/'obs_bridge.cjs')],input=json.dumps(payload),capture_output=True,text=True,timeout=55)
    try:result=json.loads(proc.stdout)
    except Exception:raise ValueError('Controllo OBS non riuscito. Verifica Node e OBS WebSocket.') from None
    if result.get('error'):raise ValueError(result['error'])
    return result

def load():return json.loads(PATH.read_text()) if PATH.exists() else {'sessions':[]}
def snapshot():
    with LOCK:return load()

def plan(data):
    minutes=int(store.number(data.get('minutes',2),1,20));cfg=services.config('tavus')
    character=store.snapshot(data.get('character_id'))
    rate=store.number(cfg.get('eur_minute',0),0,100)
    language=languages.code(data.get('language','it'))
    context=store.text(data.get('context','Parla in italiano. Presentati come personaggio virtuale.'),1600,True)
    context+='\n'+languages.instruction(language)
    missing=[]
    for field in ('face_id','pal_id'):
        if not re.fullmatch(r'[A-Za-z0-9_-]{2,100}',character.get('tavus_'+field,'')):missing.append(field+' nella scheda di '+character['name'])
    if not services.secret('tavus','api_key'):missing.append('chiave API')
    if rate<=0:missing.append('tariffa euro/minuto')
    amount=round(minutes*rate,4) if rate>0 else None
    q={'id':uuid.uuid4().hex[:24],'expires':time.time()+600,'minutes':minutes,'language':language,'context':context,'face_id':character.get('tavus_face_id'),'pal_id':character.get('tavus_pal_id'),'character_id':character['id'],'character_name':character['name'],'character_revision':character['revision'],'connection_revision':cfg.get('revision',0),'estimated_eur':amount,'missing':missing}
    with LOCK:QUOTES.clear();QUOTES[q['id']]=q
    return q

def start(data):
    if data.get('confirmed') is not True:raise ValueError('Conferma durata e stima prima della sessione esterna.')
    with services.bound('tavus'):
        return _start(data)

def _start(data):
    with LOCK:
        q=QUOTES.pop(data.get('quote_id',''),None)
        if not q or q['expires']<time.time():raise ValueError('Piano scaduto. Preparane uno nuovo.')
        if q['missing']:raise ValueError('Completa prima i collegamenti Tavus: '+', '.join(q['missing']))
        if services.config('tavus').get('revision',0)!=q.get('connection_revision',0) or not services.secret('tavus','api_key'):
            raise ValueError('Il collegamento o la tariffa Tavus sono cambiati. Prepara un nuovo piano prima di avviare la sessione.')
        if store.snapshot(q['character_id'])['revision'] != q['character_revision']:
            raise ValueError('Il personaggio è cambiato. Prepara un nuovo piano prima di avviare Tavus.')
        doc=load()
        if any(s['state'] in ('starting','active','uncertain') for s in doc['sessions']):raise ValueError('Chiudi o verifica la sessione precedente prima di crearne un’altra.')
        reservation=store.reserve('tavus',q['estimated_eur'],reference='Sessione video conversazionale')
        session={'id':q['id'],'state':'starting','created':time.time(),'minutes':q['minutes'],'language':q['language'],'estimated_eur':q['estimated_eur'],'reservation_id':reservation,
                 'character_id':q['character_id'],'character_name':q['character_name'],'character_revision':q['character_revision'],'face_id':q['face_id'],'pal_id':q['pal_id']}
        doc['sessions'].append(session);providers.atomic_json(PATH,doc)
    payload={'face_id':q['face_id'],'pal_id':q['pal_id'],'conversation_name':'Avatar Studio','conversational_context':q['context'],'require_auth':True,'max_participants':2,
             'properties':{'languages':[q['language']],'max_call_duration':q['minutes']*60,'participant_left_timeout':30,'participant_absent_timeout':60,'enable_recording':False}}
    try:
        r,_,_=services.http('https://tavusapi.com/v2/conversations','POST',payload,{'x-api-key':services.secret('tavus','api_key')})
        remote=r['conversation_id']
        if not re.fullmatch(r'[A-Za-z0-9_-]{2,100}',remote):raise ValueError('ID della conversazione non valido.')
        # Keep the recovery reference even when the join URL/token is unusable.
        # Creation is never retried automatically; the known room can still be ended.
        change(session['id'],{'remote_id':remote})
        services.checked_url(r['conversation_url'],{'tavus.daily.co'})
        with LOCK:ROOMS[session['id']]=r['conversation_url']+'?'+urlencode({'t':r['meeting_token']})
        return change(session['id'],{'state':'active','remote_id':remote,'deadline':time.time()+q['minutes']*60,'message':'Sessione pronta. Il limite di durata è inviato anche al servizio.'})
    except Exception:
        change(session['id'],{'state':'uncertain','message':'Creazione non confermata: verifica Tavus. Nessuna ripetizione automatica.'});raise

def change(identity,fields):
    with LOCK:
        doc=load();s=next((s for s in doc['sessions'] if s['id']==identity),None)
        if not s:raise ValueError('Sessione non trovata.')
        s.update(fields);providers.atomic_json(PATH,doc);return s

def room(identity):
    with LOCK:
        url=ROOMS.get(identity)
        if not url:raise ValueError('Accesso alla stanza non disponibile in questa sessione. Verifica Tavus; non creare una seconda chiamata.')
        return {'url':url}

def end(data):
    identity=data['id'];s=next((s for s in load()['sessions'] if s['id']==identity),None)
    if not s or not s.get('remote_id'):raise ValueError('ID remoto non disponibile. Verifica la sessione nel pannello Tavus.')
    services.http('https://tavusapi.com/v2/conversations/'+s['remote_id']+'/end','POST',headers={'x-api-key':services.secret('tavus','api_key')})
    with LOCK:ROOMS.pop(identity,None)
    return change(identity,{'state':'ended','message':'Sessione terminata sul servizio.'})

def recover():
    with LOCK:
        doc=load()
        for s in doc['sessions']:
            if s['state'] in ('starting','active'):s.update(state='uncertain',message='Server riavviato. Verifica/termina la sessione remota; nessun riavvio automatico.')
        providers.atomic_json(PATH,doc)

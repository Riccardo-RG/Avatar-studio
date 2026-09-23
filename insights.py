"""Real metric snapshots, comparable deltas, and opt-in collection while the Mac is on."""
import copy
import csv
import io
import json
from pathlib import Path
import threading
import time
import publishing
import providers

ROOT=Path(__file__).resolve().parent
PATH=ROOT/'data/insights.json'
LOCK=threading.RLock()
STOP=threading.Event()
ENABLED=False
RUNNING=False
LAST_RUN=0

def load():return json.loads(PATH.read_text()) if PATH.exists() else {'interval_minutes':60,'attempts':{},'errors':{}}

def settings(data):
    global ENABLED
    interval=int(data.get('interval_minutes',60))
    if not 15<=interval<=1440:raise ValueError('Intervallo consentito: da 15 minuti a 24 ore.')
    if type(data.get('enabled')) is not bool:raise ValueError('Scegli se attivare gli aggiornamenti.')
    with LOCK:
        doc=load();doc['interval_minutes']=interval;providers.atomic_json(PATH,doc);ENABLED=data['enabled']
    return snapshot()

def rows():
    with publishing.LOCK:posts=copy.deepcopy(publishing.load()['items'])
    result=[]
    for p in posts:
        if p['state']!='published':continue
        history=sorted(p.get('metrics',[]),key=lambda m:m['at']);latest=history[-1] if history else None;previous=history[-2] if len(history)>1 else None
        values=latest['values'] if latest else {};old=previous['values'] if previous else {}
        delta={key:value-old[key] if isinstance(value,(int,float)) and isinstance(old.get(key),(int,float)) else None for key,value in values.items()}
        cast=[]
        metadata=ROOT/'output'/p['job_id']/'status.json'
        if metadata.exists():cast=json.loads(metadata.read_text()).get('character_ids',[])
        result.append({'character_ids':cast,'published_at':p.get('published_at'),'id':p['id'],'job_id':p['job_id'],'title':p['title'],'platform':p['platform'],'url':p.get('url'),
            'account_id':p['account_id'],'connection_id':p.get('connection_id','default'),'connection_name':p.get('connection_name','Principale'),'latest_at':latest['at'] if latest else None,'previous_at':previous['at'] if previous else None,'values':values,'delta':delta,'samples':len(history)})
    return result

def snapshot():
    with LOCK:config=load();state={'enabled':ENABLED,'running':RUNNING,'last_run':LAST_RUN,'interval_minutes':config['interval_minutes'],'errors':config['errors']}
    state['items']=rows();state['note']='Contatori cumulativi: ogni post conta una volta. Le differenze confrontano le ultime due letture, non periodi identici; numeri di piattaforme diverse non sono una classifica comparabile.'
    return state

def collect(force=False):
    global RUNNING,LAST_RUN
    with LOCK:
        if RUNNING:return False
        RUNNING=True
    try:
        for row in rows():
            if STOP.is_set():break
            with LOCK:
                cfg=load()
                if not force and (not ENABLED or time.time()-cfg['attempts'].get(row['id'],0)<cfg['interval_minutes']*60):continue
                # Persist attempt first, including failures, to avoid a retry loop on expired tokens.
                cfg['attempts'][row['id']]=time.time();providers.atomic_json(PATH,cfg)
            error=''
            try:publishing.collect_metrics({'id':row['id']})
            except Exception as exc:error=str(exc)[:250]
            with LOCK:
                cfg=load()
                if error:cfg['errors'][row['id']]=error
                else:cfg['errors'].pop(row['id'],None)
                providers.atomic_json(PATH,cfg)
        return True
    finally:
        with LOCK:RUNNING=False;LAST_RUN=time.time()

def request_collection(data):
    with LOCK:
        if RUNNING:raise ValueError('Lettura dei risultati già in corso.')
    threading.Thread(target=collect,args=(True,),daemon=True,name='metrics-manual').start()
    return {'message':'Lettura dei contatori avviata. Nessun contenuto verrà pubblicato.'}

def csv_report():
    out=io.StringIO();writer=csv.writer(out);writer.writerow(['post_id','titolo','piattaforma','account','ultima_lettura','visualizzazioni','like','commenti','condivisioni','differenza_visualizzazioni','url'])
    def safe(value):
        if isinstance(value,(int,float)):return value
        value='' if value is None else str(value)
        return "'"+value if value.lstrip().startswith(('=','+','-','@')) or value.startswith(('\t','\r','\n')) else value
    for r in rows():writer.writerow([safe(v) for v in (r['id'],r['title'],r['platform'],r['account_id'],r['latest_at'],r['values'].get('views'),r['values'].get('likes'),r['values'].get('comments'),r['values'].get('shares'),r['delta'].get('views'),r.get('url'))])
    return out.getvalue()

def start():
    STOP.clear()
    def loop():
        while not STOP.wait(30):
            if ENABLED:collect()
    threading.Thread(target=loop,daemon=True,name='metrics-scheduler').start()

def close():
    global ENABLED
    ENABLED=False;STOP.set()

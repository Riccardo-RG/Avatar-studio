"""Explicit, resumable-by-content uploads to the user's Cloudflare R2 bucket."""
import copy
import hashlib
import json
import re
import threading
import time
import uuid
from urllib.parse import urlparse
import publishing
import service_connections as services
from web_sources import public_url,read_public

LOCK=threading.RLock()
PLANS={}
BUSY=set()

def fingerprint(config):return hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()

def destination(config,post):
    account=config.get('r2_account_id','');bucket=config.get('bucket','');base=config.get('public_base','').rstrip('/')
    if not re.fullmatch(r'[a-f0-9]{32}',account):raise ValueError('Inserisci l’Account ID Cloudflare R2 di 32 caratteri.')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,61}[a-z0-9]',bucket):raise ValueError('Nome del bucket R2 non valido.')
    u=urlparse(base)
    if u.scheme!='https' or not u.hostname or u.path not in ('','/') or u.params or u.query or u.fragment:raise ValueError('Inserisci l’origine HTTPS pubblica del bucket, senza percorso o parametri.')
    public_url(base)
    key=f'avatar-studio/{post["job_id"]}/{post["media_sha256"]}.mp4'
    return {'endpoint':'https://'+account+'.r2.cloudflarestorage.com','bucket':bucket,'key':key,'url':base+'/'+key}

def plan(data):
    with publishing.LOCK:post=copy.deepcopy(publishing.find(publishing.load(),data.get('id')))
    if post['platform']!='instagram' or post['state'] not in ('draft','approved','missed'):raise ValueError('Prepara prima un post Instagram non ancora inviato.')
    config=services.config('r2');missing=[];dest=None
    if post['media_bytes']>150_000_000:missing.append('Questo uploader accetta file fino a 150 MB. Prepara una clip più breve.')
    try:dest=destination(config,post)
    except ValueError as exc:missing.append(str(exc))
    if not services.secret('r2','access_key_id') or not services.secret('r2','secret_access_key'):missing.append('Credenziali R2 da collegare.')
    quote={'id':uuid.uuid4().hex[:24],'post_id':post['id'],'revision':post['revision'],'media_sha256':post['media_sha256'],'bytes':post['media_bytes'],
           'destination':dest,'config_digest':fingerprint(config),'missing':missing,'expires':time.time()+600,
           'note':'Il file sarà accessibile tramite l’URL pubblico del tuo bucket. Nessun Reel viene pubblicato da questo comando. Costi dello storage secondo il tuo piano, separati dal budget delle generazioni.'}
    with LOCK:
        for key in list(PLANS):
            if PLANS[key]['expires']<time.time():PLANS.pop(key)
        if len(PLANS)>=100:PLANS.pop(next(iter(PLANS)))
        PLANS[quote['id']]=quote
    return quote

def client(config):
    try:
        import boto3
        from botocore.config import Config
    except ImportError:raise ValueError('Client storage assente: esegui Prepara Mac.command per installare boto3.') from None
    return boto3.client('s3',endpoint_url='https://'+config['r2_account_id']+'.r2.cloudflarestorage.com',
        aws_access_key_id=services.secret('r2','access_key_id'),aws_secret_access_key=services.secret('r2','secret_access_key'),region_name='auto',
        config=Config(signature_version='s3v4',connect_timeout=15,read_timeout=120,retries={'max_attempts':0},s3={'addressing_style':'path'}))

def upload(data):
    if data.get('confirmed') is not True:raise ValueError('Conferma il caricamento del file sul tuo storage pubblico.')
    with LOCK:
        quote=PLANS.pop(data.get('plan_id'),None)
        if not quote or quote['expires']<time.time():raise ValueError('Piano scaduto: preparane uno nuovo.')
        if quote['missing']:raise ValueError('Completa i collegamenti R2 prima dell’invio.')
        if quote['post_id'] in BUSY:raise ValueError('Un caricamento per questo post è già in corso.')
        BUSY.add(quote['post_id'])
    try:
        with services.bound('r2'):
            config=services.config('r2')
            if fingerprint(config)!=quote['config_digest']:raise ValueError('Destinazione modificata: prepara un nuovo piano.')
            with publishing.LOCK:
                post=copy.deepcopy(publishing.find(publishing.load(),quote['post_id']))
                if post['revision']!=quote['revision'] or post['state'] not in ('draft','approved','missed'):raise ValueError('Post modificato: prepara un nuovo piano.')
                path=publishing.file(post)
                if publishing.sha(path)!=quote['media_sha256']:raise ValueError('File modificato dopo il piano di caricamento.')
            target=quote['destination'];s3=client(config);exists=False
            try:
                meta=s3.head_object(Bucket=target['bucket'],Key=target['key'])
                if meta.get('Metadata',{}).get('sha256')!=quote['media_sha256'] or meta.get('ContentLength')!=quote['bytes']:raise ValueError('Oggetto remoto con metadati diversi: non viene sovrascritto.')
                exists=True
            except ValueError:raise
            except Exception as exc:
                if str(getattr(exc,'response',{}).get('Error',{}).get('Code')) not in ('404','NoSuchKey','NotFound'):raise ValueError('Impossibile verificare R2: controlla permessi e stato del bucket.') from None
            if not exists:
                try:
                    with path.open('rb') as body:s3.put_object(Bucket=target['bucket'],Key=target['key'],Body=body,ContentLength=quote['bytes'],ContentType='video/mp4',Metadata={'sha256':quote['media_sha256']},IfNoneMatch='*')
                except Exception:raise ValueError('Esito del caricamento incerto. Preparando di nuovo il piano verrà controllato lo stesso oggetto, senza creare una nuova copia.') from None
            raw,_,_=read_public(target['url'],maximum=150_000_000)
            if hashlib.sha256(raw).hexdigest()!=quote['media_sha256']:raise ValueError('File caricato, ma l’URL pubblico non restituisce ancora il file corretto. Verifica il dominio R2 e ripeti il controllo.')
            # Save is optimistic: a concurrent edit must not receive the old URL/approval.
            saved=publishing.save({**post,'source_url':target['url']})
            return {'post_id':saved['id'],'url':target['url'],'reused':exists,'message':'File disponibile. Il post torna da revisionare: controlla e approva prima della pubblicazione.'}
    finally:
        with LOCK:BUSY.discard(quote['post_id'])

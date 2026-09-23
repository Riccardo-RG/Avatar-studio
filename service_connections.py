"""Session-only credentials and Google desktop OAuth. Public config contains no secrets."""
from contextlib import contextmanager
from contextvars import ContextVar
import uuid
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import providers
import runtime_config

ROOT=Path(__file__).resolve().parent
PATH=ROOT/'data/connections.json'
LOCK=threading.RLock()
VAULT={}
DISCONNECTED=set()
PENDING={}
SOCIAL=('youtube','tiktok','instagram')
OPERATIONS=set()
BOUND=ContextVar('connection_profile',default=None)
SERVICES=('youtube','tiktok','instagram','obs','tavus','r2')
SECRET_FIELDS={'access_token','refresh_token','client_secret','api_key','password','access_key_id','secret_access_key'}
PUBLIC_FIELDS={'nickname','client_id','account_id','label','api_version','port','face_id','pal_id','eur_minute','r2_account_id','bucket','public_base'}
HOSTS={'www.googleapis.com','youtube.googleapis.com','youtubeanalytics.googleapis.com','oauth2.googleapis.com','open.tiktokapis.com','open-upload.tiktokapis.com','graph.facebook.com','tavusapi.com'}

class RemoteError(ValueError):pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def checked_url(url,hosts=HOSTS):
    u=urllib.parse.urlparse(url)
    if u.scheme!='https' or u.hostname not in hosts or u.username or u.password or u.port not in (None,443):
        raise ValueError('Destinazione del servizio non consentita.')
    return url

def http(url,method='GET',body=None,headers=None,allowed=(200,201,202,204)):
    checked_url(url)
    headers=dict(headers or {})
    if isinstance(body,dict):body=json.dumps(body).encode();headers.setdefault('Content-Type','application/json')
    req=urllib.request.Request(url,data=body,headers=headers,method=method)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),urllib.request.HTTPSHandler(context=runtime_config.ssl_context()))
    try:
        try:response=opener.open(req,timeout=90)
        except urllib.error.HTTPError as exc:
            if exc.code not in allowed:raise RemoteError(f'Il servizio ha risposto HTTP {exc.code}. Verifica permessi, quota e stato remoto prima di riprovare.') from None
            response=exc
        with response:
            raw=response.read(2_000_001)
            if len(raw)>2_000_000:raise RemoteError('Risposta del servizio troppo grande.')
            if response.status not in allowed:raise RemoteError('Risposta HTTP inattesa.')
            data=json.loads(raw) if raw else {}
            if isinstance(data,dict) and data.get('error') and (not isinstance(data['error'],dict) or data['error'].get('code') not in ('ok',0)):
                raise RemoteError('Il servizio ha rifiutato la richiesta. Verifica permessi e limiti nel suo pannello.')
            return data,dict(response.headers),response.status
    except RemoteError:raise
    except Exception:raise RemoteError('Connessione interrotta o risposta non valida. Lo stato remoto va verificato prima di reinviare.') from None

def load():
    doc=json.loads(PATH.read_text()) if PATH.exists() else {}
    for name in SERVICES:
        cfg=doc.setdefault(name,{})
        if name in SOCIAL and 'profiles' not in cfg:
            doc[name]={'active_profile':'default','profiles':[{'id':'default','nickname':'Principale','revision':0,**{k:v for k,v in cfg.items() if k in PUBLIC_FIELDS or k=='verified'}}]}
    doc['version']=2
    return doc


def selected(doc,name,profile_id=None):
    if name not in SERVICES:raise ValueError('Servizio non valido.')
    if name not in SOCIAL:return doc[name]
    binding=BOUND.get()
    identity=profile_id or (binding[1] if binding and binding[0]==name else doc[name]['active_profile'])
    profile=next((p for p in doc[name]['profiles'] if p['id']==identity),None)
    if not profile:raise ValueError('Account salvato non disponibile: scegline uno dalla piattaforma corretta.')
    return profile


def config(name,profile_id=None):
    with LOCK:return copy.deepcopy(selected(load(),name,profile_id))


def key_for(name,profile_id=None):
    if name not in SOCIAL:return name
    identity=config(name,profile_id)['id']
    return name if identity=='default' else name+':'+identity


@contextmanager
def bound(name,profile_id=None):
    # The default in this scope is pinned to this profile, never the UI switch.
    # Edits/disconnect are blocked while its verified credentials are in use.
    with LOCK:
        identity=config(name,profile_id).get('id');binding=(name,identity);key=key_for(name,identity)
        nested=BOUND.get()==binding
        if not nested:
            if key in OPERATIONS:raise ValueError('Questo account sta completando un’operazione. Riprova fra poco.')
            OPERATIONS.add(key)
        token=BOUND.set(binding)
    try:yield identity
    finally:
        with LOCK:
            BOUND.reset(token)
            if not nested:OPERATIONS.discard(key)


def editable(name,identity=None):
    if key_for(name,identity) in OPERATIONS:raise ValueError('Questo account è in uso: attendi la fine dell’operazione prima di modificarlo o scollegarlo.')


def create_profile(data):
    name=data.get('service');nickname=data.get('nickname','')
    if name not in SOCIAL or not isinstance(nickname,str) or not 1<=len(nickname.strip())<=60:raise ValueError('Scegli una piattaforma social e un nome account da 1 a 60 caratteri.')
    with LOCK:
        doc=load();group=doc[name]
        if len(group['profiles'])>=20:raise ValueError('Sono disponibili fino a 20 account per piattaforma.')
        identity=uuid.uuid4().hex[:12]
        group['profiles'].append({'id':identity,'nickname':nickname.strip(),'revision':0})
        group['active_profile']=identity;providers.atomic_json(PATH,doc)
    return snapshot()


def switch_profile(data):
    name=data.get('service')
    if name not in SOCIAL:raise ValueError('Scegli una piattaforma social.')
    with LOCK:
        doc=load();profile=selected(doc,name,data.get('profile_id'))
        doc[name]['active_profile']=profile['id'];providers.atomic_json(PATH,doc)
    return snapshot()


def save(data):
    name=data.get('service')
    if name not in SERVICES:raise ValueError('Servizio non valido.')
    with LOCK:
        doc=load();cfg=selected(doc,name,data.get('profile_id'));identity=cfg.get('id');editable(name,identity)
        updates={};credentials={}
        for k,v in data.items():
            if k in SECRET_FIELDS:
                if not isinstance(v,str) or len(v)>6000:raise ValueError('Credenziale non valida.')
                if v.strip():credentials[k]=v.strip()
            elif k in PUBLIC_FIELDS:
                if not isinstance(v,(str,int,float)) or len(str(v))>250:raise ValueError('Configurazione non valida.')
                updates[k]=str(v).strip()
        if 'nickname' in updates and not 1<=len(updates['nickname'])<=60:raise ValueError('Nome account richiesto, massimo 60 caratteri.')
        if not re.fullmatch(r'v\d{2}\.0',updates.get('api_version',cfg.get('api_version','v25.0'))):raise ValueError('Versione Meta non valida, esempio v25.0.')
        changed=any(cfg.get(k)!=v for k,v in updates.items() if k!='nickname') or bool(credentials)
        cfg.update(updates)
        if changed:cfg.pop('verified',None)
        cfg['revision']=cfg.get('revision',0)+1
        providers.atomic_json(PATH,doc)
        key=key_for(name,identity);account=VAULT.setdefault(key,{})
        if 'access_token' in credentials:
            # A pasted replacement has its own unknown expiry and identity.
            # Never refresh it with the token from a previous OAuth session.
            account.pop('expires_at',None)
            if 'refresh_token' not in credentials:account['refresh_token']=''
        account.update(credentials);DISCONNECTED.discard(key)
    return snapshot()


def disconnect(name,profile_id=None):
    if name not in SERVICES:raise ValueError('Servizio non valido.')
    with LOCK:
        doc=load();cfg=selected(doc,name,profile_id);identity=cfg.get('id');editable(name,identity)
        key=key_for(name,identity);VAULT.pop(key,None);DISCONNECTED.add(key);cfg.pop('verified',None);cfg['revision']=cfg.get('revision',0)+1;providers.atomic_json(PATH,doc)
    return snapshot()


def secret(name,key,profile_id=None):
    with LOCK:
        storage_key=key_for(name,profile_id)
        if storage_key in DISCONNECTED:return ''
        # Existing environment variables belong only to the migrated default profile.
        account=VAULT.get(storage_key,{})
        return account[key] if key in account else (os.environ.get('AVATAR_'+name.upper()+'_'+key.upper(),'') if storage_key==name else '')


def profile_snapshot(name,profile_id=None):
    cfg=config(name,profile_id);identity=cfg.get('id')
    cfg['connected']=bool(secret(name,'access_token',identity) or secret(name,'api_key',identity) or (name=='obs' and secret(name,'password')) or (name=='r2' and secret(name,'access_key_id') and secret(name,'secret_access_key')))
    cfg['has_client_secret']=bool(secret(name,'client_secret',identity))
    if not cfg['connected']:cfg.pop('verified',None)
    return cfg


def snapshot():
    with LOCK:
        doc=load();result={}
        for name in SERVICES:
            result[name]=profile_snapshot(name,doc[name]["active_profile"] if name in SOCIAL else None)
            if name in SOCIAL:
                result[name]['active_profile']=doc[name]['active_profile']
                result[name]['profiles']=[profile_snapshot(name,p['id']) for p in doc[name]['profiles']]
        return result


def token(name,profile_id=None):
    with LOCK:
        identity=config(name,profile_id).get('id');key=key_for(name,identity);account=copy.deepcopy(VAULT.get(key,{}));cfg=config(name,identity)
        refresh=name=='youtube' and account.get('expires_at',10**15)<time.time()+90 and bool(secret(name,'refresh_token',identity))
        if refresh:form={'client_id':cfg.get('client_id',''),'client_secret':secret(name,'client_secret',identity),'refresh_token':secret(name,'refresh_token',identity),'grant_type':'refresh_token'}
    if refresh:
        # Other accounts remain switchable while this provider answers.
        answer,_,_=http('https://oauth2.googleapis.com/token','POST',urllib.parse.urlencode(form).encode(),{'Content-Type':'application/x-www-form-urlencoded'})
        with LOCK:
            if key in DISCONNECTED or config(name,identity).get('revision',0)!=cfg.get('revision',0):raise ValueError('Credenziali modificate durante il rinnovo. Riprova con il profilo aggiornato.')
            account.update(access_token=answer['access_token'],expires_at=time.time()+answer.get('expires_in',3600));VAULT[key]=account
    value=secret(name,'access_token',identity)
    if not value:raise ValueError('Collega '+name+' · '+cfg.get('nickname','account')+' nella sezione Collegamenti.')
    return value


def auth(name,profile_id=None):return {'Authorization':'Bearer '+token(name,profile_id)}


def verify(name,profile_id=None):
    with bound(name,profile_id) as profile_id:
        cfg=config(name,profile_id)
        if name=='youtube':
            r,_,_=http('https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true',headers=auth(name,profile_id));items=r.get('items',[])
            if len(items)!=1:raise ValueError('Non è stato trovato un solo canale YouTube. Verifica il canale scelto durante il login.')
            identity,label=items[0]['id'],items[0]['snippet']['title']
        elif name=='tiktok':
            r,_,_=http('https://open.tiktokapis.com/v2/user/info/?fields=open_id,display_name',headers=auth(name,profile_id));u=r['data']['user'];identity,label=u['open_id'],u['display_name']
        elif name=='instagram':
            identity=cfg.get('account_id','')
            if not identity.isdigit():raise ValueError('Inserisci l’ID dell’account Instagram professionale.')
            r,_,_=http(f'https://graph.facebook.com/{cfg.get("api_version","v25.0")}/{identity}?fields=id,username',headers=auth(name,profile_id));identity,label=r['id'],r['username']
        else:raise ValueError('Per questo servizio usa il controllo dedicato alla diretta.')
        if not re.fullmatch(r'[\w-]{2,200}',identity):raise ValueError('Identità del servizio non valida.')
        with LOCK:
            doc=load();selected(doc,name,profile_id).update(account_id=identity,label=label,verified=time.time());providers.atomic_json(PATH,doc)
        return {'profile_id':profile_id,'account_id':identity,'label':label}


def oauth_start(base,profile_id=None,*,analytics=False,revenue=False):
    if type(analytics) is not bool or type(revenue) is not bool:
        raise ValueError('Scegli esplicitamente i permessi Analytics e ricavi.')
    if revenue and not analytics:
        raise ValueError('Per leggere i ricavi abilita anche YouTube Analytics.')
    scopes=['https://www.googleapis.com/auth/youtube.upload','https://www.googleapis.com/auth/youtube.readonly']
    if analytics:scopes.append('https://www.googleapis.com/auth/yt-analytics.readonly')
    if revenue:scopes.append('https://www.googleapis.com/auth/yt-analytics-monetary.readonly')
    with LOCK:
        cfg=config('youtube',profile_id)
        if not cfg.get('client_id'):raise ValueError('Inserisci prima il client ID OAuth Google di tipo Desktop per questo account.')
        state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(64);redirect=base+'/oauth/youtube/callback'
        for key in list(PENDING):
            if PENDING[key]['expires']<time.time():PENDING.pop(key)
        if len(PENDING)>=20:raise ValueError('Completa o attendi la scadenza dei login già aperti.')
        PENDING[state]={'verifier':verifier,'redirect':redirect,'expires':time.time()+600,'profile_id':cfg['id'],'revision':cfg.get('revision',0)}
    fields={'client_id':cfg['client_id'],'redirect_uri':redirect,'response_type':'code','scope':' '.join(scopes),'access_type':'offline','prompt':'select_account consent','state':state,'code_challenge':base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='),'code_challenge_method':'S256'}
    return {'url':'https://accounts.google.com/o/oauth2/v2/auth?'+urllib.parse.urlencode(fields),'profile_id':cfg['id']}


def oauth_finish(query):
    fields=urllib.parse.parse_qs(query);state=fields.get('state',[''])[0]
    with LOCK:pending=PENDING.pop(state,None)
    if not pending or pending['expires']<time.time():raise ValueError('Login scaduto o stato OAuth non valido. Riparti dallo studio.')
    if fields.get('error'):raise ValueError('Accesso Google non autorizzato.')
    code=fields.get('code',[''])[0]
    if not code:raise ValueError('Codice OAuth mancante.')
    with bound('youtube',pending['profile_id']) as identity:
        cfg=config('youtube',identity)
        if cfg.get('revision',0)!=pending['revision']:raise ValueError('Il profilo è cambiato durante il login. Riparti dallo studio.')
        form={'code':code,'client_id':cfg['client_id'],'client_secret':secret('youtube','client_secret',identity),'redirect_uri':pending['redirect'],'grant_type':'authorization_code','code_verifier':pending['verifier']}
        r,_,_=http('https://oauth2.googleapis.com/token','POST',urllib.parse.urlencode(form).encode(),{'Content-Type':'application/x-www-form-urlencoded'})
        with LOCK:
            key=key_for('youtube',identity);DISCONNECTED.discard(key);VAULT.setdefault(key,{}).update(access_token=r['access_token'],refresh_token=r.get('refresh_token',''),expires_at=time.time()+r.get('expires_in',3600))
        return verify('youtube',identity)

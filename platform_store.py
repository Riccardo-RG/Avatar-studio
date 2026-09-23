"""Versioned characters, campaigns and a conservative EUR reservation ledger."""
import copy
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import threading
import time
import uuid
import providers
import languages

ROOT = Path(__file__).resolve().parent
PATH = ROOT / 'data/platform.json'
LOCK = threading.RLock()
APPEARANCE_FIELDS = ('name', 'color', 'background', 'accent', 'voice', 'rate')

def editorial_defaults(character):
    return dict(concept=character['personality'][:400], tone='Chiaro, curioso e amichevole. Parla in italiano.',
                audience='Un pubblico italiano interessato al tema del contenuto.',
                boundaries='Distingui fatti, opinioni e storie inventate. Non inventare esperienze personali.',
                signature='Una domanda o uno spunto pratico per chi guarda.')

def text(value, maximum=400, required=False):
    if not isinstance(value, str) or len(value.strip()) > maximum or (required and not value.strip()):
        raise ValueError('Testo vuoto o troppo lungo.')
    return value.strip()

def number(value, low=0, high=10000):
    n = float(value)
    if not math.isfinite(n) or not low <= n <= high:
        raise ValueError('Valore numerico fuori intervallo.')
    return n

def fresh():
    base = dict(revision=1, voice='piper:paola', rate=160, color='#d6dce5', background='#162226', personality='Curioso, chiaro e amichevole. Parla in italiano.', rights='original', rights_note='Personaggio originale creato per Avatar Studio.', history=[], mouth_x=.51, mouth_y=.45, mouth_width=.14)
    return {'version': 1, 'budget_eur': 30, 'reservations': [], 'characters': [
        dict(base, id='nova', name='Nova', kind='robot', image='', accent='#b4fa86'),
        dict(base, id='ari', name='Ari', kind='realistic', image='/characters/ari.png', accent='#92d7fa'),
        dict(base, id='lumo', name='Lumo', kind='illustrated', image='/characters/lumo.png', accent='#c5b8ff'),
    ], 'campaigns': [], 'prices': {'heygen_eur_minute': 0, 'brave_eur_query': 0}, 'active_character': 'nova'}

def load():
    with LOCK:
        if not PATH.exists():
            PATH.parent.mkdir(exist_ok=True, parents=True)
            providers.atomic_json(PATH, fresh())
        doc = json.loads(PATH.read_text())
        if doc.get('version', 1) < 2:
            # Preserve the old robot colours; other identities keep their own names and voices.
            legacy = providers.settings()
            editorial_path = PATH.parent / 'studio.json'
            legacy_persona = json.loads(editorial_path.read_text()).get('persona', {}) if editorial_path.exists() else {}
            for c in doc['characters']:
                c.setdefault('color', legacy['color'] if c['kind'] == 'robot' else '#d6dce5')
                c.setdefault('background', legacy['background'])
                c.setdefault('editorial', {**editorial_defaults(c), **(legacy_persona if c['id'] == 'nova' else {})})
            doc['version'] = 2
            write(doc)
        return doc

def write(doc):
    providers.atomic_json(PATH, doc)

def find(doc, collection, identity):
    for item in doc[collection]:
        if item['id'] == identity:
            return item
    raise ValueError('Elemento non trovato.')

def snapshot(identity=None):
    doc = load()
    character = find(doc, 'characters', identity or doc['active_character'])
    return {k:v for k,v in character.items() if k != 'history'}

def render_settings(config, identity=None):
    c = snapshot(identity)
    return {**config, 'character': c, **{k:c[k] for k in APPEARANCE_FIELDS}}

def save_character(data, voices):
    with LOCK:
        doc = load()
        old = find(doc, 'characters', data['id']) if data.get('id') else None
        if old and data.get('revision') != old['revision']:
            raise ValueError('Personaggio modificato in un’altra scheda. Ricarica prima di salvare.')
        item = {**(old or fresh()['characters'][0]), **{k:v for k,v in data.items() if k in (*APPEARANCE_FIELDS,'voices_by_language','kind','image','personality','editorial','tavus_face_id','tavus_pal_id','rights','rights_note','mouth_x','mouth_y','mouth_width')}}
        item['name'] = text(item['name'],24,True)
        item['personality'] = text(item['personality'],1200,True)
        item['rights_note'] = text(item['rights_note'],400)
        if item['kind'] not in ('robot','realistic','illustrated','photo') or item['voice'] not in voices:
            raise ValueError('Tipo di personaggio o voce non disponibile.')
        for key in ('accent', 'color', 'background'):
            if not isinstance(item[key], str) or not re.fullmatch(r'#[a-fA-F0-9]{6}',item[key]): raise ValueError('Colore non valido.')
        editorial = item.get('editorial', editorial_defaults(item))
        if not isinstance(editorial, dict): raise ValueError('Personalità editoriale non valida.')
        item['editorial'] = {k:text(editorial.get(k,v),400,True) for k,v in editorial_defaults(item).items()}
        for key in ('tavus_face_id', 'tavus_pal_id'):
            item[key] = text(item.get(key,''),100)
            if item[key] and not re.fullmatch(r'[A-Za-z0-9_-]{2,100}',item[key]): raise ValueError('ID Tavus non valido.')
        if item['rights'] not in ('original','own','permission'): raise ValueError('Indica l’origine del personaggio.')
        if item['kind'] == 'photo' and (item['rights'] not in ('own','permission') or not item['rights_note']):
            raise ValueError('Per una persona reale indica foto propria o autorizzata e una nota sull’autorizzazione.')
        if item['kind'] != 'robot' and not asset_file(item['image']): raise ValueError('Carica prima un’immagine PNG o JPEG.')
        import media
        if not any(v['id']==item['voice'] and v['language']=='it' for v in media.voice_catalog()):raise ValueError('Per la voce italiana abituale scegli una voce italiana. Le altre lingue hanno campi dedicati.')
        mapping=copy.deepcopy(item.get('voices_by_language',{}))
        if not isinstance(mapping,dict) or any(k not in languages.LANGUAGES for k in mapping):raise ValueError('Voci del personaggio non valide.')
        for lang in ('en','es'):
            value=data.get('voice_'+lang,mapping.get(lang,''))
            if value:
                import media
                if value not in voices or not any(v['id']==value and v['language']==lang for v in media.voice_catalog()):raise ValueError('Voce non disponibile per '+languages.LANGUAGES[lang])
                mapping[lang]=value
            else:
                mapping.pop(lang,None)
        mapping['it']=item['voice'];item['voices_by_language']=mapping
        item['rate'] = int(number(item['rate'],110,210))
        for key,low,high in [('mouth_x',.1,.9),('mouth_y',.1,.9),('mouth_width',.03,.4)]: item[key]=number(item[key],low,high)
        item['id'] = old['id'] if old else uuid.uuid4().hex[:12]
        history = copy.deepcopy(old.get('history',[])) if old else []
        if old: history.append({k:v for k,v in old.items() if k!='history'})
        item.update(revision=(old['revision'] if old else 0)+1, history=history[-30:], updated=time.time())
        if old: doc['characters'][doc['characters'].index(old)]=item
        else: doc['characters'].append(item)
        write(doc)
        return item

def activate(identity):
    with LOCK:
        doc=load(); find(doc,'characters',identity); doc['active_character']=identity; write(doc)
        return snapshot(identity)

def asset_file(url):
    if url in ('/characters/ari.png','/characters/lumo.png'): return ROOT/'static'/url.lstrip('/')
    if isinstance(url,str) and re.fullmatch(r'/character-assets/[a-f0-9]{24}\.png',url):
        p=ROOT/'data/character-assets'/url.rsplit('/',1)[-1]
        return p if p.is_file() else None
    return None

def upload_png(raw):
    # Browser decodes/re-encodes JPEG/PNG before uploading, stripping metadata.
    if not 33 <= len(raw) <= 6_000_000 or raw[:8] != b'\x89PNG\r\n\x1a\n' or raw[12:16]!=b'IHDR':
        raise ValueError('Immagine non valida: usa PNG/JPEG fino a 6 MB.')
    width,height=struct.unpack('>II',raw[16:24])
    if not 128 <= width <= 4096 or not 128 <= height <= 4096: raise ValueError('Immagine: da 128 a 4096 pixel per lato.')
    name=hashlib.sha256(raw).hexdigest()[:24]+'.png'; folder=ROOT/'data/character-assets'; folder.mkdir(exist_ok=True)
    target=folder/name
    if not target.exists(): target.write_bytes(raw)
    return {'image':'/character-assets/'+name,'width':width,'height':height}

def save_campaign(data):
    with LOCK:
        doc=load(); old=find(doc,'campaigns',data['id']) if data.get('id') else None
        if old and data.get('revision')!=old['revision']: raise ValueError('Campagna modificata. Ricarica prima di salvare.')
        if old and any(r['status'] in ('running','queued') for r in old.get('runs',[])): raise ValueError('Attendi o ferma gli agenti prima di modificare il brief.')
        c=copy.deepcopy(old) if old else dict(id=uuid.uuid4().hex[:12],revision=0,sources=[],runs=[],metrics=[],contents=[],releases=[])
        for k,limit in [('name',100),('audience',500),('objective',700),('topic',500)]: c[k]=text(data.get(k,c.get(k,'')),limit,True)
        c['character_id']=data.get('character_id',c.get('character_id',doc['active_character']));find(doc,'characters',c['character_id'])
        channels=data.get('channels',c.get('channels',['youtube','tiktok','instagram']))
        if not isinstance(channels,list) or not channels or any(v not in ('youtube','tiktok','instagram','twitch') for v in channels): raise ValueError('Seleziona almeno un canale valido.')
        c['language']=languages.code(data.get('language',c.get('language','it')))
        import market_research
        editorial=providers.editorial_options({**c,**data})
        research=market_research.options({**c,**data,'language':c['language']})
        c.update(editorial,research_country=research['country'],research_queries=research['count'])
        c['channels']=list(dict.fromkeys(channels));c['budget_eur']=number(data.get('budget_eur',c.get('budget_eur',10)))
        c['revision']+=1;c['updated']=time.time()
        if old:doc['campaigns'][doc['campaigns'].index(old)]=c
        else:doc['campaigns'].append(c)
        write(doc);return c

def change_campaign(identity, mutation):
    with LOCK:
        doc=load(); c=find(doc,'campaigns',identity);result=mutation(c); c['updated']=time.time();write(doc);return result

def save_budget(data):
    with LOCK:
        doc=load();doc['budget_eur']=number(data.get('budget_eur',doc['budget_eur']))
        for key in doc['prices']:
            if key in data:doc['prices'][key]=number(data[key],0,1000)
        write(doc);return budget_summary(doc)

def budget_summary(doc=None):
    doc=doc or load();month=dt.date.today().strftime('%Y-%m');used=sum(r['amount_eur'] for r in doc['reservations'] if r['month']==month)
    return {'limit_eur':doc['budget_eur'],'reserved_eur':round(used,4),'remaining_eur':round(max(0,doc['budget_eur']-used),4),'prices':doc['prices']}

def reserve(service,amount,campaign_id='',reference=''):
    amount=number(amount,.000001,10000)
    with LOCK:
        doc=load();summary=budget_summary(doc)
        if amount>summary['remaining_eur']:raise ValueError('Richiesta oltre il budget mensile disponibile.')
        if campaign_id:
            c=find(doc,'campaigns',campaign_id);used=sum(r['amount_eur'] for r in doc['reservations'] if r.get('campaign_id')==campaign_id)
            if used+amount>c['budget_eur']:raise ValueError('Richiesta oltre il budget della campagna.')
        identity=uuid.uuid4().hex[:12]
        doc['reservations'].append(dict(id=identity,month=dt.date.today().strftime('%Y-%m'),service=service,amount_eur=round(amount,6),campaign_id=campaign_id,reference=reference,created=time.time()))
        write(doc);return identity

def metrics(data):
    record={'id':uuid.uuid4().hex[:12], 'label':text(data.get('label',''),100,True),'platform':data.get('platform'),'date':text(data.get('date',''),10,True)}
    if record['platform'] not in ('youtube','tiktok','instagram','twitch'):raise ValueError('Canale non valido.')
    dt.date.fromisoformat(record['date'])
    for k in ('views','clicks','leads'):record[k]=int(number(data.get(k,0),0,1e10))
    record['completion_percent']=number(data.get('completion_percent',0),0,100)
    record['cost_eur']=number(data.get('cost_eur',0),0,1e7)
    record['origin']='manual';record['created']=time.time()
    return change_campaign(data['campaign_id'],lambda c:(c['metrics'].append(record),record)[1])

def analyze(c):
    rows=c['metrics'];views=sum(r['views'] for r in rows); clicks=sum(r['clicks'] for r in rows);leads=sum(r['leads'] for r in rows);cost=sum(r['cost_eur'] for r in rows)
    return {'observations':len(rows),'views':views,'clicks':clicks,'leads':leads,'cost_eur':round(cost,2), 'ctr_percent':round(clicks/views*100,2) if views else None,'cost_per_lead':round(cost/leads,2) if leads else None,'note':'Dati inseriti manualmente. Confronta periodi e canali omogenei; questi dati non dimostrano causalità.' if rows else 'Nessun risultato reale inserito: non è possibile stabilire un vincitore.'}

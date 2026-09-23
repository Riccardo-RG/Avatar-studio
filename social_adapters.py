"""Official API adapters. No credentials or upload session URLs in public queue state."""
import hashlib
import re
import time
from urllib.parse import urlencode
import service_connections as services
from web_sources import read_public,public_url

UPLOADS={}

def identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r'[\w~.-]{2,180}',value):raise ValueError('Identificatore remoto non valido.')
    return value

def youtube_metadata(item):
    return {'snippet':{'title':item['title'][:100],'description':item['description'][:5000],'categoryId':'22',**({'defaultLanguage':item.get('language','it')} if item.get('language','it') else {})},
            'status':{'privacyStatus':item['visibility'],'selfDeclaredMadeForKids':item['made_for_kids'],'containsSyntheticMedia':True}}

def source_chunks(size):
    chunk=min(size,32_000_000);count=max(1,size//chunk)
    return {'source':'FILE_UPLOAD','video_size':size,'chunk_size':chunk,'total_chunk_count':count}

def preflight(item):
    errors=[];platform=item['platform']
    try:cfg=services.profile_snapshot(platform,item.get('connection_id','default'))
    except ValueError:return ['Account salvato non disponibile. Rivedi la destinazione del post.']
    if item.get('account_id') and cfg.get('account_id')!=item['account_id']:errors.append('Il profilo collegato non corrisponde all’account approvato.')
    if not cfg.get('connected'):errors.append('Account non collegato.')
    if not cfg.get('verified'):errors.append('Identità del canale ancora da verificare.')
    if platform=='youtube' and item['visibility'] not in ('private','unlisted','public'):errors.append('Scegli la visibilità YouTube.')
    if platform=='tiktok' and item['visibility']!='inbox':errors.append('Questa edizione supporta le bozze TikTok da completare nell’app.')
    if platform=='instagram':
        if item['visibility']!='public':errors.append('La pubblicazione Instagram prevista è pubblica.')
        if not item.get('source_url'):errors.append('Instagram richiede un URL HTTPS pubblico del file preparato per il post.')
        else:
            try:
                public_url(item['source_url'])
                if not item['source_url'].startswith('https://'):errors.append('L’URL del video deve usare HTTPS.')
            except ValueError as exc:errors.append(str(exc))
        if item['duration']<3:errors.append('Il Reel deve durare almeno tre secondi.')
    return errors

def send(item,video,checkpoint,cancelled):
    platform=item['platform'];headers=services.auth(platform,item.get('connection_id','default'));size=video.stat().st_size
    def check():
        if cancelled():raise ValueError('Invio fermato: verifica lo stato remoto prima di riprendere.')
    check()
    if platform=='youtube':
        _,h,_=services.http('https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status&notifySubscribers=false','POST',youtube_metadata(item),{**headers,'X-Upload-Content-Length':str(size),'X-Upload-Content-Type':'video/mp4'})
        url=h.get('Location') or h.get('location');services.checked_url(url,{'www.googleapis.com','youtube.googleapis.com'})
        UPLOADS[item['id']]=url;checkpoint({'stage':'upload_session'})
        with video.open('rb') as f:
            offset=0
            while offset<size:
                check();raw=f.read(8*1024*1024)
                r,h,code=services.http(url,'PUT',raw,{**headers,'Content-Type':'video/mp4','Content-Range':f'bytes {offset}-{offset+len(raw)-1}/{size}'},allowed=(200,201,308))
                offset+=len(raw)
                if code==308 and (h.get('Range') or h.get('range'))!=f'bytes=0-{offset-1}':
                    raise services.RemoteError('YouTube ha confermato solo una parte del blocco: controlla lo stato della sessione.')
                if code!=308:
                    remote=identifier(r.get('id'))
                    checkpoint({'remote_id':remote,'stage':'uploaded'})
                    return {'state':'processing','remote_id':remote,'url':'https://www.youtube.com/watch?v='+remote,'message':'Caricato: verifica elaborazione e visibilità effettiva.'}
        raise services.RemoteError('YouTube non ha confermato il completamento del file.')
    if platform=='tiktok':
        source=source_chunks(size)
        r,_,_=services.http('https://open.tiktokapis.com/v2/post/publish/inbox/video/init/','POST',{'source_info':source},headers)
        remote=identifier(r['data']['publish_id']);url=r['data']['upload_url'];services.checked_url(url,{'open-upload.tiktokapis.com'})
        checkpoint({'remote_id':remote,'stage':'initialized'})
        with video.open('rb') as f:
            offset=0
            for index in range(source['total_chunk_count']):
                check();raw=f.read(size-offset if index==source['total_chunk_count']-1 else source['chunk_size'])
                services.http(url,'PUT',raw,{'Content-Type':'video/mp4','Content-Range':f'bytes {offset}-{offset+len(raw)-1}/{size}'},allowed=(200,201,202,204,206))
                offset+=len(raw)
        return {'state':'processing','remote_id':remote,'message':'Video inviato a TikTok: attendi la conferma della bozza.'}
    if platform=='instagram':
        # Bind approval to the same bytes even when Meta retrieves an externally hosted file.
        remote_file,_,_=read_public(item['source_url'],maximum=150_000_000)
        if hashlib.sha256(remote_file).hexdigest()!=item['media_sha256']:raise ValueError('L’URL pubblico non contiene lo stesso video approvato. Usa il file preparato per questo post.')
        check();cfg=services.config(platform,item.get('connection_id','default'));account=identifier(cfg['account_id']);version=cfg.get('api_version','v25.0')
        base='https://graph.facebook.com/'+version
        r,_,_=services.http(f'{base}/{account}/media','POST',{'media_type':'REELS','video_url':item['source_url'],'caption':item['description'],'share_to_feed':True},headers)
        container=identifier(r['id']);checkpoint({'container_id':container,'stage':'container'})
        return {'state':'processing','container_id':container,'message':'Container Instagram creato: il controllo stato completerà il post quando pronto.'}
    raise ValueError('Piattaforma non supportata.')

def reconcile(item,checkpoint,allow_publish=False):
    platform=item['platform'];headers=services.auth(platform,item.get('connection_id','default'))
    if platform=='youtube':
        remote=item.get('remote_id')
        if not remote:
            url=UPLOADS.get(item['id'])
            if not url:raise ValueError('Sessione di upload non disponibile. Controlla YouTube Studio; non verrà creato un secondo video.')
            r,_,code=services.http(url,'PUT',b'',{**headers,'Content-Range':f'bytes */{item["media_bytes"]}'},allowed=(200,201,308))
            if code==308:return {'state':'uncertain','message':'Upload incompleto: nessun nuovo video viene inviato automaticamente.'}
            remote=identifier(r['id']);checkpoint({'remote_id':remote})
        r,_,_=services.http('https://www.googleapis.com/youtube/v3/videos?'+urlencode({'part':'status,processingDetails','id':remote}),headers=headers)
        if not r.get('items'):raise ValueError('Video non trovato: controlla il canale e i permessi.')
        data=r['items'][0];state=data.get('status',{});processing=data.get('processingDetails',{}).get('processingStatus')
        if state.get('uploadStatus') in ('failed','rejected','deleted') or processing=='failed':return {'state':'failed','remote_id':remote,'message':'YouTube ha segnalato un errore o rifiuto. Controlla YouTube Studio.'}
        if state.get('uploadStatus')=='processed' or processing=='succeeded':
            actual=state.get('privacyStatus');names={'private':'privato','unlisted':'non in elenco','public':'pubblico'}
            message='Elaborazione conclusa. Visibilità effettiva: '+names.get(actual,'non restituita dal servizio')+'.'
            if actual and actual!=item['visibility']:message+=' Era stato richiesto '+names.get(item['visibility'],item['visibility'])+': verifica YouTube Studio e le autorizzazioni del progetto API.'
            return {'state':'published','remote_id':remote,'actual_visibility':actual,'url':'https://www.youtube.com/watch?v='+remote,'message':message}
        return {'state':'processing','remote_id':remote,'message':'YouTube sta elaborando il video.'}
    if platform=='tiktok':
        r,_,_=services.http('https://open.tiktokapis.com/v2/post/publish/status/fetch/','POST',{'publish_id':identifier(item['remote_id'])},headers);d=r['data'];state=d['status']
        if state=='PUBLISH_COMPLETE':return {'state':'published','post_ids':d.get('publicaly_available_post_id',[]),'message':'TikTok conferma la pubblicazione completata nell’app.'}
        if state=='SEND_TO_USER_INBOX':return {'state':'handed_off','message':'Bozza nella posta TikTok. Aprila nell’app, controlla testo, visibilità ed etichetta AI, poi pubblica.'}
        if state=='FAILED':return {'state':'failed','message':'TikTok ha segnalato un errore. Controlla app, limiti e permessi.'}
        return {'state':'processing','message':'TikTok sta elaborando il file.'}
    if platform=='instagram':
        cfg=services.config(platform,item.get('connection_id','default'));base='https://graph.facebook.com/'+cfg.get('api_version','v25.0')
        if item.get('remote_id'):
            r,_,_=services.http(f'{base}/{identifier(item["remote_id"])}?fields=id,permalink',headers=headers)
            return {'state':'published','url':r.get('permalink',''),'message':'Post Instagram confermato.'}
        r,_,_=services.http(f'{base}/{identifier(item["container_id"])}?fields=status_code,status',headers=headers)
        if r.get('status_code') in ('ERROR','EXPIRED'):return {'state':'failed','message':'Container Instagram scaduto o non valido.'}
        if r.get('status_code')=='PUBLISHED':return {'state':'uncertain','message':'Container già pubblicato. Recupera l’ID dal profilo; non reinviare.'}
        if r.get('status_code')=='FINISHED' and allow_publish:
            # Persist intent BEFORE the non-idempotent API call.
            checkpoint({'stage':'publish_requested'})
            answer,_,_=services.http(f'{base}/{identifier(cfg["account_id"])}/media_publish','POST',{'creation_id':item['container_id']},headers)
            remote=identifier(answer['id']);checkpoint({'remote_id':remote,'stage':'published'})
            return {'state':'published','remote_id':remote,'message':'Pubblicato su Instagram.'}
        return {'state':'processing','message':'Instagram: container pronto' if r.get('status_code')=='FINISHED' else 'Instagram sta elaborando il file.'}
    raise ValueError('Piattaforma non supportata.')

def metrics(item):
    platform=item['platform'];headers=services.auth(platform,item.get('connection_id','default'))
    if platform=='youtube':
        r,_,_=services.http('https://www.googleapis.com/youtube/v3/videos?'+urlencode({'part':'statistics','id':identifier(item['remote_id'])}),headers=headers)
        if not r.get('items'):raise ValueError('Metriche non ancora disponibili.')
        source=r['items'][0].get('statistics',{});mapping={'views':'viewCount','likes':'likeCount','comments':'commentCount'}
    elif platform=='tiktok':
        ids=list(dict.fromkeys(str(value) for value in item.get('post_ids',[])))
        if not ids:raise ValueError('TikTok non ha ancora restituito gli ID pubblici. Le metriche non sono disponibili per una bozza.')
        if len(ids)>1:raise ValueError('Questa bozza ha generato più post TikTok. Consulta i risultati dei singoli post in TikTok: lo studio non li confonde in un unico contatore.')
        identifier(ids[0])
        r,_,_=services.http('https://open.tiktokapis.com/v2/video/query/?fields=id,view_count,like_count,comment_count,share_count','POST',{'filters':{'video_ids':ids}},headers)
        videos=r.get('data',{}).get('videos',[])
        source=next((video for video in videos if str(video.get('id'))==ids[0]),None)
        if source is None:raise ValueError('Metriche del post richiesto non disponibili con i permessi attuali.')
        mapping={'views':'view_count','likes':'like_count','comments':'comment_count','shares':'share_count'}
    else:
        cfg=services.config(platform,item.get('connection_id','default'));remote=identifier(item['remote_id']);base='https://graph.facebook.com/'+cfg.get('api_version','v25.0')
        r,_,_=services.http(f'{base}/{remote}?fields=like_count,comments_count',headers=headers)
        source=r;mapping={'likes':'like_count','comments':'comments_count'}
    return {'at':time.time(),'platform':platform,'scope':'Contatori cumulativi del singolo post; le metriche assenti non valgono zero.',
            'values':{key:int(source[value]) if value in source else None for key,value in mapping.items()}}

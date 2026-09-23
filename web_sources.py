"""Bounded public-web retrieval. No cookies, local addresses, or executable content."""
import datetime as dt
import html
from html.parser import HTMLParser
import http.client
import ipaddress
import json
import os
import socket
import ssl
from urllib.parse import urlsplit, urljoin, urlencode
import platform_store as store
import runtime_config

def public_url(url):
    if not isinstance(url,str) or len(url)>2000:raise ValueError('URL non valido.')
    p=urlsplit(url)
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or p.port not in (None,80,443):
        raise ValueError('Usa un indirizzo web pubblico HTTP/HTTPS.')
    return p

def read_public(url, maximum=1_500_000, redirects=3):
    for turn in range(redirects+1):
        p=public_url(url);port=p.port or (443 if p.scheme=='https' else 80)
        addresses=socket.getaddrinfo(p.hostname,port,type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):raise ValueError('Sono consentite solo fonti web pubbliche.')
        target=addresses[0][4][0]
        connection=http.client.HTTPSConnection(p.hostname,port,timeout=15,context=runtime_config.ssl_context()) if p.scheme=='https' else http.client.HTTPConnection(p.hostname,port,timeout=15)
        # Pin the checked IP while retaining HTTPS certificate/SNI hostname checks.
        connection._create_connection=lambda address,timeout=15,source_address=None,ip=target,port=port:socket.create_connection((ip,port),timeout,source_address)
        try:
            connection.request('GET',(p.path or '/')+('?' + p.query if p.query else ''),headers={'User-Agent':'AvatarStudioResearch/1.0','Accept':'text/html,text/plain,application/json','Accept-Encoding':'identity'})
            response=connection.getresponse()
            if response.status in (301,302,303,307,308):
                url=urljoin(url,response.getheader('Location',''));continue
            if response.status!=200:raise ValueError('La fonte ha risposto HTTP '+str(response.status)+'.')
            body=response.read(maximum+1)
            if len(body)>maximum:raise ValueError('Fonte troppo grande per questa lettura.')
            return body,response.getheader('Content-Type',''),url
        finally:connection.close()
    raise ValueError('Troppi reindirizzamenti nella fonte.')

class Extract(HTMLParser):
    def __init__(self):super().__init__();self.hidden=0;self.title=False;self.titles=[];self.parts=[];self.main=0;self.main_parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','noscript','svg','nav','header','footer'):self.hidden+=1
        if tag in ('main','article'):self.main+=1
        if tag=='title':self.title=True
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript','svg','nav','header','footer'):self.hidden=max(0,self.hidden-1)
        if tag in ('main','article'):self.main=max(0,self.main-1)
        if tag=='title':self.title=False
    def handle_data(self,data):
        if self.title:self.titles.append(data)
        if not self.hidden and data.strip():
            self.parts.append(data.strip())
            if self.main:self.main_parts.append(data.strip())

def collect(url):
    body,mime,final=read_public(url,maximum=4_000_000)
    if not any(t in mime for t in ('text/html','text/plain','application/xhtml')):raise ValueError('La fonte deve essere una pagina di testo o HTML.')
    parser=Extract();parser.feed(body.decode('utf-8',errors='replace'))
    title=' '.join(parser.titles).strip()[:180] or urlsplit(final).hostname
    # Store a short excerpt, never an entire article. Web pages remain untrusted data.
    excerpt=' '.join(' '.join(parser.main_parts or parser.parts).split()[:160])[:1100]
    if len(excerpt)<40:raise ValueError('Testo insufficiente: la pagina potrebbe richiedere JavaScript o un accesso.')
    return {'url':final,'title':title,'excerpt':excerpt,'retrieved':dt.datetime.now(dt.timezone.utc).isoformat(),'origin':'web','publication_date':None}

def search(query,campaign_id,language='it',country='IT'):
    if language not in ('it','en','es') or country not in ('IT','US','GB','ES','MX','FR','DE','BR'):
        raise ValueError('Lingua o paese della ricerca non supportati.')
    key=os.environ.get('BRAVE_SEARCH_API_KEY')
    if not key:raise ValueError('Ricerca automatica: configura BRAVE_SEARCH_API_KEY. Puoi già aggiungere e leggere fonti tramite URL.')
    query=store.text(query,500,True)
    if len(query.split())>75:raise ValueError('La ricerca accetta al massimo 75 parole.')
    price=store.load()['prices']['brave_eur_query']
    if price<=0:raise ValueError('Imposta prima il costo stimato in euro per ricerca.')
    store.reserve('brave',price,campaign_id,query)
    import urllib.request
    request=urllib.request.Request('https://api.search.brave.com/res/v1/web/search?'+urlencode({'q':query,'count':5,'search_lang':language,'country':country}),headers={'X-Subscription-Token':key,'Accept':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=25,context=runtime_config.ssl_context()) as response:result=json.load(response)
    except Exception:raise ValueError('Ricerca non riuscita: controlla chiave, quota e connessione. La prenotazione resta conteggiata.') from None
    sources=[]
    for r in result.get('web',{}).get('results',[])[:5]:
        try:public_url(r['url'])
        except (ValueError,KeyError):continue
        sources.append({'url':r['url'],'title':str(r.get('title',''))[:180],'excerpt':html.unescape(str(r.get('description','')))[:900],'retrieved':dt.datetime.now(dt.timezone.utc).isoformat(),'origin':'search_snippet','publication_date':r.get('page_age')})
    return sources

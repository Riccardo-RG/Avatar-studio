"""Reviewable campaign research plan; external search runs only when requested."""
import os
import platform_store as store
import web_sources

COUNTRIES=('IT','US','GB','ES','MX','FR','DE','BR')

def options(data):
    language=data.get('language','it')
    if language not in ('it','en','es'):raise ValueError('Lingua della ricerca non supportata.')
    country=data.get('research_country') or {'it':'IT','en':'US','es':'ES'}[language]
    if country not in COUNTRIES:raise ValueError('Paese della ricerca non supportato.')
    depth=data.get('research_queries',1)
    if isinstance(depth,bool) or str(depth) not in ('1','2','3'):raise ValueError('Scegli da una a tre ricerche.')
    return {'language':language,'country':country,'count':int(depth)}

def queries(campaign):
    opts=options(campaign)
    terms={'it':['domande problemi tutorial','creator video spiegazioni','alternative recensioni limiti'],
           'en':['questions problems tutorial','creators videos explainers','alternatives reviews limitations'],
           'es':['preguntas problemas tutorial','creadores videos explicaciones','alternativas reseñas limitaciones']}[opts['language']]
    base=' '.join((campaign['topic'][:240]+' '+campaign['audience'][:100]).split()[:65])
    return [base+' '+term for term in terms[:opts['count']]]

def plan(data):
    c=store.find(store.load(),'campaigns',data.get('campaign_id'))
    opts=options(c);items=queries(c);budget=store.budget_summary()
    price=budget['prices']['brave_eur_query']
    return {**opts,'queries':items,'estimated_eur':round(price*len(items),6),
            'configured':bool(os.environ.get('BRAVE_SEARCH_API_KEY')) and price>0,
            'remaining_eur':budget['remaining_eur'],
            'note':'Ricerche web esplorative: gli estratti non dimostrano ricavi, domanda o idoneità dei contenuti. Ogni ricerca usa la tariffa configurata.'}

def execute(campaign, stopped):
    opts=options(campaign);sources=[];executed=[]
    for query in queries(campaign):
        if stopped():break
        sources.extend(web_sources.search(query,campaign['id'],language=opts['language'],country=opts['country']))
        executed.append(query)
    return list({s['url']:s for s in sources}.values())[:15],executed

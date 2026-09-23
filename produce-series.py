"""Start the original starter season through the local application's authenticated API."""
import json
from pathlib import Path
from urllib.request import Request, urlopen
BASE='http://127.0.0.1:8765'
def get(path):
    with urlopen(BASE+path) as r:return json.load(r)
boot=get('/api/bootstrap')
def post(path,data):
    with urlopen(Request(BASE+'/api/'+path,json.dumps(data).encode(),headers={'Content-Type':'application/json','X-Avatar-Token':boot['token']}),timeout=90) as r:return json.load(r)
if __name__=='__main__':
    import sys
    config=post('settings',{**boot['settings'],'voice':'piper:paola','rate':160,'resolution':720,'monthly_budget_usd':0})
    doc=get('/api/studio')
    chosen=[e for e in doc['episodes'] if e['id'].startswith('s01e') and e['status'] not in ('ready','rendering')]
    if '--first' in sys.argv:chosen=chosen[:1]
    for e in chosen:post('episode-ready',{'id':e['id'],'revision':e['revision'],'ready':True})
    result=post('series-render',{'ids':[e['id'] for e in chosen]}) if chosen else {'jobs':[]}
    Path('output/started-v2.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps([{'id':j['id'],'title':j['title']} for j in result['jobs']],ensure_ascii=False))

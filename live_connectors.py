"""Read-only platform bridges. Tokens stay in a child environment, never in files."""
import json
import os
from pathlib import Path
import subprocess
import threading


class ChatConnectors:
    def __init__(self,root,node,director):
        self.root=Path(root);self.node=node;self.director=director;self.lock=threading.RLock();self.processes={}
        self.states={p:{'state':'offline','message':'Non collegato'} for p in ('twitch','youtube')}

    def snapshot(self):
        with self.lock:return {p:dict(s) for p,s in self.states.items()}

    def connect(self,data):
        platform=data.get('platform')
        if platform not in self.states:raise ValueError('Piattaforma non valida.')
        prefix='TWITCH' if platform=='twitch' else 'YOUTUBE'
        token=data.get('token') or os.environ.get(prefix+'_ACCESS_TOKEN','')
        if not isinstance(token,str) or not 8<=len(token.strip())<=3000:raise ValueError('Inserisci il token di accesso della piattaforma, oppure configurarlo nell’ambiente del server.')
        chat=data.get('chat_id') or os.environ.get('YOUTUBE_LIVE_CHAT_ID','')
        if platform=='youtube' and (not isinstance(chat,str) or not 4<=len(chat)<=300):raise ValueError('Inserisci l’ID della chat della diretta YouTube.')
        env={'PATH':os.environ.get('PATH',''),'AVATAR_CHAT_TOKEN':token.strip(),'AVATAR_CHAT_ID':str(chat)}
        with self.lock:
            self.disconnect(platform)
            proc=subprocess.Popen([self.node,str(self.root/'chat_bridge.cjs'),platform],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,env=env)
            self.processes[platform]=proc;self.states[platform]={'state':'connecting','message':'Connessione in corso…'}
        threading.Thread(target=self._read,args=(platform,proc),daemon=True).start()
        return {'ok':True}

    def _read(self,platform,proc):
        try:
            for line in proc.stdout:
                try:
                    item=json.loads(line)
                    with self.lock:
                        if self.processes.get(platform) is not proc:return
                        if item.get('type')=='message':
                            self.director.receive(item['author'][:40],item['text'][:400],platform,item.get('event_id'),item.get('user_id'))
                        elif item.get('type') in ('status','error'):
                            self.states[platform]={'state':'connected' if item['type']=='status' else 'error','message':str(item.get('message',''))[:200]}
                except (ValueError,KeyError,TypeError):continue
        finally:
            proc.wait()
            with self.lock:
                if self.processes.get(platform) is proc:
                    self.processes.pop(platform,None)
                    if self.states[platform]['state']!='error':self.states[platform]={'state':'offline','message':'Collegamento terminato.'}

    def disconnect(self,platform):
        with self.lock:
            proc=self.processes.pop(platform,None)
            if proc and proc.poll() is None:proc.terminate()
            if platform in self.states:self.states[platform]={'state':'offline','message':'Non collegato'}
        return {'ok':True}

    def close(self):
        for platform in list(self.states):self.disconnect(platform)

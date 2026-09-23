import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from character_activity import Activity
from render_gate import wait_for_live

class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);(self.root/'data').mkdir();(self.root/'output').mkdir()
        self.activity=Activity(self.root);(self.root/'data/platform.json').write_text(json.dumps({'characters':[{'id':'ari'},{'id':'lumo'}],'campaigns':[]}))
    def tearDown(self):self.tmp.cleanup()
    def test_multiscene_video_and_publications_are_references_for_both_characters(self):
        folder=self.root/'output/123456abcdef';folder.mkdir();(folder/'status.json').write_text(json.dumps({'state':'done','title':'Dialogo','created':1}))
        (folder/'project.json').write_text(json.dumps({'script':'Contenuto integrale riservato','settings':{'character':{'id':'ari'}},'scenes':[{'settings':{'character':{'id':'lumo'}}}]}))
        (self.root/'data/publications.json').write_text(json.dumps({'items':[{'id':'post1','job_id':folder.name,'title':'Post','platform':'youtube','state':'approved','created':2,'url':'https://youtube.com/watch?v=notconfirmed'}]}))
        for c in ('ari','lumo'):
            result=self.activity.snapshot(c);self.assertEqual(len(result['items']),2);self.assertNotIn('Contenuto integrale',json.dumps(result));self.assertEqual(result['items'][0]['url'],'#publishing')
    def test_remote_conversation_reference_belongs_only_to_its_character(self):
        providers_data={'sessions':[{'id':'conversation','character_id':'ari','character_name':'Ari','created':2,'state':'ended','context':'Private conversation content'}]}
        (self.root/'data/broadcast.json').write_text(json.dumps(providers_data))
        result=self.activity.snapshot('ari')
        self.assertEqual(result['items'][0]['platform'],'Tavus')
        self.assertEqual(result['items'][0]['url'],'#live')
        self.assertNotIn('Private conversation content',json.dumps(result))
        self.assertEqual(self.activity.snapshot('lumo')['items'],[])

    def test_manual_link_is_explicit_and_removable_without_media_deletion(self):
        row=self.activity.add({'character_id':'ari','title':'Diretta archiviata','platform':'twitch','url':'https://www.twitch.tv/videos/123'})
        self.assertEqual(self.activity.snapshot('ari')['items'][0]['state'],'manual');self.activity.remove(row['id']);self.assertEqual(self.activity.snapshot('ari')['items'],[])
    def test_manual_link_cannot_be_javascript_or_unrelated_domain(self):
        for url in ('javascript:alert(1)','https://twitch.tv.example.com/video','https://user:pass@www.twitch.tv/video'):
            with self.assertRaises(ValueError):self.activity.add({'character_id':'ari','title':'Link','platform':'twitch','url':url})
    def test_live_records_immutable_identity_and_restart_marks_interruption(self):
        settings={'character':{'id':'ari','name':'Ari','revision':2}};self.activity.start('Sessione locale',settings);settings['character']['name']='Altro'
        self.activity.recover();item=self.activity.snapshot('ari')['items'][0];self.assertEqual(item['character_name'],'Ari');self.assertEqual(item['state'],'interrupted');self.assertEqual(item['platform'],'regia locale')
    def test_live_gate_releases_after_stop_or_opt_out_without_holding_lock(self):
        for change in ('stop','opt-out'):
            director=SimpleNamespace(lock=threading.RLock(),phase='running',running=True,config={'defer_render':True});calls=[]
            def advance(_):
                with director.lock:
                    if change=='stop':director.phase='idle'
                    else:director.config['defer_render']=False
            wait_for_live(director,lambda:False,lambda p,m:calls.append(m),sleep=advance);self.assertEqual(len(calls),1)
    def test_waiting_render_can_be_cancelled_or_server_closed(self):
        director=SimpleNamespace(lock=threading.RLock(),phase='paused',running=True,config={})
        with self.assertRaises(ValueError):wait_for_live(director,lambda:True,lambda p,m:None)
        director.running=False
        with self.assertRaises(ValueError):wait_for_live(director,lambda:False,lambda p,m:None)

if __name__=='__main__':unittest.main()

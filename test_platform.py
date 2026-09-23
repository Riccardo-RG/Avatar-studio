import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import agent_team
import cloud_avatar
import platform_store as store
import runtime_config
import setup_mac
import studio
import web_sources
import productions
import media

class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)
        self.patches=[patch.object(store,'PATH',self.path/'platform.json'),patch.object(studio,'PATH',self.path/'studio.json'),patch.object(media,'voice_catalog',return_value=[{'id':v,'language':'it','locale':'it-IT'} for v in ('Alice','piper:paola')])]
        for p in self.patches:p.start()
        cloud_avatar.QUOTES.clear();store.load()
        self.c=store.save_campaign({'name':'Prova','topic':'Ordine digitale','audience':'Studenti italiani','objective':'Confrontare due aperture','character_id':'lumo','budget_eur':5})
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def test_stale_character_edit_cannot_overwrite_history(self):
        c=store.load()['characters'][0];first=store.save_character({**c,'name':'Nova nuova'},['piper:paola'])
        with self.assertRaises(ValueError):store.save_character({**c,'name':'Vecchia scheda'},['piper:paola'])
        self.assertEqual(store.snapshot('nova')['name'],'Nova nuova');self.assertEqual(first['history'][0]['name'],'Nova')
    def test_real_photo_requires_recorded_authorization(self):
        with self.assertRaises(ValueError):store.save_character({'kind':'photo','image':'/characters/ari.png','rights':'original'},['piper:paola'])
    def test_snapshot_immutable_across_character_changes(self):
        snap=store.render_settings({'voice':'Alice','rate':150},'lumo');c=store.find(store.load(),'characters','lumo')
        store.save_character({**c,'name':'Lumo II'},['piper:paola'])
        self.assertEqual(snap['character']['name'],'Lumo')
    def test_concurrent_budget_requests_cannot_overspend(self):
        store.save_budget({'budget_eur':1});accepted=[]
        def reserve():
            try:accepted.append(store.reserve('test',.6))
            except ValueError:pass
        threads=[threading.Thread(target=reserve) for _ in range(8)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(len(accepted),1);self.assertEqual(store.budget_summary()['reserved_eur'],.6)
    def test_campaign_budget_and_nonfinite_inputs(self):
        store.reserve('test',4,self.c['id'])
        with self.assertRaises(ValueError):store.reserve('test',2,self.c['id'])
        for value in ('NaN','Infinity',-1):
            with self.assertRaises(ValueError):store.save_budget({'budget_eur':value})
    def test_web_cannot_reach_local_network_or_credentials(self):
        for url in ('file:///etc/passwd','https://user:pass@example.com','http://example.com:8765'):
            with self.assertRaises(ValueError):web_sources.public_url(url)
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]),patch('http.client.HTTPSConnection') as conn:
            with self.assertRaises(ValueError):web_sources.read_public('https://example.com')
            conn.assert_not_called()
    def test_web_extractor_does_not_include_script(self):
        p=web_sources.Extract();p.feed('<title>Fonte</title><script>delete_all()</script><p>Contenuto utile</p>')
        self.assertNotIn('delete_all()',' '.join(p.parts))
    def test_cloud_payload_binds_selected_image_and_voice_without_text(self):
        payload=cloud_avatar.payload('picture','audio','Title')
        self.assertEqual(payload['audio_asset_id'],'audio');self.assertNotIn('script',payload);self.assertEqual(payload['image']['asset_id'],'picture')
    def test_cloud_quote_is_single_use_and_budgeted(self):
        cloud_avatar.QUOTES['one']={'expires':10**12,'amount_eur':1,'campaign_id':self.c['id'],'title':'Test'}
        cloud_avatar.consume('one')
        with self.assertRaises(ValueError):cloud_avatar.consume('one')
        self.assertEqual(store.budget_summary()['reserved_eur'],1)
    def test_team_without_sources_never_invents_research(self):
        run={'id':'r1','status':'queued','role':'all','steps':[]};store.change_campaign(self.c['id'],lambda c:c['runs'].append(copy.deepcopy(run)))
        with patch('providers.agent_text') as model:agent_team.work(self.c['id'],self.c,run,threading.Event(),False)
        model.assert_not_called();result=store.find(store.load(),'campaigns',self.c['id'])['runs'][0];self.assertEqual(result['status'],'needs_sources')
    def test_stopped_team_does_not_start_next_model(self):
        run={'id':'r2','status':'queued','role':'all','steps':[]};store.change_campaign(self.c['id'],lambda c:c['runs'].append(copy.deepcopy(run)));event=threading.Event();event.set()
        with patch('providers.agent_text') as model:agent_team.work(self.c['id'],self.c,run,event,False)
        model.assert_not_called();self.assertEqual(run['status'],'cancelled')
    def test_writer_draft_requires_review_before_production(self):
        item={'id':'content','title':'Titolo','script':'Un copione originale da rivedere.','status':'draft'}
        store.change_campaign(self.c['id'],lambda c:c['contents'].append(item))
        with self.assertRaises(ValueError):agent_team.to_plan({'campaign_id':self.c['id'],'content_id':'content'})
        agent_team.save_content({'campaign_id':self.c['id'],'content_id':'content','reviewed':True})
        first=agent_team.to_plan({'campaign_id':self.c['id'],'content_id':'content'});second=agent_team.to_plan({'campaign_id':self.c['id'],'content_id':'content'})
        self.assertEqual(first['episode_id'],second['episode_id']);episode=next(e for e in studio.load()['episodes'] if e['id']==first['episode_id']);self.assertEqual(episode['character_id'],'lumo')
    def test_no_observations_does_not_become_zero_performance(self):
        result=store.analyze(self.c);self.assertIsNone(result['ctr_percent']);self.assertIsNone(result['cost_per_lead'])
    def test_writer_receives_strategy_objective_and_collected_evidence(self):
        source={'url':'https://example.com/source','excerpt':'Fonte raccolta verificabile.'}
        self.c['sources']=[source]
        run={'id':'team-context','status':'queued','role':'all','steps':[]}
        store.change_campaign(self.c['id'],lambda c:c['runs'].append(copy.deepcopy(run)))
        script='Quante cose tieni sulla scrivania? Prova a scegliere un solo oggetto utile per il prossimo lavoro. Riponi il resto e osserva se trovi più facilmente ciò che cerchi.'
        with patch('providers.agent_text',return_value='Confronta domanda iniziale ed esempio pratico.'),patch('providers.generate_script',return_value={'script':script}) as writer:
            agent_team.work(self.c['id'],self.c,run,threading.Event(),False)
        context=writer.call_args.args[2]['editorial_context']
        self.assertIn('Confronta domanda iniziale',context);self.assertIn(self.c['objective'],context);self.assertIn(source['excerpt'],context)
        self.assertEqual(run['status'],'done')
    def test_arm_plan_uses_native_packages_and_gpu(self):
        plan=setup_mac.plan('arm64');self.assertIn('arm64',plan['node_url']);self.assertIn('arm64',plan['llama_url']);self.assertEqual(plan['gpu_layers'],'99')
    def test_production_freezes_cast_and_checks_total_length(self):
        p=productions.prepare({'scenes':[{'character_id':'lumo','script':'Prima voce.'},{'character_id':'ari','script':'Seconda voce.','voice':'Alice'}],'format':'landscape','music':'soft-original'},['piper:paola','Alice'])
        self.assertEqual(p['scenes'][1]['settings']['voice'],'Alice');self.assertEqual(p['config']['format'],'landscape')
        with self.assertRaises(ValueError):productions.prepare({'scenes':[{'script':'x'*1000}]*3},['piper:paola'])
    def test_default_character_overrides_legacy_global_identity(self):
        result=store.render_settings({'voice':'Alice','rate':140,'name':'Lumo','accent':'#abcdef'})
        c=store.snapshot()
        for key in store.APPEARANCE_FIELDS:self.assertEqual(result[key],c[key])
        self.assertEqual(result['character']['id'],'nova')

if __name__=='__main__':unittest.main()

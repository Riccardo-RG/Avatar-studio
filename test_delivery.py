import copy
import os
import datetime as dt
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import broadcast
import cloud_avatar
from live import LiveDirector
import platform_store
import publishing as pub
import service_connections as services
import social_adapters as adapters

class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.job='f1f1f1f1f1f1'
        self.patches=[patch.object(pub,'ROOT',self.root),patch.object(pub,'PATH',self.root/'publications.json'),patch.object(services,'PATH',self.root/'connections.json'),patch.object(broadcast,'PATH',self.root/'broadcast.json'),patch.object(platform_store,'PATH',self.root/'platform.json'),patch.object(pub,'prepare_media',side_effect=self.prepare)]
        for p in self.patches:p.start()
        services.VAULT.clear();services.DISCONNECTED.clear();services.PENDING.clear();broadcast.QUOTES.clear();broadcast.ROOMS.clear();pub.ARMED=False;pub.BUSY.clear();pub.STOP.clear()
    def tearDown(self):
        pub.ARMED=False;pub.BUSY.clear();pub.STOP.clear();services.VAULT.clear()
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def prepare(self,job,platform):
        file=self.root/'output/publish-media'/job/platform/'video.mp4';file.parent.mkdir(parents=True,exist_ok=True)
        if not file.exists():file.write_bytes(b'fixture-video-unchanging')
        return file,{'duration':16},{'title':'Prova','description':'Personaggio virtuale.'}
    def draft(self,platform='youtube',job=None,offset=600):
        return pub.save({'job_id':job or self.job,'platform':platform,'visibility':{'youtube':'private','tiktok':'inbox','instagram':'public'}[platform],'due_at':dt.datetime.fromtimestamp(time.time()+offset,dt.timezone.utc).isoformat(),'timezone':'Europe/Rome'})
    def approve(self,p):return pub.approve({'items':[{'id':p['id'],'revision':p['revision']}],'mode':'single'})
    def test_draft_cannot_send_or_simulate_without_review(self):
        p=self.draft()
        with self.assertRaises(ValueError):pub.simulate({'ids':[p['id']]})
        with self.assertRaises(ValueError):pub.deliver(p['id'])
    def test_simulation_has_no_remote_requests_and_never_claims_publication(self):
        p=self.draft();self.approve(p)
        with patch.object(services,'http') as http:
            result=pub.simulate({'ids':[p['id']]});http.assert_not_called()
        self.assertFalse(result['published']);self.assertEqual(pub.find(pub.load(),p['id'])['state'],'approved')
    def test_edit_invalidates_approval(self):
        p=self.draft();self.approve(p);changed=pub.save({**p,'title':'Titolo diverso'})
        self.assertEqual(changed['state'],'draft');self.assertIsNone(changed['approval'])
    def test_stale_edit_cannot_overwrite_a_new_revision(self):
        p=self.draft();pub.save({**p,'title':'Nuovo'})
        with self.assertRaises(ValueError):pub.save({**p,'title':'Vecchio'})
    def test_file_change_invalidates_simulation(self):
        p=self.draft();self.approve(p);pub.file(p).write_bytes(b'changed')
        with self.assertRaises(ValueError):pub.simulate({'ids':[p['id']]})
    def test_same_video_cannot_be_queued_twice_for_same_platform(self):
        self.draft()
        with self.assertRaises(ValueError):self.draft()
        self.draft('tiktok')
    def test_weekly_approval_is_atomic_when_weeks_differ(self):
        a=self.draft();b=self.draft(job='e1e1e1e1e1e1',offset=9*86400)
        with self.assertRaises(ValueError):pub.approve({'mode':'weekly','items':[{'id':p['id'],'revision':p['revision']} for p in [a,b]]})
        self.assertTrue(all(p['state']=='draft' for p in pub.load()['items']))
    def test_weekly_approval_records_the_exact_selected_group(self):
        a=self.draft();b=self.draft('tiktok');c=self.draft('instagram')
        result=pub.approve({'mode':'weekly','items':[{'id':p['id'],'revision':p['revision']} for p in [a,b]]})
        self.assertEqual(result['approved'],2);self.assertEqual(pub.find(pub.load(),c['id'])['state'],'draft')
        self.assertTrue(all(pub.valid(p) for p in pub.load()['items'][:2]))
    def test_naive_datetime_is_rejected(self):
        with self.assertRaises(ValueError):pub.due('2026-09-21T12:00')
    def test_wall_time_uses_selected_zone_and_rejects_dst_ambiguity(self):
        self.assertEqual(pub.wall_time('2026-09-21T20:00','Europe/Rome'),'2026-09-21T18:00:00+00:00')
        for date in ('2026-03-29T02:30','2026-10-25T02:30'):
            with self.assertRaises(ValueError):pub.wall_time(date,'Europe/Rome')
    def test_instagram_caption_never_silently_truncated(self):
        p=self.draft('instagram')
        with self.assertRaises(ValueError):pub.save({**p,'description':'x'*2201})
    def test_disconnection_also_blocks_environment_token_for_this_session(self):
        with patch.dict(os.environ,{'AVATAR_YOUTUBE_ACCESS_TOKEN':'environment-secret'}):
            self.assertTrue(services.secret('youtube','access_token'));services.disconnect('youtube')
            self.assertEqual(services.secret('youtube','access_token'),'')
    def test_unready_post_does_not_starve_other_due_posts(self):
        a=self.draft(offset=-1);b=self.draft('tiktok',offset=-1);self.approve(a);self.approve(b);pub.ARMED=True
        with patch.object(pub,'deliver',side_effect=[ValueError('Account mancante'),{}]) as deliver:pub.scheduler_tick()
        self.assertEqual([c.args[0] for c in deliver.call_args_list],[a['id'],b['id']])
    def test_youtube_partial_ack_does_not_continue_with_wrong_offset(self):
        p=self.draft();file=pub.file(p)
        with patch.object(services,'auth',return_value={}),patch.object(services,'http',side_effect=[({}, {'Location':'https://www.googleapis.com/upload/session'},200),({}, {'Range':'bytes=0-2'},308)]):
            with self.assertRaises(services.RemoteError):adapters.send(p,file,lambda f:None,lambda:False)
    def test_heygen_recovery_only_polls_existing_video(self):
        folder=self.root/'heygen';folder.mkdir();(folder/'external.json').write_text(json.dumps({'video_id':'existing123'}));(folder/'cloud-recovery.json').write_text(json.dumps({'script':'Testo originale'}))
        with patch.object(cloud_avatar,'status',return_value={'heygen':True}):remote,saved=cloud_avatar.recovery(folder)
        with patch.object(cloud_avatar,'request',return_value={'status':'completed','video_url':'https://example.org/video.mp4'}) as request,patch.object(cloud_avatar,'read_public',return_value=(b'0000ftyp0000','video/mp4','')):
            cloud_avatar.wait_video(remote,folder,lambda:False,lambda p,m:None)
            request.assert_called_once_with('/videos/existing123',timeout=90)
        self.assertEqual(saved['script'],'Testo originale');self.assertTrue((folder/'external.mp4').exists())
    def test_approval_cannot_be_reused_after_metadata_tampering(self):
        p=self.draft();self.approve(p);pub.patch(p['id'],{'visibility':'public'})
        self.assertFalse(pub.valid(pub.find(pub.load(),p['id'])))
    def test_restart_preserves_uncertainty_and_never_resends(self):
        p=self.draft();pub.patch(p['id'],{'state':'sending'});pub.recover()
        self.assertEqual(pub.find(pub.load(),p['id'])['state'],'uncertain')
        with patch.object(adapters,'send') as send:
            with self.assertRaises(ValueError):pub.deliver(p['id'])
            send.assert_not_called()
    def test_delivery_stops_before_upload_if_account_has_changed(self):
        p=self.draft();self.approve(p);p=pub.patch(p['id'],{'account_id':'approved-channel'});pub.ARMED=True
        with patch.object(services,'verify',return_value={'account_id':'different-channel'}),patch.object(adapters,'send') as send:pub._send(p);send.assert_not_called()
        self.assertEqual(pub.find(pub.load(),p['id'])['state'],'uncertain')
    def test_late_post_requires_rescheduling(self):
        p=self.draft();self.approve(p);pub.patch(p['id'],{'due_at':dt.datetime.fromtimestamp(time.time()-7200,dt.timezone.utc).isoformat()})
        p=pub.find(pub.load(),p['id']);p['approval']['digest']=pub.digest(p);pub.patch(p['id'],{'approval':p['approval']});pub.ARMED=True
        self.assertEqual(pub.deliver(p['id'])['state'],'missed')
    def test_credentials_never_enter_public_config(self):
        services.save({'service':'youtube','client_id':'id','client_secret':'secret-value','access_token':'token-value'})
        text=services.PATH.read_text()+json.dumps(services.snapshot())
        self.assertNotIn('secret-value',text);self.assertNotIn('token-value',text);self.assertTrue(services.snapshot()['youtube']['connected'])
        services.disconnect('youtube');self.assertFalse(services.snapshot()['youtube']['connected'])
    def test_oauth_uses_pkce_and_rejects_forged_state(self):
        services.save({'service':'youtube','client_id':'desktop-id'})
        url=services.oauth_start('http://127.0.0.1:8765')['url']
        self.assertIn('code_challenge_method=S256',url)
        with patch.object(services,'http') as http:
            with self.assertRaises(ValueError):services.oauth_finish('state=forged&code=nope')
            http.assert_not_called()
    def test_upload_redirect_destination_cannot_steal_token(self):
        for url in ('http://www.googleapis.com/upload','https://www.googleapis.com.evil.test/upload','https://user:secret@www.googleapis.com/upload','https://127.0.0.1/upload'):
            with self.assertRaises(ValueError):services.checked_url(url)
    def test_youtube_upload_and_processing_are_distinct(self):
        p=self.draft();file=pub.file(p);seen=[]
        responses=[({}, {'Location':'https://www.googleapis.com/upload/session'},200),({'id':'video123'}, {},201)]
        with patch.object(services,'auth',return_value={}),patch.object(services,'http',side_effect=responses):
            result=adapters.send(p,file,seen.append,lambda:False)
        self.assertEqual(result['state'],'processing');self.assertEqual(result['remote_id'],'video123');self.assertTrue(seen)
        meta=adapters.youtube_metadata(p);self.assertTrue(meta['status']['containsSyntheticMedia']);self.assertEqual(meta['status']['privacyStatus'],'private')
    def test_youtube_reports_actual_privacy_instead_of_requested(self):
        p=self.draft();p['remote_id']='video123';p['visibility']='public'
        with patch.object(services,'auth',return_value={}),patch.object(services,'http',return_value=({'items':[{'status':{'uploadStatus':'processed','privacyStatus':'private'}}]}, {},200)):
            result=adapters.reconcile(p,lambda f:None)
        self.assertEqual(result['actual_visibility'],'private');self.assertEqual(result['state'],'published')
    def test_tiktok_draft_is_not_reported_as_published(self):
        p=self.draft('tiktok');p['remote_id']='v_inbox~123'
        with patch.object(services,'auth',return_value={}),patch.object(services,'http',return_value=({'data':{'status':'SEND_TO_USER_INBOX'}}, {},200)):
            self.assertEqual(adapters.reconcile(p,lambda f:None)['state'],'handed_off')
    def test_tiktok_chunk_plan_respects_final_remainder(self):
        p=adapters.source_chunks(70_000_000);self.assertEqual(p['total_chunk_count'],2);self.assertEqual(p['chunk_size'],32_000_000)
        self.assertEqual(adapters.source_chunks(1000)['chunk_size'],1000)
    def test_instagram_never_publishes_without_allow_flag(self):
        p=self.draft('instagram');p['container_id']='container123'
        with patch.object(services,'auth',return_value={}),patch.object(services,'http',return_value=({'status_code':'FINISHED'}, {},200)) as http:
            result=adapters.reconcile(p,lambda f:None,False)
        self.assertEqual(result['state'],'processing');self.assertEqual(http.call_count,1)
    def test_instagram_persists_publish_intent_before_mutation(self):
        services.save({'service':'instagram','account_id':'12345'});p=self.draft('instagram');p['container_id']='container123';order=[]
        def http(url,method='GET',*args,**kwargs):
            order.append(method);return ({'status_code':'FINISHED'} if method=='GET' else {'id':'post123'}, {},200)
        with patch.object(services,'auth',return_value={}),patch.object(services,'http',side_effect=http):result=adapters.reconcile(p,lambda f:order.append(f.get('stage')),True)
        self.assertLess(order.index('publish_requested'),order.index('POST'));self.assertEqual(result['state'],'published')
    def test_unavailable_metrics_are_not_invented_as_zero(self):
        p=self.draft();p['remote_id']='video123'
        with patch.object(services,'auth',return_value={}),patch.object(services,'http',return_value=({'items':[{'statistics':{'viewCount':'12'}}]}, {},200)):
            result=adapters.metrics(p)
        self.assertEqual(result['values']['views'],12);self.assertIsNone(result['values']['likes'])
    def test_tavus_plan_without_account_has_no_api_call_or_reservation(self):
        with patch.object(services,'http') as http:r=broadcast.plan({'minutes':2});http.assert_not_called()
        self.assertTrue(r['missing']);self.assertEqual(platform_store.load()['reservations'],[])
    def test_tavus_sets_provider_duration_limit_and_keeps_join_token_private(self):
        services.save({'service':'tavus','api_key':'private-key','face_id':'face123','pal_id':'pal123','eur_minute':'1'})
        c=platform_store.snapshot('nova');platform_store.save_character({**c,'tavus_face_id':'face123','tavus_pal_id':'pal123'},['piper:paola']);q=broadcast.plan({'minutes':2,'character_id':'nova'});response={'conversation_id':'conversation123','conversation_url':'https://tavus.daily.co/conversation123','meeting_token':'private-meeting-token'}
        with patch.object(services,'http',return_value=(response,{},200)) as http:r=broadcast.start({'quote_id':q['id'],'confirmed':True})
        self.assertEqual(http.call_args.args[2]['properties']['max_call_duration'],120);self.assertNotIn('private-meeting-token',broadcast.PATH.read_text());self.assertEqual(r['state'],'active')
    def test_tavus_plan_uses_the_selected_character_mapping(self):
        for identity in ('nova','lumo'):
            c=platform_store.snapshot(identity)
            platform_store.save_character({**c,'tavus_face_id':identity+'face','tavus_pal_id':identity+'pal'},['piper:paola'])
        q=broadcast.plan({'minutes':2,'character_id':'lumo'})
        self.assertEqual(q['face_id'],'lumoface');self.assertEqual(q['pal_id'],'lumopal')
        self.assertEqual(q['character_name'],'Lumo')

    def test_tavus_never_substitutes_a_global_face_for_an_unmapped_character(self):
        services.save({'service':'tavus','api_key':'private-key','face_id':'oldface','pal_id':'oldpal','eur_minute':'1'})
        q=broadcast.plan({'minutes':2,'character_id':'ari'})
        self.assertIsNone(q['face_id']);self.assertTrue(any('Ari' in field for field in q['missing']))
        with patch.object(services,'http') as http:
            with self.assertRaises(ValueError):broadcast.start({'quote_id':q['id'],'confirmed':True})
            http.assert_not_called()

    def test_tavus_profile_edit_invalidates_the_reviewed_plan_before_spending(self):
        services.save({'service':'tavus','api_key':'private-key','eur_minute':'1'})
        c=platform_store.snapshot('nova')
        saved=platform_store.save_character({**c,'tavus_face_id':'firstface','tavus_pal_id':'firstpal'},['piper:paola'])
        q=broadcast.plan({'minutes':2,'character_id':'nova'})
        platform_store.save_character({**saved,'tavus_face_id':'otherface'},['piper:paola'])
        with patch.object(services,'http') as http:
            with self.assertRaises(ValueError):broadcast.start({'quote_id':q['id'],'confirmed':True})
            http.assert_not_called()
        self.assertEqual(platform_store.load()['reservations'],[])

    def test_obs_refuses_start_without_explicit_product_confirmation(self):
        with patch('subprocess.run') as process:
            with self.assertRaises(ValueError):broadcast.obs({'action':'start_stream'},'http://127.0.0.1:8765')
        process.assert_not_called()
    def test_live_character_frozen_for_session(self):
        director=LiveDirector(self.root,start_thread=False)
        try:
            director.save_config({'character_id':'lumo','autopilot':False});director.claim('test-scene');director.control('start')
            first=director.snapshot()['character_settings'];self.assertEqual(first['character']['id'],'lumo')
            c=platform_store.find(platform_store.load(),'characters','lumo');platform_store.save_character({**c,'name':'Nuovo nome'},['piper:paola'])
            self.assertEqual(director.snapshot()['character_settings']['name'],'Lumo')
            with self.assertRaises(ValueError):director.save_config({'character_id':'ari'})
            director.control('stop');director.save_config({'character_id':'ari'});self.assertEqual(director.snapshot()['character_settings']['character']['id'],'ari')
        finally:director.close()

if __name__=='__main__':unittest.main()

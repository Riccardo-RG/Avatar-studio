import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs,urlparse
import publishing as pub
import service_connections as services
import social_adapters as adapters

class AccountTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        for module,key,value in [(services,'PATH',self.root/'connections.json'),(pub,'PATH',self.root/'publications.json'),(pub,'ROOT',self.root)]:
            p=patch.object(module,key,value);p.start();self.addCleanup(p.stop)
        services.VAULT.clear();services.DISCONNECTED.clear();services.PENDING.clear();services.OPERATIONS.clear();pub.BUSY.clear()
        self.addCleanup(services.VAULT.clear);self.addCleanup(services.OPERATIONS.clear)
        def prepare(job,platform):
            file=self.root/'output/publish-media'/job/platform/'video.mp4';file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(b'test-video')
            return file,{'duration':5},{'title':'Test','description':'Testo'}
        p=patch.object(pub,'prepare_media',side_effect=prepare);p.start();self.addCleanup(p.stop)
        services.save({'service':'youtube','nickname':'Lumo Italia','account_id':'channel-A','access_token':'token-A','client_id':'client-A'})
        self.a='default';services.create_profile({'service':'youtube','nickname':'Lumo English'});self.b=services.config('youtube')['id']
        services.save({'service':'youtube','profile_id':self.b,'account_id':'channel-B','access_token':'token-B','client_id':'client-B'})
    def draft(self,profile=None,job='f'*12):
        return pub.save({'job_id':job,'platform':'youtube','connection_id':profile or self.a,'visibility':'private','due_at':dt.datetime.fromtimestamp(time.time()+600,dt.timezone.utc).isoformat()})
    def test_switch_preserves_both_credentials_without_exposing_them(self):
        services.switch_profile({'service':'youtube','profile_id':self.a});self.assertEqual(services.token('youtube'),'token-A')
        services.switch_profile({'service':'youtube','profile_id':self.b});self.assertEqual(services.token('youtube'),'token-B')
        self.assertEqual(services.token('youtube',self.a),'token-A')
        raw=services.PATH.read_text()+json.dumps(services.snapshot());self.assertNotIn('token-A',raw);self.assertNotIn('token-B',raw)
    def test_new_profile_never_inherits_default_environment_token(self):
        services.create_profile({'service':'youtube','nickname':'Third'});identity=services.config('youtube')['id']
        with patch.dict(os.environ,{'AVATAR_YOUTUBE_ACCESS_TOKEN':'environment-token'}):self.assertEqual(services.secret('youtube','access_token',identity),'')
        with self.assertRaises(ValueError):services.token('youtube',identity)
    def test_disconnect_targets_only_selected_profile(self):
        services.disconnect('youtube',self.a)
        self.assertEqual(services.secret('youtube','access_token',self.a),'');self.assertEqual(services.token('youtube',self.b),'token-B')
        self.assertEqual(len(services.snapshot()['youtube']['profiles']),2)
    def test_invalid_profile_never_falls_back_to_active(self):
        with self.assertRaises(ValueError):services.config('youtube','missing')
        with self.assertRaises(ValueError):self.draft('missing')
        with self.assertRaises(ValueError):services.switch_profile({'service':'tiktok','profile_id':self.b})
    def test_same_video_can_go_to_two_accounts_but_not_twice_to_one(self):
        a=self.draft(self.a);b=self.draft(self.b);self.assertNotEqual(a['id'],b['id'])
        with self.assertRaises(ValueError):self.draft(self.a)
        services.save({'service':'youtube','profile_id':self.b,'account_id':'channel-A'})
        with self.assertRaises(ValueError):self.draft(self.b)
    def test_switch_never_changes_an_approved_destination(self):
        p=self.draft();pub.approve({'items':[{'id':p['id'],'revision':p['revision']}]})
        services.switch_profile({'service':'youtube','profile_id':self.b});saved=pub.find(pub.load(),p['id'])
        self.assertEqual(saved['connection_id'],self.a);self.assertEqual(saved['account_id'],'channel-A');self.assertTrue(pub.valid(saved))
        saved['connection_id']=self.b;self.assertFalse(pub.valid(saved))
    def test_send_pins_account_even_if_switch_happens_during_verification(self):
        p=self.draft();seen=[]
        def http(url,method='GET',body=None,headers=None,**kw):
            self.assertEqual(headers['Authorization'],'Bearer token-A')
            services.switch_profile({'service':'youtube','profile_id':self.b})
            return {'items':[{'id':'channel-A','snippet':{'title':'A'}}]},{},200
        def send(item,*args):
            seen.append(services.auth('youtube',item['connection_id'])['Authorization']);return {'state':'processing'}
        with patch.object(services,'http',side_effect=http),patch.object(adapters,'send',side_effect=send):pub._send(p)
        self.assertEqual(seen,['Bearer token-A']);self.assertEqual(services.config('youtube')['id'],self.b)
        self.assertEqual(services.config('youtube',self.a)['label'],'A')
    def test_account_edits_block_during_use_but_switch_and_other_profile_still_work(self):
        with services.bound('youtube',self.a):
            services.switch_profile({'service':'youtube','profile_id':self.b})
            self.assertEqual(services.config('youtube')['id'],self.a)
            with self.assertRaises(ValueError):services.save({'service':'youtube','profile_id':self.a,'access_token':'replacement'})
            with self.assertRaises(ValueError):services.disconnect('youtube',self.a)
            services.save({'service':'youtube','profile_id':self.b,'nickname':'Other name'})
        self.assertEqual(services.config('youtube')['id'],self.b);self.assertEqual(services.OPERATIONS,set())
    def test_oauth_callback_uses_original_profile_after_switch(self):
        url=services.oauth_start('http://127.0.0.1:8765',self.a)['url'];state=parse_qs(urlparse(url).query)['state'][0]
        services.switch_profile({'service':'youtube','profile_id':self.b});calls=[]
        def http(url,method='GET',body=None,headers=None,**kw):
            calls.append((url,body,headers))
            if url.endswith('/token'):
                self.assertEqual(parse_qs(body.decode())['client_id'],['client-A']);return {'access_token':'oauth-token-A','refresh_token':'refresh-A'}, {},200
            self.assertEqual(headers['Authorization'],'Bearer oauth-token-A');return {'items':[{'id':'channel-A','snippet':{'title':'Original account'}}]}, {},200
        with patch.object(services,'http',side_effect=http):result=services.oauth_finish('state='+state+'&code=test')
        self.assertEqual(result['profile_id'],self.a);self.assertEqual(services.token('youtube',self.b),'token-B');self.assertEqual(services.config('youtube')['id'],self.b)
    def test_oauth_rejects_edited_profile_without_exchange(self):
        url=services.oauth_start('http://127.0.0.1:8765',self.a)['url'];state=parse_qs(urlparse(url).query)['state'][0]
        services.save({'service':'youtube','profile_id':self.a,'client_id':'changed'})
        with patch.object(services,'http') as http:
            with self.assertRaises(ValueError):services.oauth_finish('state='+state+'&code=test')
            http.assert_not_called()
    def test_analytics_permissions_are_explicit_and_keep_existing_scopes(self):
        for analytics,revenue in ((False,False),(True,False),(True,True)):
            with self.subTest(analytics=analytics,revenue=revenue),patch.object(services,'http') as http:
                url=services.oauth_start('http://127.0.0.1:8765',self.a,analytics=analytics,revenue=revenue)['url']
                scopes=set(parse_qs(urlparse(url).query)['scope'][0].split())
                self.assertIn('https://www.googleapis.com/auth/youtube.upload',scopes)
                self.assertIn('https://www.googleapis.com/auth/youtube.readonly',scopes)
                self.assertEqual('https://www.googleapis.com/auth/yt-analytics.readonly' in scopes,analytics)
                self.assertEqual('https://www.googleapis.com/auth/yt-analytics-monetary.readonly' in scopes,revenue)
                http.assert_not_called()
    def test_invalid_permission_requests_create_no_pending_login(self):
        for options in ({'analytics':'false'},{'revenue':1},{'revenue':True}):
            before=copy.deepcopy(services.PENDING)
            with self.assertRaises(ValueError):services.oauth_start('http://127.0.0.1:8765',self.a,**options)
            self.assertEqual(services.PENDING,before)
    def test_metrics_use_post_account_when_another_is_selected(self):
        p=self.draft();pub.patch(p['id'],{'state':'published','remote_id':'video-A'});services.switch_profile({'service':'youtube','profile_id':self.b})
        def http(url,method='GET',body=None,headers=None,**kw):
            self.assertEqual(headers['Authorization'],'Bearer token-A')
            return ({'items':[{'id':'channel-A','snippet':{'title':'A'}}]} if '/channels?' in url else {'items':[{'statistics':{'viewCount':'7'}}]}),{},200
        with patch.object(services,'http',side_effect=http):r=pub.collect_metrics({'id':p['id']})
        self.assertEqual(r['values']['views'],7)
    def test_migration_keeps_valid_old_approval_bound_to_original_default(self):
        p=self.draft();pub.approve({'items':[{'id':p['id'],'revision':p['revision']}]});doc=pub.load();item=doc['items'][0];item.pop('connection_id');item.pop('connection_name')
        item['approval']['digest']=hashlib.sha256(json.dumps({k:item[k] for k in pub.FROZEN if k!='connection_id'},sort_keys=True,ensure_ascii=False).encode()).hexdigest();pub.write(doc)
        migrated=pub.load()['items'][0];self.assertEqual(migrated['connection_id'],'default');self.assertTrue(pub.valid(migrated));self.assertEqual(migrated['account_id'],'channel-A')
    def test_token_refresh_does_not_block_switch_of_another_profile(self):
        import threading
        services.VAULT[services.key_for('youtube',self.a)].update(expires_at=0,refresh_token='refresh-A')
        def http(*args,**kwargs):
            worker=threading.Thread(target=lambda:services.switch_profile({'service':'youtube','profile_id':self.b}))
            worker.start();worker.join(2);self.assertFalse(worker.is_alive(),'Global lock held during network refresh')
            return {'access_token':'renewed-A','expires_in':3600},{},200
        with services.bound('youtube',self.a),patch.object(services,'http',side_effect=http):self.assertEqual(services.token('youtube',self.a),'renewed-A')
        self.assertEqual(services.token('youtube',self.b),'token-B')
    def test_stale_refresh_cannot_overwrite_replaced_credentials(self):
        services.VAULT[services.key_for('youtube',self.a)].update(expires_at=0,refresh_token='refresh-A')
        def http(*args,**kwargs):
            services.save({'service':'youtube','profile_id':self.a,'access_token':'user-replacement'})
            return {'access_token':'stale-response'},{},200
        with patch.object(services,'http',side_effect=http):
            with self.assertRaises(ValueError):services.token('youtube',self.a)
        self.assertEqual(services.secret('youtube','access_token',self.a),'user-replacement')
    def test_legacy_connections_migrate_without_losing_label(self):
        services.PATH.write_text(json.dumps({'youtube':{'client_id':'old-client','label':'Old channel','account_id':'old-id'}}))
        doc=services.load();self.assertEqual(doc['youtube']['profiles'][0]['label'],'Old channel');self.assertEqual(doc['youtube']['active_profile'],'default')

if __name__=='__main__':unittest.main()

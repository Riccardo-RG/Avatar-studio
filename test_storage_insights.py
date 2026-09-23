import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock,patch
import insights
import publishing as pub
import service_connections as services
import storage_upload as storage

class PersonalToolsTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name);self.job='1'*12
        for module,key,value in [(pub,'ROOT',self.root),(pub,'PATH',self.root/'publications.json'),(services,'PATH',self.root/'connections.json'),(insights,'ROOT',self.root),(insights,'PATH',self.root/'insights.json')]:
            p=patch.object(module,key,value);p.start();self.addCleanup(p.stop)
        self.file=self.root/'output/publish-media'/self.job/'instagram/video.mp4';self.file.parent.mkdir(parents=True);self.raw=b'local-video-fixture';self.file.write_bytes(self.raw)
        p=patch.object(pub,'prepare_media',return_value=(self.file,{'duration':5},{'title':'Una clip','description':'Descrizione'}));p.start();self.addCleanup(p.stop)
        p=patch('socket.getaddrinfo',return_value=[(2,1,6,'',('93.184.216.34',443))]);p.start();self.addCleanup(p.stop)
        services.VAULT.clear();services.DISCONNECTED.clear();storage.PLANS.clear();storage.BUSY.clear();insights.ENABLED=False;insights.RUNNING=False;insights.LAST_RUN=0;insights.STOP.clear();pub.BUSY.clear()
        self.addCleanup(services.VAULT.clear);self.addCleanup(insights.close)
        self.post=pub.save({'job_id':self.job,'platform':'instagram','visibility':'public','due_at':dt.datetime.fromtimestamp(time.time()+3600,dt.timezone.utc).isoformat()})
    def connect(self):
        services.save({'service':'r2','r2_account_id':'a'*32,'bucket':'personal-video','public_base':'https://media.example.com','access_key_id':'test-id','secret_access_key':'test-secret'})
    def s3(self,exists=False):
        client=Mock()
        if exists:client.head_object.return_value={'Metadata':{'sha256':self.post['media_sha256']},'ContentLength':len(self.raw)}
        else:
            error=Exception('not found');error.response={'Error':{'Code':'404'}};client.head_object.side_effect=error
        return client
    def upload(self,client,plan=None):
        plan=plan or storage.plan({'id':self.post['id']})
        with patch.object(storage,'client',return_value=client),patch.object(storage,'read_public',return_value=(self.raw,{},'https://media.example.com')):
            return storage.upload({'plan_id':plan['id'],'confirmed':True})
    def test_storage_plan_without_credentials_has_no_upload(self):
        with patch.object(storage,'client') as client:r=storage.plan({'id':self.post['id']});client.assert_not_called()
        self.assertTrue(r['missing']);self.assertIsNone(r['destination'])
    def test_successful_storage_upload_resets_approval_and_never_publishes(self):
        self.connect();pub.approve({'items':[{'id':self.post['id'],'revision':self.post['revision']}],'mode':'single'})
        client=self.s3();result=self.upload(client)
        client.put_object.assert_called_once();saved=pub.find(pub.load(),self.post['id'])
        self.assertEqual(saved['state'],'draft');self.assertIsNone(saved['approval']);self.assertEqual(saved['source_url'],result['url'])
        self.assertEqual(saved['revision'],self.post['revision']+1);self.assertFalse(result['reused'])
        self.assertNotIn('test-secret',services.PATH.read_text());self.assertNotIn('test-secret',json.dumps(services.snapshot()))
    def test_retry_reuses_same_content_object_without_second_put(self):
        self.connect();client=self.s3(True);result=self.upload(client)
        client.put_object.assert_not_called();self.assertTrue(result['reused'])
        self.assertIn(self.post['media_sha256'],result['url'])
    def test_storage_requires_explicit_confirmation(self):
        self.connect();plan=storage.plan({'id':self.post['id']})
        with patch.object(storage,'client') as client:
            with self.assertRaises(ValueError):storage.upload({'plan_id':plan['id']})
            client.assert_not_called()
    def test_changed_post_or_destination_cannot_use_old_plan(self):
        self.connect();plan=storage.plan({'id':self.post['id']});pub.save({**self.post,'title':'Modificato'})
        with patch.object(storage,'client') as client:
            with self.assertRaises(ValueError):storage.upload({'plan_id':plan['id'],'confirmed':True})
            client.assert_not_called()
        plan=storage.plan({'id':self.post['id']});services.save({'service':'r2','bucket':'other-bucket'})
        with self.assertRaises(ValueError):storage.upload({'plan_id':plan['id'],'confirmed':True})
    def test_wrong_public_file_does_not_replace_post_url(self):
        self.connect();plan=storage.plan({'id':self.post['id']})
        with patch.object(storage,'client',return_value=self.s3()),patch.object(storage,'read_public',return_value=(b'wrong',{},'')):
            with self.assertRaises(ValueError):storage.upload({'plan_id':plan['id'],'confirmed':True})
        self.assertEqual(pub.find(pub.load(),self.post['id'])['source_url'],'')
    def test_unknown_upload_result_is_not_retried_automatically(self):
        self.connect();client=self.s3();client.put_object.side_effect=TimeoutError()
        with self.assertRaisesRegex(ValueError,'incerto'):self.upload(client)
        self.assertEqual(client.put_object.call_count,1);self.assertEqual(storage.BUSY,set())
    def test_sdk_client_is_bound_to_configured_r2_account(self):
        self.connect();client=storage.client(services.config('r2'))
        self.assertEqual(client.meta.endpoint_url,'https://'+'a'*32+'.r2.cloudflarestorage.com')
        self.assertEqual(client.meta.config.region_name,'auto');self.assertEqual(client.meta.config.s3['addressing_style'],'path')
        client.close()
    def published(self,metrics=None):
        doc=pub.load();doc['items'][0].update(state='published',account_id='account1',published_at=10,metrics=metrics or [],url='https://www.instagram.com/reel/one');pub.write(doc)
    def test_metrics_absence_zero_and_negative_correction_are_distinct(self):
        self.published([{'at':20,'values':{'views':5,'likes':0}},{'at':30,'values':{'views':3,'likes':0,'comments':None}}])
        r=insights.rows()[0];self.assertEqual(r['values']['likes'],0);self.assertIsNone(r['values']['comments']);self.assertEqual(r['delta']['views'],-2);self.assertEqual(r['delta']['likes'],0);self.assertIsNone(r['delta']['comments'])
    def test_latest_snapshot_is_not_a_sum_of_all_samples(self):
        self.published([{'at':30,'values':{'views':20}},{'at':10,'values':{'views':5}},{'at':20,'values':{'views':8}}])
        r=insights.rows()[0];self.assertEqual(r['values']['views'],20);self.assertEqual(r['delta']['views'],12);self.assertEqual(r['previous_at'],20)
    def test_drafts_do_not_appear_as_published_results(self):
        self.assertEqual(insights.rows(),[])
        with patch.object(pub,'collect_metrics') as collect:insights.collect(force=True);collect.assert_not_called()
    def test_optional_collection_is_off_and_failures_are_backed_off(self):
        self.published()
        with patch.object(pub,'collect_metrics',side_effect=ValueError('Token scaduto')) as collect:
            insights.collect();collect.assert_not_called()
            insights.settings({'enabled':True,'interval_minutes':15});insights.collect();insights.collect();self.assertEqual(collect.call_count,1)
        self.assertIn(self.post['id'],insights.snapshot()['errors'])
        insights.close();self.assertFalse(insights.snapshot()['enabled']);self.assertNotIn('enabled',insights.load())
    def test_manual_refresh_preserves_missing_counters_and_calls_only_read_path(self):
        self.published()
        with patch.object(pub,'collect_metrics',return_value={'values':{'views':None}}) as collect,patch.object(pub,'deliver') as send:
            insights.collect(force=True);collect.assert_called_once_with({'id':self.post['id']});send.assert_not_called()
    def test_csv_preserves_missing_values_and_escapes_spreadsheet_formulas(self):
        self.published([{'at':20,'values':{'views':0,'likes':None}}]);doc=pub.load();doc['items'][0]['title']='  =HYPERLINK("bad")';pub.write(doc)
        csv=insights.csv_report();self.assertIn("'  =HYPERLINK",csv);self.assertIn(',0,,,',csv)

if __name__=='__main__':unittest.main()

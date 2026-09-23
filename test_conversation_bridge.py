import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import broadcast
import conversation_bridge as bridge
import providers


class ConversationBridgeTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        p=patch.object(broadcast,'PATH',Path(tmp.name)/'broadcast.json');p.start();self.addCleanup(p.stop)
        p=patch.object(broadcast,'ROOMS',{'session':'https://tavus.daily.co/test?t=secret-test-token'});p.start();self.addCleanup(p.stop)
        bridge.LEASES.clear();self.addCleanup(bridge.LEASES.clear)
        self.data={'id':'session','client_id':'a'*24}
        self.messages=[{'id':'m'*16,'state':'review'}]
        providers.atomic_json(broadcast.PATH,{'sessions':[{'id':'session','state':'active','deadline':time.time()+120,'remote_id':'remote-session','character_name':'Ari'}]})
    def issue(self,**kw):return bridge.issue({**self.data,'mode':'echo','text':'Testo rivisto','confirmed':True,**kw},self.messages)
    def test_claim_prevents_two_controllers_and_heartbeat_requires_owner(self):
        self.assertIn('url',bridge.claim(self.data))
        with self.assertRaises(ValueError):bridge.claim({**self.data,'client_id':'b'*24})
        with self.assertRaises(ValueError):bridge.heartbeat({**self.data,'client_id':'b'*24})
        self.assertTrue(bridge.heartbeat(self.data)['ok'])
    def test_end_or_deadline_stops_all_new_commands(self):
        bridge.claim(self.data);broadcast.change('session',{'deadline':time.time()-1})
        for operation in (lambda:bridge.claim(self.data),lambda:bridge.heartbeat(self.data),self.issue):
            with self.assertRaises(ValueError):operation()
        broadcast.change('session',{'deadline':time.time()+60,'state':'ended'})
        with self.assertRaises(ValueError):self.issue()
    def test_echo_and_response_payloads_use_selected_remote_conversation(self):
        bridge.claim(self.data);a=self.issue();b=self.issue(mode='respond',text='Una domanda?')
        self.assertEqual(a['payload'],{'message_type':'conversation','event_type':'conversation.echo','conversation_id':'remote-session','properties':{'modality':'text','text':'Testo rivisto','done':True}})
        self.assertEqual(b['payload']['properties'],{'text':'Una domanda?'})
        self.assertEqual(b['payload']['event_type'],'conversation.respond')
    def test_reference_log_never_stores_chat_text_or_room_token(self):
        bridge.claim(self.data);self.issue(source_message_id='m'*16)
        raw=broadcast.PATH.read_text();self.assertNotIn('Testo rivisto',raw);self.assertNotIn('secret-test-token',raw)
        event=broadcast.load()['sessions'][0]['bridge_events'][0]
        self.assertEqual(event['source_message_id'],'m'*16);self.assertEqual(event['state'],'issued');self.assertEqual(len(event['digest']),64)
    def test_duplicate_source_is_blocked_even_if_text_or_mode_changes(self):
        bridge.claim(self.data);self.issue(source_message_id='m'*16)
        with self.assertRaises(ValueError):self.issue(source_message_id='m'*16,text='Un altro testo',mode='respond')
    def test_duplicate_manual_text_is_blocked_after_uncertain_dispatch(self):
        bridge.claim(self.data);event=self.issue()
        bridge.acknowledge({**self.data,'event_id':event['event_id'],'state':'uncertain'})
        with self.assertRaises(ValueError):self.issue()
    def test_missing_or_dismissed_chat_cannot_be_forwarded(self):
        bridge.claim(self.data)
        with self.assertRaises(ValueError):self.issue(source_message_id='missing')
        self.messages[0]['state']='dismissed'
        with self.assertRaises(ValueError):self.issue(source_message_id='m'*16)
    def test_ack_does_not_claim_spoken_and_cannot_rewrite_uncertain(self):
        bridge.claim(self.data);event=self.issue()
        with self.assertRaises(ValueError):bridge.acknowledge({**self.data,'event_id':event['event_id'],'state':'spoken'})
        result=bridge.acknowledge({**self.data,'event_id':event['event_id'],'state':'uncertain'})
        self.assertEqual(result['state'],'uncertain')
        self.assertEqual(bridge.acknowledge({**self.data,'event_id':event['event_id'],'state':'dispatched'})['state'],'uncertain')
    def test_release_marks_issued_uncertain_without_replay(self):
        bridge.claim(self.data);self.issue();bridge.release(self.data)
        self.assertEqual(broadcast.load()['sessions'][0]['bridge_events'][0]['state'],'uncertain')
        bridge.claim({**self.data,'client_id':'b'*24})
        with self.assertRaises(ValueError):self.issue()
    def test_expired_lease_allows_new_controller_and_marks_pending_uncertain(self):
        bridge.claim(self.data);self.issue();bridge.LEASES['session']['expires']=0
        with self.assertRaises(ValueError):bridge.heartbeat(self.data)
        bridge.claim({**self.data,'client_id':'b'*24})
        self.assertEqual(broadcast.load()['sessions'][0]['bridge_events'][0]['state'],'uncertain')
    def test_restart_preserves_reference_and_disables_controller(self):
        bridge.claim(self.data);self.issue();bridge.recover()
        self.assertEqual(bridge.LEASES,{})
        self.assertEqual(broadcast.load()['sessions'][0]['bridge_events'][0]['state'],'uncertain')
    def test_invalid_confirmation_mode_or_text_never_persists_an_event(self):
        bridge.claim(self.data)
        for fields in ({'confirmed':False},{'mode':'other'},{'text':' '},{'text':'x'*601},{'text':[]},{'source_message_id':[]}):
            with self.assertRaises(ValueError):self.issue(**fields)
        self.assertNotIn('bridge_events',broadcast.load()['sessions'][0])
    def test_interrupt_has_no_text_and_is_throttled(self):
        bridge.claim(self.data);event=self.issue(mode='interrupt')
        self.assertNotIn('properties',event['payload'])
        with self.assertRaises(ValueError):self.issue(mode='interrupt')
    def test_persistence_failure_never_releases_a_command(self):
        bridge.claim(self.data)
        with patch.object(providers,'atomic_json',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.issue()
        self.assertNotIn('bridge_events',broadcast.load()['sessions'][0])


if __name__=='__main__':unittest.main()

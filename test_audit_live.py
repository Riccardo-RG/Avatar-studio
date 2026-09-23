"""Regression checks for live state transitions and external protocol contracts.

All files, sockets, credentials, speech and service responses are isolated fakes.
"""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import broadcast
import live
import live_connectors
import providers
import runtime_config


class LiveAuditTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.now = 1000.
        self.settings = {'voice': 'test-it', 'rate': 160, 'language': 'it',
                         'name': 'Nova', 'character': {'id': 'nova'}}
        def render(settings, identity=None):
            return {**self.settings, 'name': identity or 'nova', 'character': {'id': identity or 'nova'}}
        for p in (patch.object(live.platform_store, 'snapshot', side_effect=lambda identity=None: {'id': identity or 'nova'}),
                  patch.object(live.platform_store, 'render_settings', side_effect=render),
                  patch.object(live.providers, 'settings', return_value=self.settings),
                  patch.object(live.languages, 'apply', side_effect=lambda cfg, data: {**cfg, **data})):
            p.start(); self.addCleanup(p.stop)
        self.d = live.LiveDirector(tmp.name, clock=lambda: self.now, start_thread=False)
        self.d.executor.shutdown()
        self.d.executor = Mock()
        self.addCleanup(self.d.close)
        self.d.catalog = Mock(return_value=[])
        self.d.save_config({'autopilot': False})

    def start(self):
        self.d.claim('first'); self.d.control('start')

    def test_idle_audio_transfer_does_not_invent_a_paused_session(self):
        self.d.claim('first'); self.d.claim('second', force=True)
        self.assertEqual(self.d.phase, 'idle')
        self.assertIsNone(self.d.session_id)
        self.d.control('start')
        self.assertIsNotNone(self.d.session_id)

    def test_expired_audio_owner_transfer_requires_explicit_resume(self):
        self.start(); self.now += 5
        self.assertTrue(self.d.claim('second')['owner'])
        self.assertEqual(self.d.phase, 'paused')
        self.assertFalse(self.d.heartbeat({'client': 'first'})['owner'])

    def test_finished_audio_transfer_keeps_finished_state(self):
        self.start(); self.d.phase = 'finished'
        self.d.claim('second', force=True)
        self.assertEqual(self.d.phase, 'finished')

    def test_full_config_save_can_keep_character_while_live(self):
        self.start()
        self.d.save_config({'character_id': 'nova', 'language': 'it', 'title': 'Titolo aggiornato'})
        self.assertEqual(self.d.config['title'], 'Titolo aggiornato')
        with self.assertRaises(ValueError): self.d.save_config({'character_id': 'ari'})

    def test_duration_limit_releases_character_for_next_prepared_speech(self):
        self.d.save_config({'max_minutes': 1}); self.start()
        self.now += 61; self.d.heartbeat({'client': 'first'}); self.d.tick()
        self.assertEqual(self.d.phase, 'finished')
        self.d.save_config({'character_id': 'ari', 'language': 'es'})
        self.assertEqual(self.d.snapshot()['character_settings']['character']['id'], 'ari')
        self.d.enqueue('Prova', 'Hola.')
        config = self.d.executor.submit.call_args.args[3]
        self.assertEqual(config['character']['id'], 'ari')
        self.assertEqual(config['language'], 'es')

    def test_playlist_end_releases_frozen_character_settings(self):
        self.start()
        self.d.config['autopilot'] = True
        self.d.playlist = [{'id': 'done'}]; self.d.cursor = 1
        self.d.tick()
        self.assertEqual(self.d.phase, 'finished')
        self.assertIsNone(self.d.session_settings)

    def test_removed_reply_can_be_corrected_and_queued_again(self):
        message=self.d.receive('Anna','Una domanda nuova?')
        item=self.d.respond({'id':message['id'],'text':'Prima risposta.'})
        self.d.remove(item['id'])
        self.assertEqual(self.d.messages[-1]['state'],'review')
        replacement=self.d.respond({'id':message['id'],'text':'Risposta corretta.'})
        self.assertNotEqual(item['id'],replacement['id'])
        self.assertEqual(len(self.d.queue),1)
        with patch.object(live.media,'synthesize',side_effect=ValueError('old preparation failed')):
            self.d._prepare(item,self.d.epoch,self.settings,None)
        self.assertEqual(self.d.messages[-1]['state'],'queued')

    def test_stop_restores_queued_chat_but_played_chat_cannot_repeat(self):
        self.start()
        message=self.d.receive('Anna','Una domanda nuova?')
        item=self.d.respond({'id':message['id'],'text':'Risposta.'})
        self.d.control('stop')
        self.assertEqual(self.d.messages[-1]['state'],'review')
        self.d.current=item; self.d._finish('played')
        self.assertEqual(self.d.messages[-1]['state'],'answered')
        with self.assertRaises(ValueError):self.d.respond({'id':message['id'],'text':'Duplicato.'})


class BroadcastAuditTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for p in (patch.object(broadcast, 'PATH', self.root/'broadcast.json'),
                  patch.object(broadcast, 'QUOTES', {}), patch.object(broadcast, 'ROOMS', {}),
                  patch.object(broadcast.store, 'snapshot', return_value={'revision': 1}),
                  patch.object(broadcast.store, 'reserve', return_value='reservation-fixture'),
                  patch.object(broadcast.services, 'config', return_value={'revision': 0}),
                  patch.object(broadcast.services, 'secret', return_value='fixture-key')):
            p.start(); self.addCleanup(p.stop)
        self.quote = {'id': 'quote', 'expires': time.time()+60, 'minutes': 2, 'language': 'es',
                      'context': 'Una conversazione.', 'face_id': 'face1', 'pal_id': 'pal1',
                      'character_id': 'ari', 'character_name': 'Ari', 'character_revision': 1,
                      'estimated_eur': 1, 'missing': []}
        broadcast.QUOTES['quote'] = self.quote
        self.response = {'conversation_id': 'remote123', 'conversation_url': 'https://tavus.daily.co/remote123',
                         'meeting_token': 'fixture-private-token'}

    def test_tavus_language_is_a_provider_setting_not_only_a_prompt(self):
        with patch.object(broadcast.services, 'http', return_value=(self.response, {}, 200)) as http:
            result = broadcast.start({'quote_id': 'quote', 'confirmed': True})
        self.assertEqual(result['state'], 'active')
        self.assertEqual(http.call_args.args[2]['properties']['languages'], ['es'])
        self.assertNotIn('fixture-private-token', broadcast.PATH.read_text())

    def test_changed_tavus_connection_invalidates_quote_before_any_spending(self):
        with patch.object(broadcast.services,'config',return_value={'revision':1}), patch.object(broadcast.services,'http') as http:
            with self.assertRaisesRegex(ValueError,'collegamento o la tariffa'):
                broadcast.start({'quote_id':'quote','confirmed':True})
        broadcast.store.reserve.assert_not_called()
        http.assert_not_called()
        self.assertFalse(broadcast.PATH.exists())

    def test_malformed_join_response_preserves_remote_id_for_recovery(self):
        self.response.pop('meeting_token')
        with patch.object(broadcast.services, 'http', return_value=(self.response, {}, 200)):
            with self.assertRaises(KeyError): broadcast.start({'quote_id': 'quote', 'confirmed': True})
        session = broadcast.load()['sessions'][0]
        self.assertEqual(session['state'], 'uncertain')
        self.assertEqual(session['remote_id'], 'remote123')
        with patch.object(broadcast.services, 'http', return_value=({}, {}, 200)) as http:
            ended = broadcast.end({'id': 'quote'})
        self.assertEqual(ended['state'], 'ended')
        self.assertTrue(http.call_args.args[0].endswith('/remote123/end'))


class ConnectorAuditTests(unittest.TestCase):
    def test_replaced_chat_process_cannot_deliver_late_messages(self):
        director = Mock()
        connectors = live_connectors.ChatConnectors('/fixture', '/fixture/node', director)
        previous = Mock(stdout=[json.dumps({'type': 'message', 'author': 'Old', 'text': 'Old message'})])
        connectors.processes['twitch'] = Mock()
        connectors._read('twitch', previous)
        director.receive.assert_not_called()

    def test_twitch_reconnect_keeps_events_until_new_socket_welcome(self):
        # Evaluate the real bridge with a deterministic WebSocket/fetch runtime.
        node = runtime_config.node()
        if not node: self.skipTest('Node 24 non disponibile')
        script = r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const messages=[],sockets=[],requests=[];
class Socket{constructor(url){this.url=url;sockets.push(this);}close(){this.closed=true;this.onclose?.();}}
const context={require,module:{exports:{}},URL,URLSearchParams,AbortSignal,Date,JSON,
 WebSocket:Socket,setInterval:()=>1,clearInterval:()=>{},setTimeout,
 process:{argv:[],env:{AVATAR_CHAT_TOKEN:'fixture'},stdout:{write:s=>messages.push(JSON.parse(s))}},
 fetch:async(url,options)=>{requests.push(url);return {ok:true,json:async()=>url.includes('validate')?{user_id:'42',client_id:'client',login:'fixture',scopes:['user:read:chat']}:{}};}};
vm.createContext(context);vm.runInContext(fs.readFileSync('chat_bridge.cjs','utf8')+';globalThis.auditTwitch=twitch;',context);
const event=(kind,payload,extra={})=>({data:JSON.stringify({metadata:{message_type:kind,...extra},payload})});
const welcome=event('session_welcome',{session:{id:'fixture-session',keepalive_timeout_seconds:30}});
const chat=id=>event('notification',{event:{broadcaster_user_id:'42',chatter_user_name:'Ada',chatter_user_id:'7',message_id:id,message:{text:'hello'}}},{subscription_type:'channel.chat.message'});
(async()=>{
 await context.auditTwitch();const old=sockets[0];await old.onmessage(welcome);
 await old.onmessage(event('session_reconnect',{session:{reconnect_url:'wss://eventsub.wss.twitch.tv/ws?session=next'}}));
 const replacement=sockets[1];assert.equal(old.closed,undefined);
 await old.onmessage(chat('during-handover'));
 assert(messages.some(m=>m.event_id==='during-handover'),'Notification lost while replacement socket opens');
 await replacement.onmessage(welcome);assert.equal(old.closed,true);
 await old.onmessage(chat('stale'));await replacement.onmessage(chat('new-socket'));
 assert(!messages.some(m=>m.event_id==='stale'));assert(messages.some(m=>m.event_id==='new-socket'));
 assert.equal(requests.filter(u=>u.includes('/subscriptions')).length,1,'Must not resubscribe on server handover');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        result = subprocess.run([node, '-e', script], cwd=Path(__file__).resolve().parent,
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__': unittest.main()

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import languages
import media
import providers
import platform_store as store
import productions
import studio
import packages
import social_adapters
from live import LiveDirector

CATALOG=[{'id':'piper:paola','language':'it','locale':'it-IT'},{'id':'Alice','language':'it','locale':'it-IT'},{'id':'Samantha','language':'en','locale':'en-US'},{'id':'Daniel','language':'en','locale':'en-GB'},{'id':'Mónica','language':'es','locale':'es-ES'}]

class LanguageTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        for module,key,value in [(store,'PATH',self.root/'platform.json'),(studio,'PATH',self.root/'studio.json')]:
            p=patch.object(module,key,value);p.start();self.addCleanup(p.stop)
        p=patch.object(media,'voice_catalog',return_value=CATALOG);p.start();self.addCleanup(p.stop)
        self.config=store.render_settings(providers.settings(),'lumo')
    def test_matching_voice_is_chosen_without_mutating_character(self):
        original=copy.deepcopy(self.config)
        self.assertEqual(languages.apply(self.config,{'language':'en'})['voice'],'Samantha')
        self.assertEqual(languages.apply(self.config,{'language':'es'})['voice'],'Mónica')
        self.assertEqual(self.config,original)
    def test_explicit_wrong_language_voice_is_rejected(self):
        with self.assertRaises(ValueError):languages.apply(self.config,{'language':'en','voice':'piper:paola'})
        with self.assertRaises(ValueError):languages.apply(self.config,{'language':'fr'})
    def test_missing_voice_never_falls_back_to_another_language(self):
        with self.assertRaises(ValueError):languages.apply(self.config,{'language':'es'},catalog=CATALOG[:2])
    def test_per_character_foreign_voices_are_independent_and_versioned(self):
        c=store.snapshot('lumo');saved=store.save_character({**c,'voice_en':'Daniel','voice_es':'Mónica'},[v['id'] for v in CATALOG])
        config=store.render_settings(providers.settings(),'lumo')
        self.assertEqual(languages.apply(config,{'language':'en'})['voice'],'Daniel')
        self.assertNotIn('voices_by_language',store.snapshot('ari'));self.assertGreater(saved['revision'],c['revision'])
        with self.assertRaises(ValueError):store.save_character({**saved,'voice_en':'Alice'},[v['id'] for v in CATALOG])
    def test_profile_main_voice_remains_italian(self):
        c=store.snapshot('lumo')
        with self.assertRaises(ValueError):store.save_character({**c,'voice':'Samantha'},[v['id'] for v in CATALOG])
    def test_script_prompt_overrides_old_italian_personality_instruction(self):
        config={**self.config,'language':'es','provider':'openai','editorial_context':'Il personaggio parla in italiano.'}
        reply={'choices':[{'message':{'content':'Hola. Esta es una historia breve.'},'finish_reason':'stop'}]}
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test'}),patch.object(providers,'reserve_budget',return_value=0),patch.object(providers,'request_json',return_value=reply) as request:
            result=providers.generate_script('una storia breve',15,config)
        payload=request.call_args.args[1];self.assertIn('español natural',payload['messages'][0]['content']);self.assertIn('priorità',payload['messages'][0]['content']);self.assertEqual(result['script'],'Hola. Esta es una historia breve.')
    def test_translation_is_returned_for_review_and_uses_bounded_local_generation(self):
        original='Ciao, questa è una prova.'
        with patch.object(providers,'agent_text',return_value='Hello, this is a test.') as model:
            result=providers.translate_script(original,{**self.config,'language':'en','provider':'local'})
        self.assertEqual(result['language'],'en');self.assertIn('da rileggere',result['note']);self.assertEqual(model.call_args.kwargs['max_tokens'],1200);self.assertIn(original,model.call_args.args[1])
    def test_translation_input_and_output_are_bounded(self):
        with patch.object(providers,'agent_text') as model:
            for text in ('','x'*1801):
                with self.assertRaises(ValueError):providers.translate_script(text,{**self.config,'language':'en'})
            model.assert_not_called()
        with patch.object(providers,'agent_text',return_value=''):
            with self.assertRaises(ValueError):providers.translate_script('Un testo',{**self.config,'language':'en','provider':'local'})
    def test_episode_language_survives_other_edits(self):
        e=studio.save_episode({'title':'Test','script':'Hello from Lumo.','character_id':'lumo','language':'en'})
        self.assertEqual(e['language'],'en');self.assertEqual(studio.save_episode({**e,'title':'Edited'})['language'],'en')
    def test_campaign_language_is_explicit(self):
        c=store.save_campaign({'name':'Test','topic':'Creatività','audience':'Spagna','objective':'Una prova','language':'es'})
        self.assertEqual(c['language'],'es')
    def test_montage_keeps_language_and_voice_for_each_scene(self):
        p=productions.prepare({'scenes':[{'script':'Hello.','character_id':'lumo','language':'en'},{'script':'Hola.','character_id':'ari','language':'es'}]},[v['id'] for v in CATALOG])
        self.assertEqual([s['settings']['voice'] for s in p['scenes']],['Samantha','Mónica'])
        self.assertEqual([s['settings']['language'] for s in p['scenes']],['en','es'])
    def test_live_language_is_independent_and_change_disables_old_auto_replies(self):
        director=LiveDirector(self.root,start_thread=False)
        try:
            director.save_config({'language':'en','auto_replies':True});self.assertFalse(director.config['auto_replies'])
            self.assertEqual(director.snapshot()['character_settings']['voice'],'Samantha')
            director.phase='running'
            with self.assertRaises(ValueError):director.save_config({'language':'es'})
        finally:director.close()
    def test_language_metadata_and_disclosure_match_video(self):
        for lang,phrase in [('en','Virtual character.'),('es','Personaje virtual.')]:
            p={'title':'Test','settings':{**self.config,'language':lang},'script':'A test.'}
            meta=packages.metadata(p)
            self.assertIn(phrase,meta['youtube']['description']);self.assertEqual(meta['youtube']['language'],lang)
            item={'title':'Test','description':'Test','visibility':'private','made_for_kids':False,'language':lang}
            self.assertEqual(social_adapters.youtube_metadata(item)['snippet']['defaultLanguage'],lang)

if __name__=='__main__':unittest.main()

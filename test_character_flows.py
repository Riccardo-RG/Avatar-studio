"""Regression coverage for isolated identities, migration and frozen productions."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import platform_store as store
import providers
import studio
import live
import media


class CharacterFlowTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / 'data').mkdir()
        for target, key, value in (
            (store, 'PATH', self.root / 'data/platform.json'),
            (providers, 'DATA', self.root / 'data'),
            (studio, 'PATH', self.root / 'data/studio.json'),
            (studio, 'ROOT', self.root),
        ):
            p = patch.object(target, key, value)
            p.start()
            self.addCleanup(p.stop)
        self.voices = ['Alice', 'piper:paola']
        p=patch.object(media,'voice_catalog',return_value=[{'id':v,'language':'it','locale':'it-IT'} for v in self.voices])
        p.start();self.addCleanup(p.stop)

    def test_legacy_name_cannot_relabel_another_character(self):
        providers.save_settings({'name':'Lumo','color':'#3b6ab0'}, self.voices)
        old = store.fresh()
        for c in old['characters']:
            c.pop('color'); c.pop('background')
        store.write(old)
        result = store.render_settings(providers.settings())
        self.assertEqual((result['name'], result['character']['id']), ('Nova', 'nova'))
        self.assertEqual(result['color'], '#3b6ab0')
        self.assertEqual(store.render_settings(providers.settings(), 'lumo')['character']['kind'], 'illustrated')
        self.assertEqual(store.load()['version'], 2)

    def test_studio_preferences_cannot_change_character_properties(self):
        before = store.snapshot('lumo')
        prefs = providers.save_studio_settings({'name':'Confuso','voice':'Alice','accent':'#ffffff','resolution':540}, self.voices)
        after = store.render_settings(providers.settings(), 'lumo')
        self.assertEqual(after['character'], before)
        self.assertEqual(after['resolution'], 540)
        self.assertNotIn('voice', prefs)
        self.assertNotIn('name', prefs)

    def test_appearance_edits_are_isolated_and_old_render_stays_frozen(self):
        nova = store.snapshot('nova'); lumo = store.snapshot('lumo')
        frozen = store.render_settings(providers.settings(), 'nova')
        store.save_character({**nova,'color':'#112233','background':'#223344','voice':'Alice','rate':180}, self.voices)
        self.assertEqual(store.snapshot('lumo'), lumo)
        self.assertEqual(frozen['color'], nova['color'])
        self.assertEqual(store.snapshot('nova')['color'], '#112233')
        self.assertEqual(store.load()['characters'][0]['history'][0]['color'], nova['color'])

    def test_duplicate_has_own_identity_and_does_not_mutate_source(self):
        original = store.snapshot('lumo')
        saved = store.save_character({**original,'id':'','name':'Lumo copia'}, self.voices)
        self.assertNotEqual(saved['id'], original['id'])
        self.assertEqual(store.snapshot('lumo'), original)
        self.assertEqual(saved['history'], [])

    def test_personality_context_is_character_specific(self):
        lumo = store.snapshot('lumo')
        editorial = {**lumo['editorial'], 'concept':'Un esploratore di mondi di carta.'}
        store.save_character({**lumo,'editorial':editorial}, self.voices)
        self.assertIn('mondi di carta', studio.prompt_context('domanda','lumo'))
        self.assertNotIn('mondi di carta', studio.prompt_context('domanda','nova'))

    def test_legacy_editorial_profile_is_preserved_for_nova_only(self):
        doc = studio.fresh(); doc['persona']['concept'] = 'Il robot che studia le abitudini umane.'
        providers.atomic_json(studio.PATH, doc)
        self.assertEqual(store.snapshot('nova')['editorial']['concept'], doc['persona']['concept'])
        self.assertNotEqual(store.snapshot('lumo')['editorial']['concept'], doc['persona']['concept'])

    def test_episode_cast_stays_explicit_after_active_character_changes(self):
        e = studio.save_episode({'title':'Prova','script':'Una piccola storia.','character_id':'lumo'})
        store.activate('ari')
        updated = studio.save_episode({**e, 'title':'Nuovo titolo'})
        self.assertEqual(updated['character_id'], 'lumo')
        with self.assertRaises(ValueError):
            studio.save_episode({**updated,'character_id':''})

    def test_legacy_episode_migration_uses_completed_project_identity(self):
        doc = studio.fresh(); e=doc['episodes'][0]; e.pop('character_id'); e['job_id']='a'*12
        folder=self.root/'output'/e['job_id'];folder.mkdir(parents=True)
        providers.atomic_json(folder/'project.json',{'settings':{'character':{'id':'ari'}}})
        providers.atomic_json(studio.PATH,doc)
        self.assertEqual(studio.load()['episodes'][0]['character_id'],'ari')

    def test_live_cast_does_not_follow_video_default(self):
        director=live.LiveDirector(self.root,start_thread=False)
        self.addCleanup(director.close)
        self.assertEqual(director.config['character_id'],'nova')
        store.activate('lumo')
        self.assertEqual(director.snapshot()['character_settings']['character']['id'],'nova')

if __name__ == '__main__':
    unittest.main()

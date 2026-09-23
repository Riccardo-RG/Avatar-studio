import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

import media
import packages
import providers
import studio


class EditorialTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.patch=patch.object(studio,'PATH',Path(self.temp.name)/'studio.json')
        self.patch.start();self.addCleanup(self.patch.stop)

    def test_stale_edit_cannot_overwrite_newer_script(self):
        old=studio.load()['episodes'][0]
        updated=studio.save_episode({**old,'script':'Questo è il nuovo testo.'})
        self.assertEqual(updated['revision'],2)
        with self.assertRaisesRegex(ValueError,'altra finestra'):
            studio.save_episode(old)
        self.assertEqual(studio.load()['episodes'][0]['script'],'Questo è il nuovo testo.')

    def test_running_revision_cannot_replace_edited_draft(self):
        e=studio.load()['episodes'][0]
        studio.set_ready(e['id'],1)
        selected,_,_=studio.claim_episodes([e['id']])
        revised=studio.save_episode({**e,'script':'Questo è un copione cambiato durante il rendering.'})
        studio.finish_episode(e['id'],1,'old-job',True)
        self.assertEqual(studio.load()['episodes'][0],revised)

    def test_batch_validation_is_atomic(self):
        a,b=studio.load()['episodes'][:2]
        studio.set_ready(a['id'],1)
        with self.assertRaisesRegex(ValueError,'pronti'):
            studio.claim_episodes([a['id'],b['id']])
        self.assertEqual(studio.load()['episodes'][0]['status'],'approved')

    def test_duplicate_scripts_are_not_produced_in_batch(self):
        a,b=studio.load()['episodes'][:2]
        b=studio.save_episode({**b,'script':a['script']})
        for e in [a,b]:studio.set_ready(e['id'],e['revision'])
        with self.assertRaisesRegex(ValueError,'stesso copione'):
            studio.claim_episodes([a['id'],b['id']])
        self.assertEqual(studio.load()['episodes'][0]['status'],'approved')

    def test_snapshot_persona_and_rubric_are_independent(self):
        e=studio.load()['episodes'][0];studio.set_ready(e['id'],1)
        episodes,persona,rubrics=studio.claim_episodes([e['id']])
        studio.save_persona({'tone':'Una nuova voce narrativa.'})
        studio.save_rubric({'id':'umani','name':'Nuovo nome'})
        self.assertNotEqual(persona['tone'],studio.load()['persona']['tone'])
        self.assertNotEqual(rubrics[0]['name'],studio.load()['rubrics'][0]['name'])
        self.assertEqual(episodes[0]['script'],e['script'])

    def test_failure_is_retryable_and_restart_recovers_queue(self):
        e=studio.load()['episodes'][0];studio.set_ready(e['id'],1)
        studio.claim_episodes([e['id']]);studio.finish_episode(e['id'],1,'failed-job',False)
        self.assertEqual(studio.load()['episodes'][0]['status'],'approved')
        studio.claim_episodes([e['id']]);studio.recover_interrupted()
        self.assertEqual(studio.load()['episodes'][0]['status'],'approved')

    def test_prompt_uses_saved_persona_and_selected_rubric(self):
        studio.save_persona({'tone':'Tono speciale per il test.'})
        context=studio.prompt_context('domanda')
        self.assertIn('Tono speciale',context);self.assertIn('Domanda impossibile',context)
        self.assertNotIn('Manuale degli umani',context)

    def test_ai_receives_editorial_context(self):
        captured=[]
        def fake_run(command, **kwargs):
            captured.append(Path(command[command.index('-f')+1]).read_text())
            return SimpleNamespace(returncode=0,stdout='Un copione per il test.')
        model=Path(self.temp.name)/'models/qwen2.5-1.5b-instruct-q4_k_m.gguf'
        model.parent.mkdir(exist_ok=True);model.touch()
        executable=model.parent/'llama';executable.touch()
        with patch.object(providers,'ROOT',model.parent.parent),patch.object(providers.runtime_config,'llama',return_value=str(executable)),patch.object(providers.subprocess,'run',side_effect=fake_run):
            providers.generate_script('Un piccolo tema',15,{**providers.DEFAULTS,'editorial_context':'Personaggio curioso.'})
        self.assertIn('Personaggio curioso.',captured[0])


    def test_caption_alignment_preserves_words_with_and_without_boundaries(self):
        text='Una frase abbastanza lunga per richiedere una divisione dei sottotitoli senza perdere neppure una parola.'
        words=text.split();align=[{'phoneme':' ','end':i} for i in range(1,len(words))]
        exact,method=media.sentence_captions(text,len(words),align)
        self.assertEqual(method,'phoneme_boundaries')
        approximate,method=media.sentence_captions(text,8,[])
        self.assertEqual(method,'sentence_estimate')
        for caps in [exact,approximate]:
            self.assertEqual(' '.join(c['text'] for c in caps),text)
            self.assertTrue(all(c['start']<c['end'] for c in caps))
            self.assertTrue(all(a['end']<=b['start'] for a,b in zip(caps,caps[1:])))

    def test_packages_contain_distinct_texts_and_identical_media(self):
        folder=Path(self.temp.name)/'aabbccddeeff';folder.mkdir()
        for filename in ['video.mp4','cover.png','captions.srt']:(folder/filename).write_bytes(b'test-asset')
        project={'script':'Un test. E una domanda?','settings':{'name':'NOVA'},'title':'Un titolo','episode':{'question':'Quale scegli?'}}
        bundles=packages.make_packages(folder,project)
        descriptions=set()
        for platform in bundles:
            with zipfile.ZipFile(folder/f'{platform}.zip') as archive:
                self.assertEqual(archive.read('video.mp4'),b'test-asset')
                self.assertIn('cover.png',archive.namelist())
                info=json.loads(archive.read('metadata.json'))
                descriptions.add(info['description'])
                self.assertIn('Voce sintetica',info['description'])
        self.assertEqual(len(descriptions),3)


if __name__=='__main__':unittest.main()

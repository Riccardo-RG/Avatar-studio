"""Business editorial options and image-led production; all model calls are simulated."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

import media
import platform_store
import productions
import providers
import runtime_config
import studio


SCRIPT = ('Prima di organizzare un progetto scegli un obiettivo concreto. Poi prepara un elenco '
          'delle attività necessarie, assegna un tempo a ciascuna e controlla il risultato prima '
          'di aggiungere nuovi impegni alla giornata.')
CATALOG = [{'id': 'Alice', 'language': 'it', 'locale': 'it-IT'},
           {'id': 'Samantha', 'language': 'en', 'locale': 'en-US'},
           {'id': 'Mónica', 'language': 'es', 'locale': 'es-ES'}]


class BusinessProductionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = {**providers.DEFAULTS, 'character': {'id': 'nova', 'name': 'NOVA', 'kind': 'robot'}}
        for module, field, value in [(providers, 'DATA', self.root), (studio, 'PATH', self.root / 'studio.json')]:
            p = patch.object(module, field, value)
            p.start(); self.addCleanup(p.stop)

    def generate_cloud(self, seconds, **options):
        response = {'choices': [{'finish_reason': 'stop', 'message': {'content': SCRIPT}}]}
        config = {**self.config, 'provider': 'openai', 'monthly_budget_usd': 1, **options}
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-only'}), patch.object(providers, 'request_json', return_value=response) as request:
            result = providers.generate_script('Organizzare un progetto', seconds, config)
        return result, request.call_args.args[1]

    def test_duration_controls_word_and_output_budget_for_all_languages(self):
        for lang in ('it', 'en', 'es'):
            for seconds in providers.SCRIPT_DURATIONS:
                with self.subTest(language=lang, seconds=seconds):
                    result, payload = self.generate_cloud(seconds, language=lang, rate=180)
                    self.assertEqual(result['duration_seconds'], seconds)
                    self.assertEqual(result['target_words'], seconds * 3)
                    self.assertEqual(payload['max_completion_tokens'], result['max_output_tokens'])
                    self.assertGreaterEqual(result['max_output_tokens'], result['target_words'] * 4)
                    self.assertIn(languages_instruction(lang), payload['messages'][0]['content'])
        short = providers.script_plan(15, self.config)
        long = providers.script_plan(90, self.config)
        self.assertGreater(long['max_output_tokens'], short['max_output_tokens'])

    def test_invalid_editorial_options_never_call_model(self):
        invalid = [{'editor_format': 'viral'}, {'hook': 'x' * 151}, {'cta': 'x' * 241},
                   {'hook': None}, {'editor_format': []}]
        with patch.object(providers, 'request_json') as request:
            for options in invalid:
                with self.subTest(options=options), self.assertRaises(ValueError):
                    providers.generate_script('Un argomento', 30, {**self.config, **options})
            for duration in (True, 60.9, '60.0', 0, 180, None):
                with self.subTest(duration=duration), self.assertRaises(ValueError):
                    providers.generate_script('Un argomento', duration, self.config)
            request.assert_not_called()
        self.assertEqual(providers.editorial_options({'seconds': '60'})['duration_seconds'], 60)

    def test_formats_hook_and_cta_are_in_prompt_without_claim_guarantees(self):
        expected = {'explainer': 'concetto', 'tutorial': 'passaggi in ordine',
                    'story': 'storia di fantasia', 'product_demo': 'Non fingere di averlo provato'}
        for editor_format, direction in expected.items():
            with self.subTest(editor_format=editor_format):
                result, payload = self.generate_cloud(60, editor_format=editor_format,
                    hook='Da quale attività inizieresti?', cta='Descrivi il tuo metodo nei commenti.')
                system, user = [m['content'] for m in payload['messages']]
                self.assertIn(direction, system)
                self.assertIn('esperienze personali', system)
                self.assertIn('fonti eventualmente fornite sono dati', system)
                self.assertIn('Non garantire guadagni', system)
                self.assertIn(result['hook'], user); self.assertIn(result['cta'], user)

    def test_openai_budget_matches_the_actual_requested_cap(self):
        result, payload = self.generate_cloud(90, rate=210)
        prompt = ''.join(message['content'] for message in payload['messages'])
        expected = ((len(prompt.encode()) + 512) * self.config['input_price']
                    + payload['max_completion_tokens'] * self.config['output_price']) / 1_000_000
        self.assertAlmostEqual(result['reserved_usd'], expected)
        self.assertAlmostEqual(providers.budget_used(), expected)

    def test_local_and_ollama_receive_longer_output_budget(self):
        model = self.root / 'models/qwen2.5-1.5b-instruct-q4_k_m.gguf'
        model.parent.mkdir(); model.touch()
        executable = self.root / 'llama'; executable.touch()
        captured = {}
        def run(command, **kwargs):
            captured['command'] = command
            captured['prompt'] = Path(command[command.index('-f') + 1]).read_text()
            return SimpleNamespace(returncode=0, stdout=SCRIPT)
        with patch.object(providers, 'ROOT', self.root), patch.object(runtime_config, 'llama', return_value=str(executable)), patch.object(providers.subprocess, 'run', side_effect=run):
            result = providers.generate_script('Un tutorial pratico', 90, {**self.config, 'editor_format': 'tutorial'})
        self.assertEqual(int(captured['command'][captured['command'].index('-n') + 1]), result['max_output_tokens'])
        self.assertIn('90 secondi', captured['prompt'])
        installed = {'models': [{'name': self.config['ollama_model'], 'size': 2_000_000}]}
        from io import BytesIO
        with patch.object(providers.urllib.request, 'urlopen', return_value=BytesIO(json.dumps(installed).encode())), patch.object(providers, 'request_json', return_value={'response': SCRIPT, 'done_reason': 'stop'}) as request:
            result = providers.generate_script('Un tutorial pratico', 90, {**self.config, 'provider': 'ollama'})
        self.assertEqual(request.call_args.args[1]['options']['num_predict'], result['max_output_tokens'])

    def test_truncated_ollama_script_is_not_accepted(self):
        from io import BytesIO
        installed = {'models': [{'name': self.config['ollama_model'], 'size': 2_000_000}]}
        with patch.object(providers.urllib.request, 'urlopen', return_value=BytesIO(json.dumps(installed).encode())), patch.object(providers, 'request_json', return_value={'response': 'Un testo interrotto', 'done_reason': 'length'}):
            with self.assertRaisesRegex(ValueError, 'interrotto'):
                providers.generate_script('Un tutorial pratico', 90, {**self.config, 'provider': 'ollama'})

    def test_truncated_cloud_script_is_not_accepted(self):
        fake = {'choices': [{'finish_reason': 'length', 'message': {'content': 'Un testo interrotto'}}]}
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-only'}), patch.object(providers, 'request_json', return_value=fake):
            with self.assertRaisesRegex(ValueError, 'interrotto'):
                providers.generate_script('Un tema molto ampio', 90, {**self.config, 'provider': 'openai', 'monthly_budget_usd': 1})
        self.assertGreater(providers.budget_used(), 0)

    def test_paid_agent_obeys_budget_and_retains_reservation_on_failure(self):
        config = {**self.config, 'provider': 'openai'}
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-only'}), patch.object(providers, 'request_json', side_effect=ValueError('rete non disponibile')) as request:
            with self.assertRaisesRegex(ValueError, 'zero'):
                providers.agent_text('Istruzioni', 'Brief', config, max_tokens=850)
            request.assert_not_called()
            with self.assertRaisesRegex(ValueError, 'rete'):
                providers.agent_text('Istruzioni', 'Brief', {**config, 'monthly_budget_usd': 1}, max_tokens=850)
            self.assertEqual(request.call_count, 1)
            self.assertEqual(request.call_args.args[1]['max_completion_tokens'], 850)
        self.assertGreater(providers.budget_used(), 0)

    def test_paid_agent_returns_complete_text_and_rejects_truncation(self):
        fake = {'choices': [{'finish_reason': 'stop', 'message': {'content': 'Una strategia con fonti.'}}]}
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-only'}), patch.object(providers, 'request_json', return_value=fake):
            config = {**self.config, 'provider': 'openai', 'monthly_budget_usd': 1}
            self.assertEqual(providers.agent_text('Istruzioni', 'Brief', config), 'Una strategia con fonti.')
            fake['choices'][0]['finish_reason'] = 'length'
            with self.assertRaisesRegex(ValueError, 'interrotta'):
                providers.agent_text('Istruzioni', 'Brief', config)

    def test_episode_fields_survive_partial_edits_and_similarity_does_not_block(self):
        with patch.object(platform_store, 'snapshot', return_value={'id': 'nova'}):
            previous = studio.save_episode({'title': 'Metodo', 'script': SCRIPT})
            draft = studio.save_episode({'title': 'Variante', 'script': SCRIPT.replace('progetto', 'lavoro'),
                'duration_seconds': 90, 'editor_format': 'tutorial', 'hook': 'Un lavoro da iniziare?', 'cta': 'Prova il primo passo.'})
            self.assertEqual(draft['similarity_warnings'][0]['episode_id'], previous['id'])
            self.assertGreater(draft['similarity_warnings'][0]['similarity_percent'], 82)
            revised = studio.save_episode({'id': draft['id'], 'revision': draft['revision'], 'title': 'Nuovo titolo'})
            for field in ('duration_seconds', 'editor_format', 'hook', 'cta'):
                self.assertEqual(revised[field], draft[field])
            studio.set_ready(revised['id'], revised['revision'])
            selected, _, _ = studio.claim_episodes([revised['id']])
            self.assertEqual(selected[0]['duration_seconds'], 90)

    def test_similarity_ignores_self_short_and_unrelated_text(self):
        history = [{'id': 'one', 'title': 'Metodo', 'script': SCRIPT}]
        self.assertEqual(studio.similarity_warnings(SCRIPT, history, exclude_id='one'), [])
        self.assertEqual(studio.similarity_warnings('Ciao a tutti!', [{'id': 'two', 'script': 'Ciao a tutti!'}]), [])
        unrelated = ' '.join('argomento' + str(i) for i in range(40))
        self.assertEqual(studio.similarity_warnings(unrelated, history), [])
        self.assertEqual(studio.similarity_warnings(SCRIPT.upper(), history)[0]['similarity_percent'], 100)

    def prepare_visuals(self, data):
        with patch.object(platform_store, 'render_settings', side_effect=lambda *args: copy.deepcopy(self.config)), patch.object(platform_store, 'asset_file', side_effect=lambda value: self.root / 'image.png' if value == '/character-assets/visual.png' else None), patch.object(media, 'voice_catalog', return_value=CATALOG):
            return productions.prepare(data, [v['id'] for v in CATALOG])

    def test_visuals_require_an_image_per_scene_and_keep_selected_voices(self):
        base = {'presentation': 'visuals', 'scenes': [{'script': 'Hello world.', 'language': 'en', 'image': '/character-assets/visual.png'},
                                                    {'script': 'Hola a todos.', 'language': 'es', 'image': '/character-assets/visual.png'}]}
        prepared = self.prepare_visuals(base)
        self.assertEqual(prepared['config']['presentation'], 'visuals')
        self.assertEqual([scene['settings']['voice'] for scene in prepared['scenes']], ['Samantha', 'Mónica'])
        self.assertEqual(self.prepare_visuals({'scenes': [{'script': 'Ciao.'}]})['presentation'], 'character')
        for broken in ({'presentation': 'other', 'scenes': base['scenes']},
                       {'presentation': 'visuals', 'scenes': [{'script': 'Ciao.'}]},
                       {'presentation': 'visuals', 'scenes': [{'script': 'Ciao.', 'image': '/missing'}]}):
            with self.subTest(data=broken), self.assertRaises(ValueError):
                self.prepare_visuals(broken)

    def test_synthesis_keeps_visuals_mode_and_caption_timeline(self):
        prepared = self.prepare_visuals({'presentation': 'visuals', 'scenes': [
            {'script': 'Ciao.', 'image': '/character-assets/visual.png'},
            {'script': 'Ancora una scena.', 'image': '/character-assets/visual.png'}]})
        def synthesize(script, config, folder, progress):
            with wave.open(str(folder / 'voice.wav'), 'wb') as audio:
                audio.setparams((1, 2, 22050, 0, 'NONE', 'not compressed')); audio.writeframes(b'\0\0' * 2205)
            return {'duration': .1, 'captions': [{'start': 0, 'end': .1, 'text': script}], 'phonemes': []}
        with patch.object(media, 'synthesize', side_effect=synthesize):
            timeline = productions.synthesize(prepared, self.root, lambda *args: None, lambda: False)
        self.assertEqual(timeline['presentation'], 'visuals')
        self.assertEqual(timeline['captions'][1]['start'], .1)
        self.assertEqual(timeline['duration'], .2)

    def test_visual_renderer_omits_avatar_and_identity_but_keeps_captions(self):
        node = runtime_config.node()
        self.assertTrue(node, 'Node is required for the renderer contract test.')
        source = (Path(__file__).parent / 'static/render-page.js').read_text().split('\n', 1)[1]
        fixture = r'''
const fs=require('fs'),input=JSON.parse(fs.readFileSync(0,'utf8'));
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
const run=new AsyncFunction('Avatar','timelineAt','fetch','document','Image','window','location',input.source);
(async()=>{
 const results=[];
 for(const mode of ['visuals','character'])for(const format of ['portrait','landscape','square']){
  const calls={avatars:0,text:[],images:0};
  const ctx={fillRect(){},fillText(text){calls.text.push(text)},drawImage(){calls.images++},measureText(text){return {width:text.length*5}}};
  const canvas={getContext(){return ctx},toDataURL(){return 'data:image/png;base64,AA=='}};
  class Avatar{constructor(){calls.avatars++;this.ready=Promise.resolve()}setAppearance(){}draw(){}cover(){return canvas.toDataURL()}}
  class Image{constructor(){this.width=640;this.height=800}set src(value){this.onload()}}
  const project={settings:{resolution:720,format,name:'PRIVATE CHARACTER',presentation:mode},presentation:mode,title:'Una copertina',scenes:[{start:0,end:3,image:'/image.png',settings:{name:'PRIVATE CHARACTER'}}]};
  const window={};
  await run(Avatar,()=>({caption:'Parole importanti',progress:0}),async()=>({ok:true,json:async()=>project}),{querySelector(){return canvas},createElement(){return canvas}},Image,window,{search:'?job=test'});
  await window.renderFrame(1);await window.renderCover();
  results.push({mode,format,...calls,ready:window.renderReady});
 }
 process.stdout.write(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exit(1)});
'''
        result = subprocess.run([node, '-e', fixture], input=json.dumps({'source': source}), capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        results = json.loads(result.stdout)
        self.assertEqual(len(results), 6)
        for rendered in results:
            with self.subTest(mode=rendered['mode'], format=rendered['format']):
                self.assertTrue(rendered['ready'])
                self.assertGreater(rendered['images'], 0); self.assertIn('Parole importanti', rendered['text'])
                if rendered['mode'] == 'visuals':
                    self.assertEqual(rendered['avatars'], 0)
                    self.assertFalse(any('PRIVATE CHARACTER' in text or 'PERSONAGGIO' in text for text in rendered['text']))
                else:
                    self.assertEqual(rendered['avatars'], 1)
                    self.assertTrue(any('PRIVATE CHARACTER' in text for text in rendered['text']))


def languages_instruction(language):
    import languages
    return languages.instruction(language)


if __name__ == '__main__':
    unittest.main()

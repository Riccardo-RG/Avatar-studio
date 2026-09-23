import copy
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import clips
import media
import packages
import platform_store
import providers

class ClipTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        for module,field,value in [(clips,'ROOT',self.root),(platform_store,'PATH',self.root/'platform.json')]:
            p=patch.object(module,field,value);p.start();self.addCleanup(p.stop)
        self.id='a'*12;self.folder=self.root/'data/recordings'/self.id;self.folder.mkdir(parents=True)
        (self.folder/'source.mp4').write_bytes(b'video')
        self.meta={'id':self.id,'title':'Registrazione','duration':60,'created':1,'captions':[{'start':4,'end':8,'text':'Prima frase'},{'start':9,'end':12,'text':'Seconda frase'}]}
        providers.atomic_json(self.folder/'recording.json',self.meta)
    def data(self,**kwargs):return {'source_id':'recording:'+self.id,'title':'Clip','start':6,'end':10,**kwargs}
    def test_cut_trims_and_retimes_subtitles_without_changing_source(self):
        p=clips.prepare(self.data())
        self.assertEqual(p['captions'],[{'start':0,'end':2,'text':'Prima frase'},{'start':3,'end':4,'text':'Seconda frase'}])
        self.assertTrue(p['burn_captions']);self.assertFalse(p['captions_burned'])
        self.assertEqual(json.loads((self.folder/'recording.json').read_text())['captions'],self.meta['captions'])
    def test_existing_visible_subtitles_are_never_burned_twice(self):
        p=clips.prepare(self.data(source_captions_burned=True))
        self.assertTrue(p['captions_burned']);self.assertFalse(p['burn_captions'])
    def test_no_srt_means_no_invented_subtitles(self):
        self.meta['captions']=[];providers.atomic_json(self.folder/'recording.json',self.meta)
        p=clips.prepare(self.data());self.assertEqual(p['captions'],[]);self.assertFalse(p['burn_captions'])
    def test_rejects_out_of_range_nonfinite_and_long_cuts(self):
        for fields in ({'start':-1},{'end':61},{'start':9.5},{'start':'NaN'},{'position':1.1},{'format':'other'}):
            with self.assertRaises(ValueError):clips.prepare(self.data(**fields))
        self.meta['duration']=1000;providers.atomic_json(self.folder/'recording.json',self.meta)
        with self.assertRaises(ValueError):clips.prepare(self.data(end=200))
    def test_source_paths_cannot_escape_recordings(self):
        for identity in ['recording:../../settings','https://example.com','job:/tmp','recording:'+self.id+'/../']:
            with self.assertRaises(ValueError):clips.source(identity)
    def test_import_is_chunked_and_preserves_file_extension(self):
        raw=b'fixture-video'
        with patch.object(clips,'probe',return_value={'duration':5,'width':320,'height':180,'audio':True}):
            item=clips.import_stream(io.BytesIO(raw),len(raw),'a recording.webm')
        self.assertTrue(item['url'].endswith('/source.webm'));self.assertEqual(clips.source(item['source_id'])[0].read_bytes(),raw)
    def test_interrupted_import_removes_only_its_partial_copy(self):
        before=set(self.folder.parent.iterdir())
        with self.assertRaises(ValueError):clips.import_stream(io.BytesIO(b'short'),100,'recording.mp4')
        self.assertEqual(set(self.folder.parent.iterdir()),before)
    def test_subtitles_validate_order_and_duration(self):
        srt='1\n00:00:01,000 --> 00:00:02,500\nCiao, <b>mondo</b>!\n'
        self.assertEqual(clips.parse_srt(srt,3)[0]['text'],'Ciao, mondo!')
        for value in [srt.replace('02,500','09,500'),srt.replace('00:00:01','00:99:01'),'empty']:
            with self.assertRaises(ValueError):clips.parse_srt(value,3)
    def test_suggestions_are_declared_temporal_and_stay_in_duration(self):
        r=clips.suggest({'source_id':'recording:'+self.id,'seconds':30})
        self.assertIn('non una valutazione AI',r['note']);self.assertTrue(all(0<=c['start']<c['end']<=60 for c in r['items']))
    def test_multiscene_clip_associates_only_characters_in_the_cut(self):
        identity='b'*12;folder=self.root/'output'/identity;folder.mkdir(parents=True)
        (folder/'video.mp4').write_bytes(b'video');providers.atomic_json(folder/'status.json',{'state':'done'})
        project={'duration':20,'settings':platform_store.render_settings(providers.settings(),'nova'),'captions':[],
                 'scenes':[{'start':0,'end':10,'settings':platform_store.render_settings(providers.settings(),'nova')},{'start':10,'end':20,'settings':platform_store.render_settings(providers.settings(),'lumo')}]}
        providers.atomic_json(folder/'project.json',project)
        p=clips.prepare(self.data(source_id='job:'+identity,start=12,end=18,character_ids=['ari']))
        self.assertEqual(p['character_ids'],['lumo']);self.assertEqual(p['config']['character']['id'],'lumo');self.assertEqual(p['scenes'][0]['start'],0)
    def test_changed_source_is_rejected_before_ffmpeg(self):
        p=clips.prepare(self.data());(self.folder/'source.mp4').write_bytes(b'changed-source')
        with patch.object(clips.subprocess,'Popen') as process:
            with self.assertRaises(ValueError):clips.render(p,self.root,lambda:False,lambda *a:None,lambda *a:None)
            process.assert_not_called()
    def test_clip_metadata_never_claims_unknown_voice_is_synthetic(self):
        p={'title':'Una clip','settings':{'name':'Registrazione'},'script':'','clip':True}
        for v in packages.metadata(p).values():self.assertNotIn('Voce sintetica',v['description'])
    def test_webm_without_duration_header_is_scanned_locally(self):
        target=self.root/'recorded.webm'
        subprocess.run([media.ffmpeg_path(),'-v','error','-y','-f','lavfi','-i','color=c=navy:s=320x180:r=24','-t','2','-c:v','libvpx-vp9','-live','1',str(target)],capture_output=True,check=True,timeout=30)
        header=subprocess.run([media.ffmpeg_path(),'-hide_banner','-i',str(target)],capture_output=True,text=True,timeout=10)
        self.assertIn('Duration: N/A',header.stderr)
        result=clips.probe(target)
        self.assertGreater(result['duration'],1.9);self.assertLess(result['duration'],2.1)
        self.assertEqual(result['codec'],'vp9')
    def test_actual_silent_source_becomes_a_playable_clip_with_audio_and_srt(self):
        command=[media.ffmpeg_path(),'-v','error','-y','-f','lavfi','-i','color=c=navy:s=320x180:r=24','-t','3','-c:v','libx264','-pix_fmt','yuv420p',str(self.folder/'source.mp4')]
        subprocess.run(command,capture_output=True,check=True,timeout=30)
        self.meta.update(duration=3,captions=[{'start':.5,'end':2.5,'text':'Una prova locale di sottotitoli.'}]);providers.atomic_json(self.folder/'recording.json',self.meta)
        clip=clips.prepare(self.data(start=1,end=3,format='portrait'));target=self.root/'rendered';target.mkdir()
        project=clips.render(clip,target,lambda:False,lambda *a:None,lambda *a:None)
        info=clips.probe(target/'video.mp4')
        self.assertTrue(info['audio']);self.assertEqual((info['width'],info['height']),(720,1280));self.assertTrue(project['captions_burned'])
        self.assertIn('00:00:00,000 --> 00:00:01,500',(target/'captions.srt').read_text())
        self.assertTrue((target/'cover.png').is_file())

if __name__=='__main__':unittest.main()

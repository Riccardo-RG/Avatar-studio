"""Offline regression checks for interrupted setup and portable transfer archives."""
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import export_m1
import runtime_config
import setup_mac
import verify_m1


class SetupAudit(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='avatar M1 test ')
        self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def test_platform_minimum_before_installing(self):
        for version in ('11.7','12.7','13.4'):
            self.assertIn('13.5',setup_mac.host_problem('Darwin','arm64',(3,11),version))
        self.assertEqual(setup_mac.host_problem('Darwin','arm64',(3,13),'13.5'),'')
        self.assertTrue(setup_mac.host_problem('Darwin','arm64',(3,14),'15.0'))
        with self.assertRaises(ValueError):setup_mac.plan('aarch32')

    def test_correct_existing_download_is_not_requested_again(self):
        path=self.root/'model';path.write_bytes(b'complete')
        with patch.object(setup_mac,'run') as run:
            setup_mac.download('https://example.test/model',path,hashlib.sha256(b'complete').hexdigest())
        run.assert_not_called()

    def test_interrupted_download_resumes_and_atomic_completion(self):
        target=self.root/'model.gguf';partial=target.with_suffix('.gguf.part');partial.write_bytes(b'part')
        def finish(args):
            self.assertIn('--continue-at',args);self.assertFalse(target.exists())
            Path(args[args.index('--output')+1]).write_bytes(b'part-complete')
        with patch.object(setup_mac,'run',side_effect=finish):
            setup_mac.download('https://example.test/model',target,hashlib.sha256(b'part-complete').hexdigest())
        self.assertEqual(target.read_bytes(),b'part-complete');self.assertFalse(partial.exists())

    def test_failed_checksum_keeps_previously_installed_file(self):
        target=self.root/'model';target.write_bytes(b'previous')
        def corrupt(args):Path(args[args.index('--output')+1]).write_bytes(b'corrupt')
        with patch.object(setup_mac,'run',side_effect=corrupt),self.assertRaises(RuntimeError):
            setup_mac.download('https://example.test/model',target,hashlib.sha256(b'valid').hexdigest())
        self.assertEqual(target.read_bytes(),b'previous');self.assertFalse(target.with_suffix('.part').exists())

    def test_completed_partial_is_promoted_without_network(self):
        target=self.root/'model.gguf';target.with_suffix('.gguf.part').write_bytes(b'complete')
        with patch.object(setup_mac,'run') as run:
            setup_mac.download('https://example.test/model',target,hashlib.sha256(b'complete').hexdigest())
        run.assert_not_called();self.assertEqual(target.read_bytes(),b'complete')

    def test_cdn_without_resume_restarts_once(self):
        target=self.root/'model.gguf';target.with_suffix('.gguf.part').write_bytes(b'partial')
        calls=[]
        def fetch(args):
            calls.append(args)
            if len(calls)==1:raise subprocess.CalledProcessError(33,args)
            self.assertNotIn('--continue-at',args)
            Path(args[args.index('--output')+1]).write_bytes(b'complete')
        with patch.object(setup_mac,'run',side_effect=fetch):
            setup_mac.download('https://example.test/model',target,hashlib.sha256(b'complete').hexdigest())
        self.assertEqual(len(calls),2)

    def test_http_416_damaged_completed_partial_can_recover(self):
        target=self.root/'model.gguf';target.with_suffix('.gguf.part').write_bytes(b'badcomplete')
        calls=[]
        def fetch(args):
            calls.append(args)
            if len(calls)==1:raise subprocess.CalledProcessError(22,args)
            Path(args[args.index('--output')+1]).write_bytes(b'complete')
        with patch.object(setup_mac,'run',side_effect=fetch):
            setup_mac.download('https://example.test/model',target,hashlib.sha256(b'complete').hexdigest())
        self.assertEqual(target.read_bytes(),b'complete');self.assertEqual(len(calls),2)

    def test_missing_checksum_cannot_download(self):
        with patch.object(setup_mac,'run') as run,self.assertRaises(ValueError):
            setup_mac.download('https://example.test/model',self.root/'model')
        run.assert_not_called()

    def test_partial_or_foreign_node_is_not_ready(self):
        folder=self.root/'node';folder.mkdir()
        self.assertFalse(setup_mac.node_ready(folder,'arm64'))
        npm=folder/'lib/node_modules/npm/bin/npm-cli.js';npm.parent.mkdir(parents=True);npm.write_text('')
        with patch.object(setup_mac.subprocess,'check_output',return_value=json.dumps({'version':setup_mac.NODE_VERSION,'arch':'x64'})):
            self.assertFalse(setup_mac.node_ready(folder,'arm64'))
        with patch.object(setup_mac.subprocess,'check_output',return_value=json.dumps({'version':setup_mac.NODE_VERSION,'arch':'arm64'})):
            self.assertTrue(setup_mac.node_ready(folder,'arm64'))

    def test_atomic_runtime_replacement_rolls_back_on_failure(self):
        destination=self.root/'node';destination.mkdir();(destination/'old').write_text('original')
        with self.assertRaises(FileNotFoundError):setup_mac.replace_runtime(self.root/'missing-staging',destination)
        self.assertEqual((destination/'old').read_text(),'original')
        staged=self.root/'staged';staged.mkdir();(staged/'new').write_text('replacement')
        setup_mac.replace_runtime(staged,destination)
        self.assertEqual((destination/'new').read_text(),'replacement')

    def test_tar_extraction_rejects_parent_path(self):
        tarpath=self.root/'bad.tar'
        with tarfile.open(tarpath,'w') as archive:
            info=tarfile.TarInfo('../escaped');info.size=1;archive.addfile(info,io.BytesIO(b'x'))
        with self.assertRaises((tarfile.TarError,RuntimeError)):setup_mac.extract(tarpath,self.root/'extract')
        self.assertFalse((self.root/'escaped').exists())

    def test_runtime_rejects_intel_node_on_arm64(self):
        node=self.root/'node';node.write_text('placeholder')
        with patch.dict(os.environ,{'AVATAR_NODE':str(node)}),patch.object(runtime_config.platform,'machine',return_value='arm64'),patch.object(runtime_config.subprocess,'check_output',return_value='{"version":"24.19.0","arch":"x64"}'):
            runtime_config.node.cache_clear();self.assertEqual(runtime_config.node(),'')
        runtime_config.node.cache_clear()

    def test_importable_ffmpeg_without_subtitles_is_not_ready(self):
        from types import SimpleNamespace
        module=SimpleNamespace(get_ffmpeg_exe=lambda:'/fixture/ffmpeg')
        with patch.dict('sys.modules',{'imageio_ffmpeg':module}),patch.object(runtime_config.subprocess,'check_output',side_effect=[' scale crop pad fps ',' libx264 aac ']),self.assertRaises(RuntimeError):
            runtime_config.ffmpeg_capabilities()


class ArchiveAudit(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='avatar archive con spazi ')
        self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        patcher=patch.object(export_m1,'ROOT',self.root);patcher.start();self.addCleanup(patcher.stop)

    def build_archive(self,files):
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as archive:
            manifest=[export_m1.write_member(archive,p) for p in files]
            archive.writestr('avatar-studio/TRASFERIMENTO.json',json.dumps({'files':manifest}))
        buffer.seek(0);return buffer

    def test_streaming_media_hash_and_executable_permissions(self):
        file=self.root/'video.mp4';file.write_bytes(b'video'*(1024*1024))
        command=self.root/'Avvia Avatar Studio.command';command.write_text('#!/bin/zsh\necho ok\n');command.chmod(0o644)
        with patch.object(Path,'read_bytes',side_effect=AssertionError('Media must be streamed')):
            result=self.build_archive([file,command])
        with zipfile.ZipFile(result) as archive:
            manifest=verify_m1.verify_entries(archive)
            self.assertEqual(len(manifest['files']),2)
            info=archive.getinfo('avatar-studio/'+command.name)
            self.assertTrue((info.external_attr>>16)&0o111)
            target=self.root/'estratto con spazi';verify_m1.extract_checked(archive,target)
        self.assertTrue(os.access(target/'avatar-studio'/command.name,os.X_OK))

    def test_secrets_and_native_files_are_rejected_before_packaging(self):
        for name,raw in [('credentials.json',b'{}'),('state.json',b'{"nested":{"access_token":"private"}}'),('native.bin',b'\xcf\xfa\xed\xfemachine')]:
            with self.subTest(name=name):
                file=self.root/name;file.write_bytes(raw)
                with self.assertRaises(ValueError):self.build_archive([file])

    def test_symlink_outside_project_is_rejected(self):
        link=self.root/'outside.txt';link.symlink_to('/etc/hosts')
        with self.assertRaises(ValueError):self.build_archive([link])

    def test_nested_zip_secrets_are_rejected(self):
        file=self.root/'package.zip'
        with zipfile.ZipFile(file,'w') as archive:archive.writestr('metadata.json','{"access_token":"private"}')
        with self.assertRaises(ValueError):self.build_archive([file])

    def test_manifest_cannot_omit_injected_file(self):
        file=self.root/'safe.txt';file.write_text('safe');buffer=self.build_archive([file])
        with zipfile.ZipFile(buffer,'a') as archive:archive.writestr('avatar-studio/unlisted.txt','injected')
        with zipfile.ZipFile(buffer) as archive,self.assertRaises(ValueError):verify_m1.verify_entries(archive)

    def test_zip_path_traversal_is_rejected(self):
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as archive:archive.writestr('avatar-studio/../../escaped','injected')
        with zipfile.ZipFile(buffer) as archive,self.assertRaises(ValueError):verify_m1.verify_entries(archive)

    def test_failed_export_does_not_replace_previous_package(self):
        output=self.root/'output';output.mkdir();target=output/'Avatar-Studio-M1.zip';target.write_bytes(b'previous-good-archive')
        unsafe=self.root/'state.json';unsafe.write_text('{"api_key":"private"}')
        with patch.object(export_m1,'members',return_value=[unsafe]),self.assertRaises(ValueError):export_m1.main()
        self.assertEqual(target.read_bytes(),b'previous-good-archive')


if __name__=='__main__':unittest.main()

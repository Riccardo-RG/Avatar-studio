"""Validate the archive and its relocation without installing or calling external services."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import zipfile
from export_m1 import forbidden_name

ROOT=Path(__file__).resolve().parent

def verify_entries(archive):
    infos=archive.infolist();names={i.filename for i in infos}
    if len(names)!=len(infos):raise ValueError('Nomi duplicati nell’archivio.')
    for info in infos:
        name=info.filename;parts=Path(name).parts
        if not parts or parts[0]!='avatar-studio' or '..' in parts or '\\' in name or forbidden_name(name):raise ValueError('Percorso non trasferibile: '+name)
        if stat.S_ISLNK(info.external_attr>>16):raise ValueError('Collegamento simbolico non consentito nel pacchetto.')
        if name.endswith('.command') and not (info.external_attr>>16)&0o111:raise ValueError('Avviatore senza permesso di esecuzione: '+name)
    manifest=json.loads(archive.read('avatar-studio/TRASFERIMENTO.json'))
    declared=['avatar-studio/'+row['path'] for row in manifest['files']]
    if len(declared)!=len(set(declared)) or set(declared)!=names-{'avatar-studio/TRASFERIMENTO.json'}:raise ValueError('Il manifesto non corrisponde ai file dell’archivio.')
    for row in manifest['files']:
        digest=hashlib.sha256();size=0
        with archive.open('avatar-studio/'+row['path']) as source:
            for chunk in iter(lambda:source.read(1024*1024),b''):digest.update(chunk);size+=len(chunk)
        if size!=row['bytes'] or digest.hexdigest()!=row['sha256']:raise ValueError('Checksum non valido: '+row['path'])
    return manifest

def extract_checked(archive,target):
    archive.extractall(target)
    for info in archive.infolist():
        if info.filename.endswith('.command'):
            file=target/info.filename;file.chmod((info.external_attr>>16)&0o755)
            if not os.access(file,os.X_OK):raise ValueError('Avviatore non eseguibile dopo l’estrazione.')

def main():
    archive_path=ROOT/'output/Avatar-Studio-M1.zip'
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        manifest=verify_entries(archive)
        names=set(archive.namelist())
        for required in ('STATO-LOCALE.md','SERVIZI-E-COSTI.md','WORKFLOW-GUIDA.md','video_projects.py',
                         'static/projects.js','static/projects.css','static/navigation.js',
                         'test_video_projects.py','test_video_project_http.py','check-project-workflow.cjs',
                         'youtube_analytics.py','static/youtube-analytics.js','check-analytics-ui.cjs',
                         'check-growth-flows.cjs','test_research_team.py'):
            assert 'avatar-studio/'+required in names,required
        for required in ('CRESCITA-GUIDA.md','policy_catalog.json','growth.py','policy_intelligence.py','static/business.js','TESTING-FINALE.md','SERVIZI-ESTERNI.md','PUBBLICAZIONE-GUIDA.md','static/activity.js','character_activity.py','data/publications.json','data/activity.json','ACCOUNT-LINGUE-GUIDA.md','CLIP-RISULTATI-GUIDA.md','conversation_bridge.py','clips.py','insights.py','storage_upload.py','languages.py','static/vendor/daily.js','static/vendor/DAILY-LICENSE.txt','runtime_config.cjs','render_process.py','Prepara Mac.command','Avvia Avatar Studio.command'):
            assert 'avatar-studio/'+required in names,required
        assert not any('/.env' in n or '/.venv/' in n or '/runtime/' in n or '/voice-deps/' in n for n in names)
        with tempfile.TemporaryDirectory(prefix='avatar transfer con spazi ') as temp:
            target=Path(temp).resolve()
            for name in names:assert (target/name).resolve().is_relative_to(target)
            extract_checked(archive,target);project=target/'avatar-studio'
            for script in project.glob('*.py'):compile(script.read_text(),str(script),'exec')
            code="from pathlib import Path; import runtime_config,setup_mac; root=Path.cwd().resolve(); assert runtime_config.ROOT==root; p=setup_mac.plan('arm64'); assert p['architecture']=='arm64' and p['gpu_layers']=='99'; assert str(root) in p['python']; print('Relocation and ARM64 plan passed')"
            result=subprocess.run([sys.executable,'-c',code],cwd=project,capture_output=True,text=True,check=True)
    with archive_path.open('rb') as source:archive_sha=hashlib.file_digest(source,'sha256').hexdigest()
    report={'archive':str(archive_path),'files':len(manifest['files']),'bytes':archive_path.stat().st_size,'sha256':archive_sha,'crc_verified':True,'manifest_sha256_verified':True,'command_executable_bits_verified':True,'path_with_spaces_verified':True,'relocated_python_compiled':True,'arm64_plan_verified':True,'physical_m1_tested':False}
    (ROOT/'output/m1-transfer-verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

if __name__=='__main__':main()

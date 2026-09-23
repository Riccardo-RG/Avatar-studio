#!/usr/bin/env python3
"""Package code, portable assets and projects, excluding native runtimes and secrets."""
import hashlib
import json
from pathlib import Path
import re
import stat
import zipfile

ROOT=Path(__file__).resolve().parent
NATIVE_SUFFIXES={'.so','.dylib','.node','.exe','.dll','.pyc'}
SECRET_NAMES={'.env','.env.local','.env.production','.npmrc','.pypirc','credentials.json','id_rsa','id_ed25519'}
SECRET_KEYS={'api_key','access_token','refresh_token','client_secret','secret_access_key','access_key_id','meeting_token','password'}
NATIVE_MAGIC={b'\x7fELF',b'\xcf\xfa\xed\xfe',b'\xfe\xed\xfa\xcf',b'\xce\xfa\xed\xfe',b'\xfe\xed\xfa\xce',b'\xca\xfe\xba\xbe',b'\xbe\xba\xfe\xca'}

def forbidden_name(name):
    parts=Path(name).parts
    return any(p in SECRET_NAMES or p in ('.venv','runtime','voice-deps','deps','__pycache__','node_modules') or p.startswith('.env.') for p in parts) or Path(name).suffix in NATIVE_SUFFIXES

def check_json_secrets(value,label):
    if isinstance(value,dict):
        for key,item in value.items():
            if key.casefold() in SECRET_KEYS and item not in (None,'',False):raise ValueError('Esportazione bloccata: credenziale presente in '+label+'.')
            check_json_secrets(item,label)
    elif isinstance(value,list):
        for item in value:check_json_secrets(item,label)

def check_portable_file(path,relative):
    if forbidden_name(relative):raise ValueError('File non trasferibile nel pacchetto: '+relative)
    if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):raise ValueError('Collegamento esterno non trasferibile: '+relative)
    with path.open('rb') as source:
        if source.read(4) in NATIVE_MAGIC:raise ValueError('Binario nativo non trasferibile: '+relative)
    if path.suffix=='.json':check_json_secrets(json.loads(path.read_text()),relative)
    if path.suffix=='.zip':
        with zipfile.ZipFile(path) as nested:
            for info in nested.infolist():
                if forbidden_name(info.filename):raise ValueError('File non trasferibile nell’archivio '+relative)
                if info.is_dir():continue
                with nested.open(info) as source:
                    if source.read(4) in NATIVE_MAGIC:raise ValueError('Binario nativo nell’archivio '+relative)
                if info.filename.endswith('.json'):check_json_secrets(json.loads(nested.read(info)),relative)

def write_member(archive,path):
    relative=path.relative_to(ROOT).as_posix();check_portable_file(path,relative)
    info=zipfile.ZipInfo.from_file(path,'avatar-studio/'+relative)
    info.compress_type=zipfile.ZIP_STORED if path.suffix in ('.mp4','.zip','.png','.jpg') else zipfile.ZIP_DEFLATED
    # Finder/Archive Utility receives Unix executable flags even if source was copied without them.
    if path.suffix=='.command':info.create_system=3;info.external_attr=(stat.S_IFREG|0o755)<<16
    digest=hashlib.sha256();size=0
    with path.open('rb') as source,archive.open(info,'w',force_zip64=True) as dest:
        for chunk in iter(lambda:source.read(1024*1024),b''):
            digest.update(chunk);size+=len(chunk);dest.write(chunk)
    return {'path':relative,'bytes':size,'sha256':digest.hexdigest()}

def members():
    files=[]
    for path in ROOT.iterdir():
        if path.is_file() and (path.suffix in ('.py','.js','.cjs','.md','.command') or path.name in ('package.json','package-lock.json','requirements-mac.txt','policy_catalog.json')):
            files.append(path)
    for directory in ('static','models'):
        for path in (ROOT/directory).rglob('*'):
            if path.is_file() and path.suffix not in ('.onnx','.gguf') and path.name!='.DS_Store':files.append(path)
    for name in ('settings.json','studio.json','live.json','platform.json','usage.json','connections.json','publications.json','broadcast.json','activity.json','insights.json','growth.json'):
        path=ROOT/'data'/name
        if path.is_file():files.append(path)
    if (ROOT/'data/recordings').exists():files.extend(p for p in (ROOT/'data/recordings').glob('*/*') if p.is_file() and p.suffix in ('.mp4','.mov','.mkv','.webm','.json'))
    project_files = ('project.json', 'snapshot.json', 'timeline.json', 'voice.wav',
                     'script.txt', 'captions.srt', 'character.png', 'materials.zip')
    for folder in (ROOT/'data/video-projects').glob('*'):
        if folder.is_dir() and re.fullmatch(r'[a-f0-9]{12}', folder.name):
            files.extend(path for path in folder.rglob('*') if path.is_file() and path.name in project_files)
    if (ROOT/'data/character-assets').exists():files.extend((ROOT/'data/character-assets').glob('*.png'))
    for folder in (ROOT/'output').iterdir() if (ROOT/'output').exists() else []:
        if folder.is_dir() and re.fullmatch(r'[a-f0-9]{12}',folder.name) and (folder/'status.json').exists():
            status=json.loads((folder/'status.json').read_text())
            if status.get('state')=='done':files.extend(p for p in folder.rglob('*') if p.is_file() and p.suffix!='.log')
        elif folder.is_dir() and folder.name=='live':files.extend(p for p in folder.rglob('*') if p.is_file() and p.suffix in ('.wav','.json'))
        elif folder.is_dir() and folder.name=='publish-media':files.extend(folder.glob('*/*/video.mp4'))
        elif folder.is_file() and folder.name not in ('m1-package-verification.json','m1-transfer-verification.json') and (folder.name in ('live-demo.mp4','serie-completa.zip') or folder.suffix in ('.json','.png','.jpg')):files.append(folder)
    return sorted(set(files))

def main():
    target=ROOT/'output/Avatar-Studio-M1.zip';temporary=target.with_suffix('.tmp');manifest=[]
    target.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=2) as archive:
        for path in members():
            manifest.append(write_member(archive,path))
        archive.writestr('avatar-studio/TRASFERIMENTO.json',json.dumps({'architecture':'Installa componenti nativi sul Mac di destinazione','secrets_included':False,'native_binaries_included':False,'files':manifest},ensure_ascii=False,indent=2))
    with zipfile.ZipFile(temporary) as archive:
        if archive.testzip() is not None:raise ValueError('Verifica CRC del nuovo archivio fallita. Il pacchetto precedente è conservato.')
        if any(forbidden_name(n) for n in archive.namelist()):raise ValueError('Il pacchetto contiene file non trasferibili.')
    temporary.replace(target)
    report={'archive':str(target),'files':len(manifest),'bytes':target.stat().st_size,'crc_verified':True,'native_binaries':False,'api_keys':False}
    (ROOT/'output/m1-package-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

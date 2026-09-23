#!/usr/bin/env python3
"""Install native dependencies inside this project, never into global Python."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid

ROOT=Path(__file__).resolve().parent
NODE_VERSION='24.19.0'
NODE_SHA={'arm64':'8294b7aa9b03997481c06babf1e8b270c859358f27da57a11509afe537ac381d','x64':'d1b5e999db158c62fe8f7267a4476b035d8bd93b1a605bac24a3f0dd166e3316'}
LLAMA_SHA={'arm64':'e64c549a443d1353f440f436039d449a431fbcc1528b03838dda3d9a26530062','x64':'42575805396c6a8873d81da3ddf376135ff7c71a5e5c14076c546e0f221c3ece'}
MODEL_URL='https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/91cad51170dc346986eccefdc2dd33a9da36ead9/qwen2.5-1.5b-instruct-q4_k_m.gguf'
MODEL_SHA='6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e'
VOICE_URL='https://huggingface.co/rhasspy/piper-voices/resolve/c10ece1aade47bb51c153c893d14e5bf8e5b7117/it/it_IT/paola/medium/'
VOICE_SHA={'.onnx':'6fc918b5a0ea6137382833dddfa567bffbe6a5060c02043c87192ee59c04210c','.onnx.json':'aea19c0a7fce29fbc359b93f10e7902854401e4c95ae2ea328ae516b15d296cf'}

def sha256(path):
    with Path(path).open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()

def host_problem(system=None,machine=None,version=None,macos=None):
    system=system or platform.system();machine=machine or platform.machine()
    version=version or sys.version_info[:2];macos=macos if macos is not None else platform.mac_ver()[0]
    if system!='Darwin' or not (3,11)<=tuple(version[:2])<(3,14):
        return 'Serve macOS e Python 3.11–3.13 nativo. Installa Python da python.org e riprova.'
    if machine not in ('arm64','x86_64'):return 'Architettura non supportata: usa un Mac Apple Silicon o Intel a 64 bit.'
    try:mac_version=tuple(int(x) for x in macos.split('.')[:2])
    except (ValueError,AttributeError):mac_version=()
    if mac_version<(13,5):return 'Serve macOS 13.5 o successivo per Node.js 24 e le dipendenze native. Aggiorna macOS prima della preparazione.'
    return ''

def run(args,**kwargs):subprocess.run([str(a) for a in args],check=True,cwd=ROOT,**kwargs)
def download(url,target,checksum=None):
    target=Path(target)
    if not checksum:raise ValueError('Ogni download richiede un checksum SHA-256.')
    if target.is_file() and sha256(target)==checksum:return
    target.parent.mkdir(parents=True,exist_ok=True);partial=target.with_suffix(target.suffix+'.part')
    if partial.is_file() and sha256(partial)==checksum:partial.replace(target);return
    # Keep a partial model for the next run; never expose it as an installed model.
    command=['/usr/bin/curl','--fail','--location','--proto','=https','--proto-redir','=https','--tlsv1.2','--retry','2','--connect-timeout','20','--speed-limit','1024','--speed-time','60']
    try:run([*command,'--continue-at','-','--output',partial,url])
    except subprocess.CalledProcessError as exc:
        if exc.returncode not in (22,33,36) or not partial.exists():raise
        # CDNs can reject byte ranges (including HTTP 416 for a damaged complete part).
        # Restart only once, retaining the previously installed target on any failure.
        partial.unlink(missing_ok=True);run([*command,'--output',partial,url])
    if sha256(partial)!=checksum:
        partial.unlink(missing_ok=True);raise RuntimeError('Checksum del download non valido.')
    partial.replace(target)

def node_ready(folder,arch):
    if not (folder/'lib/node_modules/npm/bin/npm-cli.js').is_file():return False
    try:
        result=subprocess.check_output([folder/'bin/node','-p','JSON.stringify({version:process.versions.node,arch:process.arch})'],text=True,timeout=10)
        return json.loads(result)=={'version':NODE_VERSION,'arch':arch}
    except (OSError,ValueError,subprocess.SubprocessError):return False

def llama_ready(folder,arch,*,explain=False):
    binary=folder/'llama-completion'
    try:
        if not os.access(binary,os.X_OK):return False
        architectures=subprocess.check_output(['/usr/bin/lipo','-archs',binary],text=True,timeout=30).split()
        if ('arm64' if arch=='arm64' else 'x86_64') not in architectures:return False
        # The first native launch can take longer while macOS validates dylibs.
        subprocess.run([binary,'--version'],capture_output=True,check=True,timeout=60)
        return True
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        if explain:
            detail=getattr(exc,'stderr',None) or str(exc)
            if isinstance(detail,bytes):detail=detail.decode(errors='replace')
            raise RuntimeError('Il motore locale non si avvia: '+detail[-1500:]) from exc
        return False

def replace_runtime(staged,destination):
    # All files are staged on the same filesystem before the runtime becomes visible.
    backup=destination.with_name(destination.name+'.previous-'+uuid.uuid4().hex[:8])
    if destination.exists():destination.rename(backup)
    try:staged.rename(destination)
    except BaseException:
        if backup.exists():backup.rename(destination)
        raise
    if backup.exists():shutil.rmtree(backup)

def extract(archive,destination):
    destination.mkdir(parents=True,exist_ok=True)
    with tarfile.open(archive) as tar:
        if not hasattr(tarfile,'data_filter'):raise RuntimeError('Aggiorna Python 3.11 a una versione recente per estrarre gli archivi in sicurezza.')
        tar.extractall(destination,filter='data')

def plan(machine=None):
    machine=machine or platform.machine()
    if machine not in ('arm64','x86_64'):raise ValueError('Architettura Mac non supportata.')
    arch='arm64' if machine=='arm64' else 'x64'
    return {'architecture':arch,'minimum_macos':'13.5','python_versions':'3.11–3.13','python':str(ROOT/'.venv/bin/python'),'node_url':f'https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-darwin-{arch}.tar.gz','llama_url':f'https://github.com/ggml-org/llama.cpp/releases/download/b11050/llama-b11050-bin-macos-{arch}.tar.gz','gpu_layers':'99' if arch=='arm64' else '0','scope':'Solo cartella del progetto. Nessuna chiave o pubblicazione.','downloads':'Dipendenze Python/Node e, se mancanti, modelli voce e Qwen (~1,2 GB). Download verificati SHA-256 e modelli riprendibili.'}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plan',action='store_true');parser.add_argument('--architecture',choices=['arm64','x86_64']);args=parser.parse_args();p=plan(args.architecture)
    if args.plan:print(json.dumps(p,ensure_ascii=False,indent=2));return
    if args.architecture:raise SystemExit('--architecture si usa solo con --plan: l’installazione rileva il Mac reale.')
    problem=host_problem()
    if problem:raise SystemExit(problem)
    if not hasattr(tarfile,'data_filter'):raise SystemExit('Aggiorna Python a una versione recente di 3.11–3.13 prima di installare: serve il filtro di estrazione sicura (Python 3.11.4 o successivo).')
    native_arm=subprocess.run(['/usr/sbin/sysctl','-n','hw.optional.arm64'],capture_output=True,text=True).stdout.strip()=='1'
    if native_arm and platform.machine()!='arm64':raise SystemExit('Questo Python usa Rosetta. Avvia Python ARM64 nativo prima di preparare il Mac M1.')
    venv=ROOT/'.venv';python=venv/'bin/python'
    if not python.exists():run([sys.executable,'-m','venv',venv])
    actual=json.loads(subprocess.check_output([python,'-c','import platform,sys,json;print(json.dumps([platform.machine(),list(sys.version_info[:2])]))'],text=True))
    if actual[0]!=platform.machine() or not (3,11)<=tuple(actual[1])<(3,14):raise SystemExit('La .venv usa un’architettura o una versione Python incompatibile. Rinominala e ripeti; non vengono cancellati dati.')
    run([python,'-m','pip','install','--upgrade','pip']);run([python,'-m','pip','install','--only-binary=:all:','-r',ROOT/'requirements-mac.txt'])
    runtime=ROOT/'runtime';runtime.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.avatar-setup-',dir=runtime) as tmp:
        tmp=Path(tmp);node_root=runtime/'node'
        if not node_ready(node_root,p['architecture']):
            archive=tmp/'node.tar.gz';download(p['node_url'],archive,NODE_SHA[p['architecture']]);extract(archive,tmp/'node')
            staged=next((tmp/'node').iterdir())
            if not node_ready(staged,p['architecture']):raise RuntimeError('Il runtime Node scaricato non si avvia correttamente.')
            replace_runtime(staged,node_root)
        node=node_root/'bin/node';env={**os.environ,'PATH':str(node_root/'bin')+os.pathsep+os.environ.get('PATH',''),'PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD':'1'}
        run([node,node_root/'lib/node_modules/npm/bin/npm-cli.js','ci' if (ROOT/'package-lock.json').exists() else 'install','--ignore-scripts','--no-audit','--no-fund'],env=env)
        llama_root=runtime/'llama-native'
        if not llama_ready(llama_root,p['architecture']):
            archive=tmp/'llama.tar.gz';download(p['llama_url'],archive,LLAMA_SHA[p['architecture']]);extract(archive,tmp/'llama')
            binary=next((tmp/'llama').rglob('llama-completion'),None)
            if not binary:raise RuntimeError('Archivio llama.cpp senza llama-completion.')
            if not llama_ready(binary.parent,p['architecture'],explain=True):raise RuntimeError('Il motore llama.cpp scaricato non corrisponde all’architettura richiesta.')
            replace_runtime(binary.parent,llama_root)
    model=ROOT/'models/qwen2.5-1.5b-instruct-q4_k_m.gguf'
    download(MODEL_URL,model,MODEL_SHA)
    for suffix in ('.onnx','.onnx.json'):
        path=ROOT/'models/piper'/('it_IT-paola-medium'+suffix)
        download(VOICE_URL+path.name,path,VOICE_SHA[suffix])
    run([python,ROOT/'runtime_config.py'])
    print('\nPreparazione completata. Apri Avvia Avatar Studio.command. Chrome deve essere installato. Il collaudo su M1 va eseguito su quel Mac.')

if __name__=='__main__':main()

"""Portable runtime discovery, preferring project-local/native dependencies."""
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import ssl
from functools import lru_cache

ROOT=Path(__file__).resolve().parent
LEGACY=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies'

def choose(env,candidates):
    if os.environ.get(env):return os.environ[env] if Path(os.environ[env]).exists() else ''
    return next((str(p) for p in candidates if p and Path(p).exists()),'')

@lru_cache(maxsize=1)
def node():
    candidates=[os.environ['AVATAR_NODE']] if os.environ.get('AVATAR_NODE') else [ROOT/'runtime/node/bin/node',shutil.which('node'),LEGACY/'node/bin/node']
    for path in candidates:
        if not path or not Path(path).exists():continue
        try:
            info=json.loads(subprocess.check_output([str(path),'-p','JSON.stringify({version:process.versions.node,arch:process.arch})'],text=True,timeout=4))
            arch='arm64' if platform.machine()=='arm64' else 'x64'
            if int(info['version'].split('.')[0])>=24 and info['arch']==arch:return str(path)
        except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError):continue
    return ''
def playwright():return choose('AVATAR_PLAYWRIGHT',[ROOT/'node_modules/playwright',LEGACY/'node/node_modules/playwright']) or 'playwright'
def chrome():return choose('AVATAR_CHROME',['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'])
def llama():return choose('AVATAR_LLAMA',[ROOT/'runtime/llama-native/llama-completion',ROOT/'runtime/llama-native/bin/llama-completion',ROOT/'runtime/llama-b11050/llama-completion' if platform.machine()=='x86_64' else None,shutil.which('llama-completion')])
def gpu_layers():return os.environ.get('AVATAR_GPU_LAYERS','99' if platform.machine()=='arm64' else '0')

def ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context(cafile='/etc/ssl/cert.pem' if Path('/etc/ssl/cert.pem').exists() else None)

def dependency_path(folder):
    # Never load Intel/Python-3.11 wheels into a native M1 or another Python ABI.
    if platform.machine()=='x86_64' and sys.version_info[:2]==(3,11) and not (ROOT/'.venv').exists():
        sys.path.insert(0,str(ROOT/folder))

def ffmpeg_capabilities():
    import imageio_ffmpeg
    binary=imageio_ffmpeg.get_ffmpeg_exe()
    filters=subprocess.check_output([binary,'-hide_banner','-filters'],text=True,stderr=subprocess.DEVNULL,timeout=8)
    encoders=subprocess.check_output([binary,'-hide_banner','-encoders'],text=True,stderr=subprocess.DEVNULL,timeout=8)
    if not all(' '+name+' ' in filters for name in ('subtitles','scale','crop','pad','fps')):
        raise RuntimeError('FFmpeg non include i filtri necessari, compreso subtitles/libass.')
    if not all(' '+name+' ' in encoders for name in ('libx264','aac')):
        raise RuntimeError('FFmpeg non include gli encoder H.264/AAC necessari.')
    return 'Eseguibile avviato; filtri, sottotitoli libass e H.264/AAC presenti'

def diagnostics():
    from setup_mac import host_problem
    dependency_path('deps');dependency_path('voice-deps')
    try:
        native_arm=subprocess.run(['/usr/sbin/sysctl','-n','hw.optional.arm64'],capture_output=True,text=True,timeout=3).stdout.strip()=='1'
    except (OSError,subprocess.TimeoutExpired):native_arm=False
    problem=host_problem()
    checks=[{'name':'Python','ok':(3,11)<=sys.version_info[:2]<(3,14),'detail':platform.python_version()+' · '+platform.machine()+' (supportati 3.11–3.13)'},
            {'name':'Sistema operativo','ok':not problem,'detail':problem or 'macOS '+platform.mac_ver()[0]+' · requisito minimo 13.5'},
            {'name':'Esecuzione nativa','ok':not(native_arm and platform.machine()!='arm64'),'detail':'Usa Python ARM64 su Apple Silicon.'},
            {'name':'Node.js','ok':bool(node()),'detail':node() or 'Installa Node.js 24 LTS'},
            {'name':'Playwright','ok':Path(playwright()).exists(),'detail':playwright()},
            {'name':'Chrome','ok':bool(chrome()),'detail':chrome() or 'Installa Google Chrome'},
            {'name':'Motore locale','ok':bool(llama()),'detail':llama() or 'Esegui la preparazione oppure configura Ollama'},
            {'name':'Modello Qwen','ok':(ROOT/'models/qwen2.5-1.5b-instruct-q4_k_m.gguf').exists(),'detail':'Modello GGUF condivisibile fra Intel e M1'},
            {'name':'Modello voce Paola','ok':all((ROOT/'models/piper'/('it_IT-paola-medium'+suffix)).is_file() for suffix in ('.onnx','.onnx.json')),'detail':'Modello vocale e configurazione locale'}]
    for name,module in [('Voce Piper','piper'),('FFmpeg','imageio_ffmpeg')]:
        try:__import__(module);ok=True;detail=ffmpeg_capabilities() if module=='imageio_ffmpeg' else 'Disponibile per questo Python'
        except Exception:ok=False;detail='Esegui Prepara Mac.command'
        checks.append({'name':name,'ok':ok,'detail':detail})
    return {'machine':platform.machine(),'python':platform.python_version(),'gpu_layers':gpu_layers(),'checks':checks,'ready':all(c['ok'] for c in checks)}

if __name__=='__main__':print(json.dumps(diagnostics(),ensure_ascii=False,indent=2))

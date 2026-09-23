#!/usr/bin/env python3
"""Local-only Avatar Studio server. Python stdlib; no cloud dependency by default."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import functools
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import threading
import time
import traceback
from urllib.parse import unquote, urlparse
import uuid

# Reserve the listening port before imports create workers or recover saved jobs.
# A second launch must fail without touching the first process's workspace.
STARTUP_SERVER = None
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    try:
        STARTUP_SERVER = ThreadingHTTPServer(('127.0.0.1', args.port), SimpleHTTPRequestHandler)
    except OSError as exc:
        raise SystemExit('Impossibile avviare lo studio: porta già occupata o non disponibile. Chiudi il secondo avvio e usa la finestra esistente.') from exc

import media
import providers
import studio
import packages
from live import LiveDirector
from live_connectors import ChatConnectors
import platform_store
import agent_team
import cloud_avatar
import runtime_config
import productions
import clips
import video_projects
import languages
import storage_upload
import insights
import youtube_analytics
import publishing
import service_connections
import broadcast
import conversation_bridge
import render_process
import growth
import policy_intelligence
import market_research
import web_sources
from character_activity import Activity,character_ids
from render_gate import wait_for_live

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
OUTPUT.mkdir(exist_ok=True)
RUNTIME = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies"
NODE = runtime_config.node()
PLAYWRIGHT = runtime_config.playwright()
CHROME = runtime_config.chrome()
TOKEN = secrets.token_urlsafe(32)
JOBS = {}
JOB_LOCK = threading.RLock()
EXECUTOR = ThreadPoolExecutor(max_workers=1)
SCRIPT_LOCK = threading.Lock()
PREVIEW_LOCK = threading.Lock()
EXPORT_LOCK = threading.Lock()
IMPORT_SLOTS = threading.BoundedSemaphore(2)
PREVIEWS = ROOT / "data/previews"
PREVIEWS.mkdir(parents=True, exist_ok=True)
VOICES = media.voices()
BASE_URL = ""
LIVE_PREVIEW = None
LIVE = LiveDirector(ROOT)
CHAT = ChatConnectors(ROOT, NODE, LIVE)
agent_team.recover()

def effective_settings(identity=None):
    return platform_store.render_settings(providers.settings(), identity)

def video_settings(data,require_voice=True):
    config=effective_settings(data.get('character_id'));config['language']=languages.code(data.get('language','it'))
    if require_voice:config=languages.apply(config,data)
    if require_voice and data.get('voice'):
        if data['voice'] not in VOICES:raise ValueError('Voce non disponibile.')
        config['voice']=data['voice']
    if 'rate' in data:config['rate']=int(platform_store.number(data['rate'],100,220))
    return config


def public_job(job):
    return {k: v for k, v in job.items() if k not in {"process", "future", "cloud_quote", "clip"}}


def persist_job(job):
    providers.atomic_json(OUTPUT / job["id"] / "status.json", public_job(job))


def update_job(job, percent, message):
    with JOB_LOCK:
        if job.get("cancelled"):
            raise ValueError("Produzione annullata.")
        job.update(progress=percent, message=message)
        persist_job(job)


def render_job(job, script, config):
    folder = OUTPUT / job["id"]
    try:
        wait_for_live(LIVE,lambda:bool(job.get('cancelled')),lambda p,m:update_job(job,p,m))
        with JOB_LOCK:
            job["state"] = "running"
        update_job(job, 2, "Preparazione della voce")
        if job.get('clip'):
            def set_clip_process(proc):
                with JOB_LOCK:
                    job['process']=proc
                    if job.get('cancelled'):proc.terminate()
            project=clips.render(job['clip'],folder,lambda:bool(job.get('cancelled')),lambda p,m:update_job(job,p,m),set_clip_process)
            timeline=project
        else:
            if job.pop('recover_cloud',False):
                remote,saved=cloud_avatar.recovery(folder)
                script=saved['script'];config=saved['settings']
                timeline={k:v for k,v in saved.items() if k not in ('title','script','settings')}
                cloud_avatar.wait_video(remote,folder,lambda:bool(job.get('cancelled')),lambda p,m:update_job(job,p,m))
            elif job.get('production'):
                timeline=productions.synthesize(job['production'],folder,lambda p,m:update_job(job,p,m),lambda:bool(job.get('cancelled')))
            elif job.get('cloud_quote'):
                q=job.pop('cloud_quote')
                timeline=q['timeline']
                cloud_avatar.generate(q,folder,lambda:bool(job.get('cancelled')),lambda p,m:update_job(job,p,m))
            else:
                timeline = media.synthesize(script, config, folder, lambda p, m: update_job(job, p, m))
            project = {"version": 2, "title": job["title"], "script": script, "settings": config, **timeline}
            if job.get('engine')=='heygen':project['external_video']=True
            for field in ("episode", "persona", "rubric"):
                if field in job:
                    project[field] = job[field]
            providers.atomic_json(folder / "project.json", project)
            update_job(job, 27, "Preparazione della scena del personaggio")
            env = {**os.environ, "AVATAR_PLAYWRIGHT": PLAYWRIGHT, "AVATAR_CHROME": CHROME,
                   "AVATAR_FFMPEG": media.ffmpeg_path()}
            if timeline.get('music'):env['AVATAR_MUSIC']=str(productions.music_file(timeline['music']))
            def set_render_process(proc):
                with JOB_LOCK:
                    job['process'] = proc
                    if job.get('cancelled'):
                        proc.terminate()
            render_process.run([NODE, str(ROOT / 'render.cjs'), BASE_URL, job['id'], str(folder)],
                folder, env, set_render_process,
                lambda p: update_job(job, 30 + int(p * 65), 'Rendering del video'))
        update_job(job, 97, "Preparazione dei pacchetti social")
        bundles = packages.make_packages(folder, project)
        update_job(job, 100, "Video e pacchetti pronti sul Mac")
        with JOB_LOCK:
            if job.get('cancelled'):
                raise ValueError('Produzione annullata.')
            job.update(state="done", duration=round(timeline["duration"], 2),
                video=f"/output/{job['id']}/video.mp4", thumbnail=f"/output/{job['id']}/poster.png",
                path=str(folder / "video.mp4"), packages=bundles, cover=f"/output/{job['id']}/cover.png")
    except Exception as exc:
        proc = job.get("process")
        if proc and proc.poll() is None:
            proc.terminate()
        with JOB_LOCK:
            job.update(state="cancelled" if job.get("cancelled") else "error", message=str(exc))
        (folder / "video.mp4").unlink(missing_ok=True)
        (folder / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
    finally:
        with JOB_LOCK:
            job.pop("process", None)
            persist_job(job)
            if job.get("episode"):
                studio.finish_episode(job["episode"]["id"], job["episode"]["revision"], job["id"], job["state"] == "done")


def check_capacity(count):
    if sum(j['state'] in ('queued', 'running') for j in JOBS.values()) + count > 10:
        raise ValueError('La coda accetta al massimo dieci video. Attendi il completamento.')


def enqueue(title, script, config, **snapshots):
    identity = uuid.uuid4().hex[:12]
    cast=character_ids(config)
    for scene in snapshots.get('production',{}).get('scenes',[]):cast|=character_ids(scene['settings'])
    if snapshots.get('clip'):cast=set(snapshots['clip']['character_ids'])
    job = {'id': identity, 'title': title, 'state': 'queued', 'progress': 0,
           'message': 'In coda', 'created': time.time(),'character_ids':sorted(cast), **snapshots}
    (OUTPUT / identity).mkdir()
    JOBS[identity] = job
    persist_job(job)
    EXECUTOR.submit(render_job, job, script, config)
    return job


studio.recover_interrupted()
video_projects.recover_interrupted()


for status in OUTPUT.glob("*/status.json"):
    try:
        job = json.loads(status.read_text())
        if job["state"] in ("running", "queued"):
            job.update(state="error", message="Produzione interrotta dalla chiusura dell'app. Puoi riprovare.")
            providers.atomic_json(status, job)
        if (status.parent / 'video.mp4').is_file():
            job['path'] = str(status.parent / 'video.mp4')
        JOBS[job["id"]] = job
    except (ValueError, KeyError):
        pass


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "static"), **kwargs)

    def log_message(self, fmt, *args):
        if args and '/oauth/' in str(args[0]):return
        if args and str(args[0]).startswith(("GET /api/jobs", "GET /api/studio", "GET /api/live", "GET /live-preview.jpg", "POST /api/live/heartbeat", "POST /api/live/frame")):
            return
        super().log_message(fmt, *args)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def host_valid(self):
        return self.headers.get("Host") in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

    def respond(self, value, code=200):
        data = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self.host_valid():
            return self.respond({"error": "Host non valido"}, 403)
        path = unquote(urlparse(self.path).path)
        if path == '/oauth/youtube/callback':
            try:
                service_connections.oauth_finish(urlparse(self.path).query)
                self.send_response(303);self.send_header('Location','/?edition=delivery#connections');self.end_headers();return
            except ValueError as exc:return self.respond({'error':str(exc)},400)
        if path == '/api/growth':return self.respond(growth.snapshot())
        if path == '/api/policies':return self.respond(policy_intelligence.snapshot())
        if path == '/api/insights':return self.respond(insights.snapshot())
        if path == '/api/insights.csv':
            raw=('\ufeff'+insights.csv_report()).encode('utf-8');self.send_response(200);self.send_header('Content-Type','text/csv; charset=utf-8');self.send_header('Content-Disposition','attachment; filename=risultati-contenuti.csv');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
        if path == '/api/clips':return self.respond({'items':clips.catalog()})
        if path == '/api/video-projects':return self.respond(video_projects.catalog())
        if path.startswith('/video-project-assets/'):
            file = video_projects.asset_file(path)
            return self.serve_file(file) if file else self.send_error(404)
        if path.startswith('/recordings/'):
            match=re.fullmatch(r'/recordings/([a-f0-9]{12})/(source\.(?:mp4|mov|mkv|webm))',path)
            file=clips.recording_path(match[1],match[2]) if match else None
            return self.serve_file(file) if file and file.is_file() else self.send_error(404)
        if path == '/api/publications':return self.respond(publishing.snapshot())
        if path == '/api/connections':return self.respond(service_connections.snapshot())
        if path == '/api/broadcast':return self.respond(broadcast.snapshot())
        if path.startswith('/api/character-activity/'):
            identity=path.rsplit('/',1)[-1]
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',identity):return self.respond({'error':'Personaggio non valido.'},400)
            return self.respond(Activity(ROOT).snapshot(identity))
        if path.startswith('/publish-media/'):
            match=re.fullmatch(r'/publish-media/([a-f0-9]{12})/(youtube|tiktok|instagram)/video\.mp4',path)
            file=OUTPUT/'publish-media'/match[1]/match[2]/'video.mp4' if match else None
            return self.serve_file(file) if file and file.is_file() else self.send_error(404)
        if path.startswith('/docs/'):
            name=path.rsplit('/',1)[-1]
            return self.serve_file(ROOT/name) if name in {'WORKFLOW-GUIDA.md','STATO-LOCALE.md','SERVIZI-E-COSTI.md','CRESCITA-GUIDA.md','POLICY-FONTI.md','ANALISI-BUSINESS-SOCIAL.md','REVISIONE-PRE-TEST.md','AUDIT-M1.md','TESTING-FINALE.md','SERVIZI-ESTERNI.md','PUBBLICAZIONE-GUIDA.md','PERSONAGGI-GUIDA.md','CLIP-RISULTATI-GUIDA.md','ACCOUNT-LINGUE-GUIDA.md'} and (ROOT/name).exists() else self.send_error(404)
        if path == "/api/bootstrap":
            return self.respond({"token": TOKEN, "settings": effective_settings(), "studio_settings": providers.studio_settings(), "voices": VOICES, "voice_catalog":media.voice_catalog(), "languages":languages.LANGUAGES,
                "used_usd": providers.budget_used(), "has_openai_key": bool(os.environ.get("OPENAI_API_KEY")),
                "output_folder": str(OUTPUT), "local_model": "Qwen2.5 · 1.5B"})
        if path == '/api/platform':
            doc=platform_store.load()
            return self.respond({**doc,'budget':platform_store.budget_summary(doc),'integrations':cloud_avatar.status()})
        if path == '/api/diagnostics':return self.respond(runtime_config.diagnostics())
        if path.startswith('/characters/') or path.startswith('/character-assets/'):
            file=platform_store.asset_file(path)
            return self.serve_file(file) if file and file.is_file() else self.send_error(404)
        if path == '/live-preview.jpg':
            frame=LIVE_PREVIEW
            if frame is None:return self.send_error(404)
            self.send_response(200)
            self.send_header('Content-Type','image/jpeg')
            self.send_header('Content-Length',str(len(frame)))
            self.end_headers();self.wfile.write(frame);return
        if path == "/api/live":
            return self.respond({**LIVE.snapshot(), 'connectors': CHAT.snapshot(), 'preview_ready': LIVE_PREVIEW is not None})
        if path == "/api/live/catalog":
            return self.respond([{k:v for k,v in e.items() if k not in ('project','script')} for e in LIVE.catalog()])
        if path.startswith('/live-assets/'):
            match = re.fullmatch(r'/live-assets/([a-f0-9]{16})/(voice\.wav|project\.json)', path)
            file = LIVE.assets / match[1] / match[2] if match else None
            return self.serve_file(file) if file and file.is_file() else self.send_error(404)
        if path == '/live-demo.mp4':
            file = OUTPUT / 'live-demo.mp4'
            return self.serve_file(file) if file.is_file() else self.send_error(404)
        if path == "/api/studio":
            return self.respond(studio.load())
        if path == "/exports/serie-completa.zip":
            file = OUTPUT / "serie-completa.zip"
            return self.serve_file(file) if file.is_file() else self.send_error(404)
        if path.startswith("/preview/"):
            match = re.fullmatch(r"/preview/([a-f0-9]{16})/voice\.wav", path)
            file = PREVIEWS / match[1] / "voice.wav" if match else None
            return self.serve_file(file) if file and file.is_file() else self.send_error(404)
        if path == "/api/jobs":
            with JOB_LOCK:
                return self.respond(sorted([public_job(x) for x in JOBS.values()], key=lambda x: x["created"], reverse=True))
        if path.startswith("/api/jobs/"):
            with JOB_LOCK:
                job = JOBS.get(path.rsplit("/", 1)[-1])
                return self.respond(public_job(job) if job else {"error": "Video non trovato"}, 200 if job else 404)
        if path.startswith("/output/"):
            # No arbitrary file access: whitelist project media and generated files.
            match = re.fullmatch(r"/output/([a-f0-9]{12})/(video\.mp4|external\.mp4|poster\.png|voice\.wav|captions\.srt|project\.json|cover\.png|platforms\.json|script\.txt|youtube\.zip|tiktok\.zip|instagram\.zip)", path)
            if not match:
                return self.send_error(404)
            file = OUTPUT / match[1] / match[2]
            if not file.is_file():
                return self.send_error(404)
            return self.serve_file(file)
        if path not in {"/", "/index.html", "/style.css", "/app.js", "/projects.js", "/projects.css", "/navigation.js", "/avatar.js", "/render.html", "/render-page.js",
                        "/languages.js", "/conversation.js", "/vendor/daily.js", "/vendor/DAILY-LICENSE.txt", "/vendor/daily-version.json", "/insights.js", "/youtube-analytics.js", "/business.js", "/clips.js", "/extras.css", "/activity.js", "/delivery.js", "/delivery.css", "/platform.js", "/platform.css", "/character-renderer.js", "/live-control.js", "/live.css", "/live-scene.html", "/live-scene.js", "/live-canvas.js", "/studio.js", "/studio.css", "/vendor/three.module.js", "/vendor/THREE-LICENSE.txt"}:
            return self.send_error(404)
        return super().do_GET()

    def serve_file(self, path):
        size = path.stat().st_size
        start, end = 0, size - 1
        range_header = self.headers.get("Range")
        if range_header:
            match = re.fullmatch(r"bytes=(\d+)-(\d*)", range_header)
            if not match:
                return self.send_error(416)
            start = int(match[1])
            end = min(int(match[2]) if match[2] else end, end)
            if start > end:
                return self.send_error(416)
        self.send_response(206 if range_header else 200)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        if range_header:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with path.open("rb") as stream:
            stream.seek(start)
            remaining = end - start + 1
            while remaining:
                data = stream.read(min(65536, remaining))
                self.wfile.write(data)
                remaining -= len(data)

    def do_POST(self):
        global LIVE_PREVIEW
        if not self.host_valid() or self.headers.get("X-Avatar-Token") != TOKEN:
            return self.respond({"error": "Sessione scaduta. Ricarica la pagina."}, 403)
        try:
            size = int(self.headers.get("Content-Length", 0))
            if urlparse(self.path).path in ('/api/recording-upload', '/api/video-project-import'):
                if not 0<size<=clips.MAX_BYTES:
                    self.close_connection=True
                    return self.respond({'error':'Importa una registrazione fino a 2 GB.'},400)
                if not IMPORT_SLOTS.acquire(blocking=False):
                    self.close_connection=True
                    return self.respond({'error':'Due importazioni già in corso. Attendi prima di riprovare.'},409)
                try:
                    self.connection.settimeout(120)
                    if urlparse(self.path).path == '/api/video-project-import':
                        try:
                            revision = int(self.headers.get('X-Project-Revision', ''))
                            result = video_projects.import_video(self.headers.get('X-Project-ID'), revision,
                                self.rfile, size, unquote(self.headers.get('X-Recording-Name', '')))
                        except Exception:
                            # Rejected/stale imports may leave an unread binary body.
                            self.close_connection = True
                            raise
                        return self.respond(result, 201)
                    return self.respond(clips.import_stream(self.rfile,size,unquote(self.headers.get('X-Recording-Name',''))),201)
                finally:IMPORT_SLOTS.release()
            if urlparse(self.path).path == '/api/character-upload':
                if not 33<=size<=6_000_000:return self.respond({'error':'Immagine oltre 6 MB o vuota.'},400)
                return self.respond(platform_store.upload_png(self.rfile.read(size)))
            if urlparse(self.path).path == '/api/live/frame':
                with LIVE.lock:
                    owner = self.headers.get('X-Scene-Client') == LIVE.lease and LIVE.lease is not None
                if not owner or not 4 <= size <= 250000:
                    return self.respond({'error':'Anteprima non valida.'},400)
                frame=self.rfile.read(size)
                if not frame.startswith(b'\xff\xd8') or not frame.endswith(b'\xff\xd9'):
                    return self.respond({'error':'Formato immagine non valido.'},400)
                LIVE_PREVIEW=frame
                return self.respond({'ok':True})
            if not 0 < size <= (1_100_000 if urlparse(self.path).path=='/api/clip-subtitles' else 128000):
                raise ValueError("Richiesta troppo grande o vuota.")
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError("Richiesta non valida.")
            path = urlparse(self.path).path
            if path == '/api/video-project':
                return self.respond(video_projects.save(data, video_settings(data)))
            if path == '/api/video-project-prepare':
                return self.respond(video_projects.prepare(data.get('id'), data.get('revision')))
            if path == '/api/video-project-render':
                def enqueue_project_clip(project, clip):
                    with JOB_LOCK:
                        check_capacity(1)
                        job = enqueue(project['title'], ' '.join(c['text'] for c in clip['captions']),
                            clip['config'], clip=clip, engine='clip', video_project_id=project['id'],
                            video_project_revision=project['revision'])
                        return public_job(job)
                return self.respond(video_projects.render(data, enqueue_project_clip), 202)
            business_routes={'/api/growth-strategy':growth.save_strategy,'/api/growth-experiment':growth.save_experiment,
                '/api/growth-reference':growth.save_reference,'/api/growth-link':growth.link_publication,
                '/api/growth-observation':growth.save_observation,'/api/growth-import':growth.import_csv,
                '/api/growth-report':growth.report,'/api/policy-review':policy_intelligence.assess,
                '/api/research-plan':market_research.plan}
            if path in business_routes:return self.respond(business_routes[path](data))
            if path == '/api/reference-read':return self.respond(web_sources.collect(data.get('url','')))
            if path == '/api/storage-plan':return self.respond(storage_upload.plan(data))
            if path == '/api/storage-upload':return self.respond(storage_upload.upload(data))
            if path == '/api/insights-settings':return self.respond(insights.settings(data))
            if path == '/api/insights-collect':return self.respond(insights.request_collection(data),202)
            if path == '/api/youtube-analytics':return self.respond(youtube_analytics.fetch_report(data))
            if path == '/api/clip-details':return self.respond(clips.details(data.get('source_id')))
            if path == '/api/clip-subtitles':return self.respond(clips.subtitles(data))
            if path == '/api/clip-suggest':return self.respond(clips.suggest(data))
            if path == '/api/clip-plan':
                plan=clips.prepare(data)
                return self.respond({k:v for k,v in plan.items() if k not in ('source_project','config','scenes')})
            if path == '/api/clip-render':
                clip=clips.prepare(data)
                with JOB_LOCK:
                    check_capacity(1)
                    job=enqueue(clip['title'],' '.join(c['text'] for c in clip['captions']),clip['config'],clip=clip,engine='clip')
                return self.respond(public_job(job),202)
            if path == '/api/activity-add':return self.respond(Activity(ROOT).add(data))
            if path == '/api/activity-remove':return self.respond(Activity(ROOT).remove(data.get('id')))
            routes={'/api/publication-save':publishing.save,'/api/publication-approve':publishing.approve,'/api/publication-simulate':publishing.simulate,'/api/publication-arm':publishing.set_armed,'/api/publication-cancel':publishing.cancel,'/api/publication-check':publishing.check,'/api/publication-metrics':publishing.collect_metrics,
                    '/api/connection-save':service_connections.save,'/api/connection-create':service_connections.create_profile,'/api/connection-switch':service_connections.switch_profile,'/api/broadcast-plan':broadcast.plan,'/api/broadcast-start':broadcast.start,'/api/broadcast-end':broadcast.end}
            if path in routes:return self.respond(routes[path](data))
            if path == '/api/publication-send':return self.respond(publishing.deliver(data['id']),202)
            if path == '/api/connection-verify':return self.respond(service_connections.verify(data['service'],data.get('profile_id')))
            if path == '/api/connection-disconnect':return self.respond(service_connections.disconnect(data['service'],data.get('profile_id')))
            if path == '/api/oauth-youtube':return self.respond(service_connections.oauth_start(BASE_URL,data.get('profile_id'),analytics=data.get('analytics',False),revenue=data.get('revenue',False)))
            if path == '/api/obs':return self.respond(broadcast.obs(data,BASE_URL))
            bridge_routes={'/api/conversation-claim':conversation_bridge.claim,'/api/conversation-heartbeat':conversation_bridge.heartbeat,'/api/conversation-release':conversation_bridge.release,'/api/conversation-ack':conversation_bridge.acknowledge}
            if path in bridge_routes:return self.respond(bridge_routes[path](data))
            if path == '/api/conversation-issue':return self.respond(conversation_bridge.issue(data,LIVE.snapshot()['messages']))
            if path == '/api/broadcast-room':return self.respond(conversation_bridge.claim(data))
            if path == '/api/cloud-plan':return self.respond(cloud_avatar.quote({**data,'planning':True}))
            if path == '/api/cloud-recover':
                with JOB_LOCK:
                    job=JOBS.get(data.get('id'))
                    if not job or job.get('engine')!='heygen' or job['state'] not in ('error','cancelled'):raise ValueError('Scegli una generazione HeyGen interrotta.')
                    _,saved=cloud_avatar.recovery(OUTPUT/job['id']);check_capacity(1)
                    job.update(state='queued',cancelled=False,recover_cloud=True,message='Recupero della stessa generazione HeyGen',progress=0);persist_job(job)
                    EXECUTOR.submit(render_job,job,saved['script'],saved['settings'])
                return self.respond(public_job(job),202)
            if path == '/api/character':return self.respond(platform_store.save_character(data,VOICES))
            if path == '/api/character-activate':
                c=platform_store.activate(data.get('id'))
                return self.respond(effective_settings())
            if path == '/api/campaign':return self.respond(platform_store.save_campaign(data))
            if path == '/api/campaign-source':return self.respond(agent_team.add_source(data))
            if path == '/api/campaign-run':return self.respond(agent_team.start(data),202)
            if path == '/api/campaign-stop':return self.respond(agent_team.stop(data))
            if path == '/api/campaign-content':return self.respond(agent_team.save_content(data))
            if path == '/api/campaign-plan':return self.respond(agent_team.to_plan(data))
            if path == '/api/campaign-metrics':return self.respond(platform_store.metrics(data))
            if path == '/api/platform-budget':return self.respond(platform_store.save_budget(data))
            if path == '/api/integrations':return self.respond(cloud_avatar.keys(data))
            if path == '/api/cloud-quote':
                if data.get('video_project_id'):
                    def quote_project(project):
                        result = cloud_avatar.quote(project, config=project['settings'])
                        with cloud_avatar.LOCK:
                            cloud_avatar.QUOTES[result['quote_id']].update(
                                video_project_id=project['id'], video_project_revision=project['revision'])
                        return result
                    return self.respond(video_projects.quote_generation(data['video_project_id'],
                        data.get('video_project_revision'), quote_project))
                return self.respond(cloud_avatar.quote(data))
            if path == '/api/production':
                production=productions.prepare(data,VOICES)
                with JOB_LOCK:
                    check_capacity(1)
                    job=enqueue(production['title'],'\n\n'.join(s['script'] for s in production['scenes']),production['config'],production=production)
                return self.respond(public_job(job),202)
            if path == '/api/cloud-render':
                with cloud_avatar.LOCK:
                    project_quote = cloud_avatar.QUOTES.get(data.get('quote_id'), {})
                    project_id = project_quote.get('video_project_id')
                    project_revision = project_quote.get('video_project_revision')
                if project_id:
                    def enqueue_project_cloud(project):
                        with JOB_LOCK:
                            check_capacity(1)
                            q = cloud_avatar.consume(data.get('quote_id'))
                            return public_job(enqueue(q['title'], q['script'], q['config'], engine='heygen',
                                cloud_quote=q, video_project_id=project['id'], video_project_revision=project['revision']))
                    return self.respond(video_projects.enqueue_generation(project_id, project_revision,
                        'api', enqueue_project_cloud), 202)
                with JOB_LOCK:
                    check_capacity(1)
                    q=cloud_avatar.consume(data.get('quote_id'))
                    job=enqueue(q['title'],q['script'],q['config'],engine='heygen',cloud_quote=q)
                return self.respond(public_job(job),202)
            if path == '/api/live/config':
                return self.respond(LIVE.save_config(data))
            if path == '/api/live/control':
                return self.respond(LIVE.control(data.get('action')))
            if path == '/api/live/claim':
                return self.respond(LIVE.claim(data.get('client'),data.get('force',False)))
            if path == '/api/live/heartbeat':
                return self.respond(LIVE.heartbeat(data))
            if path == '/api/live/speak':
                return self.respond(LIVE.enqueue(data.get('title','Intervento dalla regia'),data.get('text')))
            if path == '/api/live/remove':
                return self.respond(LIVE.remove(data.get('id')))
            if path == '/api/live/message':
                return self.respond(LIVE.receive(data.get('author','Spettatore'),data.get('text')))
            if path == '/api/live/respond':
                return self.respond(LIVE.respond(data))
            if path == '/api/live/connect':
                return self.respond(CHAT.connect(data))
            if path == '/api/live/disconnect':
                return self.respond(CHAT.disconnect(data.get('platform')))
            if path == "/api/settings":
                return self.respond(providers.save_studio_settings(data, VOICES))
            if path == "/api/persona":
                c=platform_store.snapshot(data.get('character_id'))
                return self.respond(platform_store.save_character({'id':c['id'], 'revision':data.get('revision'),
                    'editorial':{k:data.get(k,v) for k,v in c['editorial'].items()}}, VOICES))
            if path == "/api/rubric":
                return self.respond(studio.save_rubric(data))
            if path == "/api/episode":
                return self.respond(studio.save_episode(data))
            if path == "/api/episode-ready":
                return self.respond(studio.set_ready(data.get('id'), data.get('revision'), data.get('ready', True)))
            if path == "/api/series-render":
                ids = data.get('ids')
                if not isinstance(ids, list) or not ids:
                    raise ValueError('Scegli gli episodi pronti da produrre.')
                with JOB_LOCK:
                    check_capacity(len(ids))
                    selected, persona, rubrics = studio.claim_episodes(ids)
                    jobs = []
                    try:
                        for episode in selected:
                            rubric = next(r for r in rubrics if r['id'] == episode['rubric_id'])
                            config = languages.apply(effective_settings(episode.get('character_id')),episode)
                            job = enqueue(episode['title'], episode['script'], config,
                                          episode=episode, persona=config['character']['editorial'], rubric=rubric)
                            jobs.append(public_job(job))
                    except Exception:
                        queued = {j['episode']['id'] for j in jobs}
                        for episode in selected:
                            if episode['id'] not in queued:
                                studio.finish_episode(episode['id'], episode['revision'], episode.get('job_id'), False)
                        raise
                return self.respond({'jobs': jobs}, 202)
            if path == "/api/series-export":
                with EXPORT_LOCK:
                    with JOB_LOCK:
                        episodes = studio.load()['episodes']
                        jobs = [public_job(JOBS[e['job_id']]) for e in episodes if e['status'] == 'ready'
                                and e.get('job_id') in JOBS and JOBS[e['job_id']]['state'] == 'done'
                                and JOBS[e['job_id']].get('episode', {}).get('revision') == e['revision']]
                    if not jobs:
                        raise ValueError('Produci prima almeno un episodio del piano.')
                    packages.series_package(jobs)
                return self.respond({'url': '/exports/serie-completa.zip', 'count': len(jobs)})
            if path == "/api/preview":
                script = data.get('script', '')
                if not isinstance(script, str) or not 2 <= len(script.strip()) <= 2400:
                    raise ValueError('Scrivi un copione tra 2 e 2400 caratteri.')
                config = video_settings(data)
                identity = hashlib.sha256(json.dumps([script.strip(), config['voice'], config['rate'], 2]).encode()).hexdigest()[:16]
                folder = PREVIEWS / identity
                with PREVIEW_LOCK:
                    folder.mkdir(exist_ok=True)
                    if not (folder / 'timeline.json').exists():
                        timeline = media.synthesize(script.strip(), config, folder, lambda p,m: None)
                        providers.atomic_json(folder / 'timeline.json', timeline)
                    timeline = json.loads((folder / 'timeline.json').read_text())
                return self.respond({'audio': f'/preview/{identity}/voice.wav', 'project': {**timeline, 'settings': config}})
            if path == '/api/translate':
                if not SCRIPT_LOCK.acquire(blocking=False):return self.respond({'error':'Una bozza è già in preparazione.'},409)
                try:return self.respond(providers.translate_script(data.get('script'),video_settings(data,require_voice=False)))
                finally:SCRIPT_LOCK.release()
            if path == "/api/script":
                if not SCRIPT_LOCK.acquire(blocking=False):
                    return self.respond({"error": "È già in corso la scrittura di un copione."}, 409)
                try:
                    config = video_settings(data,require_voice=False)
                    config.update(providers.editorial_options(data))
                    config['editorial_context'] = studio.prompt_context(data.get('rubric_id'), config['character']['id'])+'\nPersonaggio: '+config['character']['personality']
                    result = providers.generate_script(data.get("topic"), data.get("seconds", 30), config)
                    return self.respond(result)
                finally:
                    SCRIPT_LOCK.release()
            if path == "/api/render":
                if data.get('video_project_id'):
                    def enqueue_project_local(project):
                        with JOB_LOCK:
                            check_capacity(1)
                            return public_job(enqueue(project['title'], project['script'], project['settings'],
                                video_project_id=project['id'], video_project_revision=project['revision']))
                    return self.respond(video_projects.enqueue_generation(data['video_project_id'],
                        data.get('video_project_revision'), 'local', enqueue_project_local), 202)
                script = data.get("script", "")
                if not isinstance(script, str) or not 2 <= len(script.strip()) <= 2400:
                    raise ValueError("Scrivi un copione tra 2 e 2400 caratteri.")
                with JOB_LOCK:
                    check_capacity(1)
                    job = enqueue(str(data.get("title") or "Video senza titolo")[:80], script.strip(), video_settings(data))
                return self.respond(public_job(job), 202)
            if path == "/api/cancel":
                with JOB_LOCK:
                    job = JOBS.get(str(data.get("id")))
                    if not job or job["state"] not in ("queued", "running"):
                        raise ValueError("Nessun video in lavorazione da annullare.")
                    job["cancelled"] = True
                    if job.get("process"):
                        job["process"].terminate()
                return self.respond({"ok": True})
            if path == "/api/reveal":
                identity = str(data.get("id", ""))
                file = OUTPUT / identity / "video.mp4"
                if identity not in JOBS or not file.is_file():
                    raise ValueError("Video non trovato.")
                subprocess.run(["/usr/bin/open", "-R", str(file)], check=True, timeout=10)
                return self.respond({"ok": True})
            return self.respond({"error": "Operazione non trovata"}, 404)
        except video_projects.Conflict as exc:
            return self.respond({'error': str(exc)}, 409)
        except (ValueError, TypeError, subprocess.TimeoutExpired) as exc:
            return self.respond({"error": str(exc)}, 400)
        except Exception:
            traceback.print_exc()
            return self.respond({"error": "Errore interno. Controlla il terminale dell'app."}, 500)


if __name__ == "__main__":
    server = STARTUP_SERVER
    server.RequestHandlerClass = Handler
    BASE_URL = f"http://127.0.0.1:{server.server_port}"
    publishing.start()
    insights.start()
    conversation_bridge.recover()
    broadcast.recover()
    print(f"Avatar Studio pronto: {BASE_URL}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        with JOB_LOCK:
            for job in JOBS.values():
                if job["state"] in ("queued", "running"):
                    job["cancelled"] = True
                    if job.get("process"):
                        job["process"].terminate()
        LIVE.close()
        CHAT.close()
        agent_team.close()
        publishing.close()
        insights.close()
        EXECUTOR.shutdown(wait=False, cancel_futures=True)
        server.server_close()

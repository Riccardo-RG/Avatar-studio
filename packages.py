"""Local platform-ready packages. This module never publishes or contacts a platform."""
import json
from pathlib import Path
import re
import zipfile

import providers

ROOT = Path(__file__).resolve().parent
PLATFORMS = ('youtube', 'tiktok', 'instagram')


def metadata(project):
    episode = project.get('episode', {})
    rubric = project.get('rubric', {})
    title = episode.get('title') or project.get('title') or 'Un video dal mio avatar'
    name = project['settings']['name']
    lang=project['settings'].get('language','it')
    words={'it':('Tu cosa ne pensi?','Personaggio virtuale. Voce sintetica. Scene e osservazioni a scopo creativo.','Raccontalo nei commenti.'),'en':('What do you think?','Virtual character. Synthetic voice. Scenes and observations for creative purposes.','Tell us in the comments.'),'es':('¿Qué opinas?','Personaje virtual. Voz sintética. Escenas y observaciones con fines creativos.','Cuéntalo en los comentarios.')}
    question = episode.get('question') or words.get(lang,words['it'])[0]
    summary = re.split(r'(?<=[.!?])\s+', project['script'].strip())[0]
    tag = re.sub(r'[^\w]', '', rubric.get('tag', 'PersonaggioVirtuale'))
    disclosure=words.get(lang,words['it'])[1];comment=words.get(lang,words['it'])[2]
    avatar_tag={'it':'AvatarItaliano','en':'EnglishAvatar','es':'AvatarEnEspañol'}.get(lang,'Avatar')
    reels_tag='ReelsItalia' if lang=='it' else 'Reels';virtual_tag='PersonaggioVirtuale' if lang=='it' else 'VirtualCharacter' if lang=='en' else 'PersonajeVirtual'
    result = {
        'youtube': {'title': title[:95], 'description': f'{summary}\n\n{question}\n\n{disclosure}\n\n#Shorts #{tag}',
                    'tags': [name, rubric.get('name', 'Avatar'), 'Shorts'], 'format': 'YouTube Shorts · 9:16'},
        'tiktok': {'title': title[:80], 'description': f'{question}\n\n{disclosure}\n#{tag} #{avatar_tag}',
                   'format': 'TikTok · 9:16'},
        'instagram': {'title': title[:80], 'description': f'{summary}\n\n{question}\n{comment}\n\n{disclosure}\n\n#{tag} #{reels_tag} #{virtual_tag}',
                      'format': 'Instagram Reels · 9:16'},
    }
    for info in result.values():info['language']=lang
    if project.get('clip'):
        for platform,info in result.items():
            info['description']=(summary+'\n\n' if summary else '')+'Clip estratta da una registrazione. Rivedi il testo prima della pubblicazione.'
            if 'tags' in info:info['tags']=['Clip']
    aspect=project['settings'].get('format','portrait')
    if aspect!='portrait':
        label='16:9' if aspect=='landscape' else '1:1'
        result['youtube']['description']=result['youtube']['description'].replace('#Shorts','#Video')
        result['youtube']['tags']=[t for t in result['youtube']['tags'] if t!='Shorts']
        for platform in result:result[platform]['format']=platform.title()+' · '+label
        result['instagram']['description']=result['instagram']['description'].replace('#ReelsItalia','#ContenutiOriginali')
    return result


def make_packages(folder, project):
    details = metadata(project)
    providers.atomic_json(folder / 'platforms.json', details)
    (folder / 'script.txt').write_text(project['script'] + '\n', encoding='utf-8')
    aspect={'portrait':'9:16','landscape':'16:9','square':'1:1'}[project['settings'].get('format','portrait')]
    caption_note=('Sottotitoli impressi nel video; SRT separato facoltativo.' if project.get('captions_burned',not project.get('clip')) else 'Sottotitoli disponibili nel file SRT, da aggiungere sulla piattaforma.' if project.get('captions') else 'Nessun sottotitolo disponibile; il file SRT è vuoto.')
    readme = ('Pacchetto locale: nessun contenuto è stato pubblicato.\n\n'
              f'video.mp4: video H.264 in formato {aspect}, con traccia audio. {caption_note}\n'
              'cover.png: copertina da usare dove la piattaforma consente un’immagine personalizzata.\n'
              'captions.srt: tempi relativi a questo video; evita di duplicare eventuali sottotitoli già visibili.\n'
              'post.txt: titolo e descrizione adattati; rileggili e modificali prima del caricamento.\n'
              'Controlla le impostazioni di visibilità e le eventuali etichette AI nella piattaforma.\n'
              'La data nel piano è soltanto organizzativa: non programma una pubblicazione.\n')
    for platform, info in details.items():
        with zipfile.ZipFile(folder / f'{platform}.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=2) as archive:
            for filename in ['video.mp4', 'cover.png', 'captions.srt', 'script.txt']:
                archive.write(folder / filename, filename)
            archive.writestr('post.txt', info['title'] + '\n\n' + info['description'] + '\n')
            archive.writestr('metadata.json', json.dumps(info, ensure_ascii=False, indent=2))
            archive.writestr('LEGGIMI.txt', readme)
    return {platform: f"/output/{folder.name}/{platform}.zip" for platform in PLATFORMS}


def series_package(jobs):
    """Export completed current revisions, once per user request."""
    output = ROOT / 'output'
    temporary = output / 'serie-completa.tmp'
    target = output / 'serie-completa.zip'
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=2) as archive:
        manifest = []
        for index, job in enumerate(jobs, 1):
            folder = output / job['id']
            slug = re.sub(r'[^a-zA-Z0-9]+', '-', job['title']).strip('-').lower()[:60]
            prefix = f'{index:02d}-{slug}'
            for filename in ('video.mp4', 'cover.png', 'captions.srt', 'script.txt', 'platforms.json', 'project.json'):
                archive.write(folder / filename, f'{prefix}/{filename}')
            metadata_path = folder / 'platforms.json'
            for platform, info in json.loads(metadata_path.read_text()).items():
                archive.writestr(f'{prefix}/{platform}.txt', info['title'] + '\n\n' + info['description'])
            manifest.append({'title': job['title'], 'folder': prefix, 'duration': job['duration'],
                             'planned_date': job.get('episode', {}).get('planned_date', ''), 'published': False})
        archive.writestr('indice.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr('LEGGIMI.txt', 'Tutti i contenuti sono salvati localmente. Nessun post è stato pubblicato.\nOgni cartella contiene un MP4 comune e tre testi di accompagnamento distinti.\n')
    temporary.replace(target)
    return target

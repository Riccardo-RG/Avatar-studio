"""Verify actual exported streams and generate a contact sheet for visual QA."""
import array
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'deps'))
import imageio_ffmpeg
from PIL import Image, ImageDraw

jobs = json.loads((ROOT / 'output/acceptance.json').read_text())
report = []
sheet = Image.new('RGB', (810, len(jobs) * 530), '#111811')
draw = ImageDraw.Draw(sheet)
for row, job in enumerate(jobs):
    folder = ROOT / 'output' / job['id']
    project = json.loads((folder / 'project.json').read_text())
    frames = imageio_ffmpeg.read_frames(str(folder / 'video.mp4'))
    metadata = next(frames)
    assert metadata['size'][0] * 16 == metadata['size'][1] * 9
    assert metadata['codec'] == 'h264'
    duration = metadata['duration']
    assert abs(duration - project['duration']) < .2
    targets = [round(t * metadata['fps']) for t in [.6, duration * .5, max(.6,duration - .8)]]
    selected = {}
    count = 0
    for index, frame in enumerate(frames):
        count += 1
        if index in targets:
            selected[index] = Image.frombytes('RGB', metadata['size'], frame)
    assert count >= (duration - .2) * metadata['fps']
    assert len(selected) == len(set(targets))
    first, last = selected[targets[0]].tobytes(), selected[targets[-1]].tobytes()
    assert first != last, 'Static export'
    audio = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-i', str(folder / 'video.mp4'),
        '-vn', '-f', 's16le', '-acodec', 'pcm_s16le', '-ac', '1', '-ar', '22050', 'pipe:1'],
        capture_output=True, check=True).stdout
    samples = array.array('h', audio)
    rms = math.sqrt(sum(x*x for x in samples) / len(samples)) / 32768
    assert rms > .005, 'Missing or silent audio'
    assert abs(len(samples) / 22050 - duration) < .2
    captions = project['captions']
    assert all(0 <= c['start'] < c['end'] <= duration + .1 for c in captions)
    assert all(captions[i]['end'] <= captions[i+1]['start'] for i in range(len(captions)-1))
    assert ' '.join(c['text'] for c in captions) == ' '.join(project['script'].split())
    draw.text((15, row*530 + 8), job['title'].replace('·','/'), fill='#d4f7ba')
    for col, frame_index in enumerate(targets):
        thumb = selected[frame_index].resize((252,448))
        sheet.paste(thumb, (col * 270 + 9, row * 530 + 34))
        draw.text((col*270+15,row*530+491), f'{frame_index/metadata["fps"]:.1f} s',fill='#dae5d4')
    item = {'id': job['id'], 'duration': duration, 'frames': count, 'size': metadata['size'],
            'codec': metadata['codec'], 'audio_rms': round(rms,4), 'captions': len(captions),
            'script_preserved': True, 'decoded_all_frames': True}
    report.append(item)
    print(json.dumps(item), flush=True)
sheet.save(ROOT / 'output/qa-contact-sheet.jpg', quality=90)
(ROOT / 'output/verification.json').write_text(json.dumps(report, indent=2))

"""Speech and timed captions, independent of the visual avatar."""
import functools
import array
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import threading
import wave
import runtime_config

ROOT = Path(__file__).resolve().parent
runtime_config.dependency_path('deps')
NEURAL_LOCK = threading.Lock()
NEURAL_VOICE = None


def neural_voice():
    global NEURAL_VOICE
    if NEURAL_VOICE is None:
        runtime_config.dependency_path('voice-deps')
        from piper import PiperVoice
        NEURAL_VOICE = PiperVoice.load(str(ROOT / 'models/piper/it_IT-paola-medium.onnx'), include_alignments=True)
    return NEURAL_VOICE


def ffmpeg_path():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


@functools.lru_cache(maxsize=1)
def voice_catalog():
    text = subprocess.check_output(['/usr/bin/say', '-v', '?'], text=True)
    result=[];seen=set()
    for line in text.splitlines():
        match=re.match(r'^(.*?)\s+(it|en|es)_([A-Z]{2})\s+#',line)
        if match:
            identity=match[1].strip()
            if identity not in seen:
                seen.add(identity)
                result.append({'id':identity,'language':match[2],'locale':match[2]+'-'+match[3]})
    if (ROOT/'models/piper/it_IT-paola-medium.onnx').exists():result.insert(0,{'id':'piper:paola','language':'it','locale':'it-IT'})
    return result


def voices():return [voice['id'] for voice in voice_catalog()]


def viseme(phoneme):
    if phoneme in '^$ _.,!?;:' or phoneme in ('p', 'b', 'm'):
        return 'closed'
    if any(v in phoneme for v in 'uʊoɔw'):
        return 'round'
    if any(v in phoneme for v in 'iɪeɛj'):
        return 'wide'
    if any(v in phoneme for v in 'aɑɐ'):
        return 'open'
    return 'soft'


def neural_sentence(sentence, rate):
    voice = neural_voice()
    from piper import SynthesisConfig
    pcm = bytearray()
    alignments = []
    for chunk in voice.synthesize(sentence, syn_config=SynthesisConfig(
            length_scale=220 / rate, noise_scale=.55, noise_w_scale=.65, volume=.78), include_alignments=True):
        if chunk.sample_rate != 22050:
            raise ValueError('La voce neurale richiede una frequenza di 22050 Hz.')
        start = len(pcm) / 44100
        raw = chunk.audio_int16_bytes
        cursor = start
        for item in chunk.phoneme_alignments or []:
            end = min(start + len(raw) / 44100, cursor + int(item.num_samples) / chunk.sample_rate)
            if end > cursor:
                alignments.append({'start': cursor, 'end': end, 'phoneme': item.phoneme, 'shape': viseme(item.phoneme)})
            cursor = end
        pcm.extend(raw)
    return bytes(pcm), alignments


def sentence_captions(sentence, duration, alignments):
    parts = split_captions(sentence)
    words = sentence.split()
    boundaries = [0.0] + [a['end'] for a in alignments if a['phoneme'] == ' '] + [duration]
    exact = len(boundaries) == len(words) + 1
    captions, word_index, weight_index = [], 0, 0
    weights = [max(2, len(w)) for w in words]
    total_weight = sum(weights)
    for part in parts:
        count = len(part.split())
        next_word = word_index + count
        next_weight = weight_index + sum(weights[word_index:next_word])
        start = boundaries[word_index] if exact else duration * weight_index / total_weight
        end = boundaries[next_word] if exact else duration * next_weight / total_weight
        captions.append({'start': start, 'end': end, 'text': part})
        word_index, weight_index = next_word, next_weight
    return captions, 'phoneme_boundaries' if exact else 'sentence_estimate'


def split_captions(text):
    # Short speech segments give exact segment timing without a transcription API.
    pieces = re.split(r"(?<=[.!?;:])\s+", text.strip())
    result = []
    for piece in pieces:
        words = piece.split()
        part = []
        for word in words:
            if part and (len(" ".join(part + [word])) > 76 or len(part) >= 12):
                result.append(" ".join(part))
                part = []
            part.append(word)
        if part:
            result.append(" ".join(part))
    return result


def srt_time(t):
    n = round(t * 1000)
    return f"{n // 3600000:02}:{n // 60000 % 60:02}:{n // 1000 % 60:02},{n % 1000:03}"


def synthesize(text, config, folder, progress):
    if config['voice'].startswith('piper:'):
        with NEURAL_LOCK:
            return _synthesize(text, config, folder, progress)
    return _synthesize(text, config, folder, progress)


def _synthesize(text, config, folder, progress):
    if not isinstance(text, str) or not 2 <= len(text.strip()) <= 2400:
        raise ValueError("Il copione deve contenere tra 2 e 2400 caratteri.")
    if "[[" in text or "]]" in text:
        raise ValueError("Rimuovi i comandi vocali tra doppie parentesi dal copione.")
    neural = config['voice'] == 'piper:paola'
    # Synthesize whole sentences, never interrupt the voice at a caption boundary.
    chunks = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text.strip()) if s.strip()] if neural else split_captions(text)
    audio = bytearray(b"\0" * 11024)  # 0.25 s lead-in at 22050 Hz, 16-bit mono
    captions = []
    phonemes, alignment_methods = [], set()
    for index, chunk in enumerate(chunks):
        progress(5 + round(index / len(chunks) * 20), f"Voce · frase {index + 1}/{len(chunks)}")
        alignments = []
        if neural:
            raw, alignments = neural_sentence(chunk, config['rate'])
        else:
            txt, aiff, wav = (folder / ("part" + ext) for ext in (".txt", ".aiff", ".wav"))
            txt.write_text(chunk, encoding="utf-8")
            subprocess.run(["/usr/bin/say", "-v", config["voice"], "-r", str(config["rate"]),
                            "-f", str(txt), "-o", str(aiff)], check=True, capture_output=True, timeout=60)
            subprocess.run(["/usr/bin/afconvert", "-f", "WAVE", "-d", "LEI16@22050", "-c", "1",
                            str(aiff), str(wav)], check=True, capture_output=True, timeout=30)
            with wave.open(str(wav), "rb") as source:
                raw = source.readframes(source.getnframes())
        start = len(audio) / 44100
        audio.extend(raw)
        if neural:
            timed, method = sentence_captions(chunk, len(raw) / 44100, alignments)
            alignment_methods.add(method)
            captions.extend({**c, 'start': start + c['start'], 'end': start + c['end']} for c in timed)
            phonemes.extend({'start': start + a['start'], 'end': start + a['end'], 'shape': a['shape']} for a in alignments)
        else:
            captions.append({"start": start, "end": len(audio) / 44100, "text": chunk})
            alignment_methods.add('speech_segment')
        audio.extend(b"\0" * (2204 if neural else 3528))
    audio.extend(b"\0" * 13230)
    duration = len(audio) / 44100
    if duration > 180:
        raise ValueError("Il video supera 3 minuti. Accorcia il copione.")
    with wave.open(str(folder / "voice.wav"), "wb") as dest:
        dest.setparams((1, 2, 22050, 0, "NONE", "not compressed"))
        dest.writeframes(audio)
    values = array.array("h", audio)
    envelope = []
    for offset in range(0, len(values), 735):
        block = values[offset:offset + 735]
        rms = math.sqrt(sum(x*x for x in block) / max(1, len(block))) / 32768
        envelope.append(round(min(1.0, rms * 9), 4))
    srt = "\n\n".join(f"{i+1}\n{srt_time(c['start'])} --> {srt_time(c['end'])}\n{c['text']}"
                        for i, c in enumerate(captions)) + "\n"
    (folder / "captions.srt").write_text(srt, encoding="utf-8")
    for name in ("part.txt", "part.aiff", "part.wav"):
        (folder / name).unlink(missing_ok=True)
    return {"duration": duration, "captions": captions, "envelope": envelope, "envelope_fps": 30,
            'phonemes': phonemes, 'voice_engine': 'piper' if neural else 'macos',
            'caption_alignment': sorted(alignment_methods)}

"""Convert a local browser WebM recording to a shareable MP4 without cutting the audio."""
import argparse
from pathlib import Path
import subprocess
import media

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('source',type=Path)
    parser.add_argument('target',type=Path)
    args=parser.parse_args()
    if not args.source.is_file() or args.source.suffix.lower()!='.webm':parser.error('Scegli una registrazione WebM locale.')
    if args.target.suffix.lower()!='.mp4':parser.error('Il file di destinazione deve essere un MP4.')
    if args.target.exists():parser.error('Il file di destinazione esiste già: scegli un nuovo nome.')
    subprocess.run([media.ffmpeg_path(),'-hide_banner','-loglevel','error','-n','-protocol_whitelist','file,pipe',
        '-i',str(args.source.resolve()),'-vf','fps=24,tpad=stop_mode=clone:stop=-1',
        '-c:v','libx264','-preset','veryfast','-crf','22','-pix_fmt','yuv420p','-c:a','aac','-b:a','128k',
        '-shortest','-movflags','+faststart',str(args.target.resolve())],check=True)
    print(args.target.resolve())

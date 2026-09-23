"""Verify the actual browser-recorded demonstration after MP4 conversion."""
import array
import json
import math
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'deps'))
import imageio_ffmpeg
from PIL import Image,ImageDraw
p=ROOT/'output/live-demo.mp4';reader=imageio_ffmpeg.read_frames(str(p));meta=next(reader)
assert meta['size']==(1280,720) and meta['codec']=='h264'
assert meta['duration']>25
count=0;selected={};targets=[round(t*meta['fps']) for t in [3,meta['duration']*.5,meta['duration']-2]]
for i,frame in enumerate(reader):
 count+=1
 if i in targets:selected[i]=Image.frombytes('RGB',meta['size'],frame)
assert len(selected)==3 and len({im.tobytes() for im in selected.values()})==3
assert count>=(meta['duration']-.2)*meta['fps']
raw=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-i',str(p),'-vn','-f','s16le','-acodec','pcm_s16le','-ac','1','-ar','22050','pipe:1'],capture_output=True,check=True).stdout
values=array.array('h',raw);rms=math.sqrt(sum(x*x for x in values)/len(values))/32768
assert rms>.005
assert abs(len(values)/22050-meta['duration'])<.2
sheet=Image.new('RGB',(960,3*290),'#111b1e');draw=ImageDraw.Draw(sheet)
for row,index in enumerate(targets):
 sheet.paste(selected[index].resize((480,270)),(10,row*290+10))
 draw.text((520,row*290+50),f'Live recording / {index/meta["fps"]:.1f} s',fill='#b4fa86')
sheet.save(ROOT/'output/live-media-contact.jpg')
report={'duration':meta['duration'],'resolution':meta['size'],'fps':meta['fps'],'frames':count,'audio_rms':round(rms,4),'decoded_all_frames':True,'distinct_sampled_frames':True,'browser_recording':True,'bytes':p.stat().st_size}
(ROOT/'output/live-media-verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))

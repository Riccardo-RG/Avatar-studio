import {Avatar,timelineAt} from './character-renderer.js';
const id=new URLSearchParams(location.search).get('job');
const response=await fetch(`/output/${encodeURIComponent(id)}/project.json`);
if(!response.ok)throw Error('Progetto non trovato');
const project=await response.json(),canvas=document.querySelector('#frame'),resolution=project.settings.resolution,format=project.settings.format||'portrait';
const visuals=(project.presentation||project.settings.presentation)==='visuals';
if(visuals&&(!(project.scenes?.length)||project.scenes.some(scene=>!scene.image)))throw Error('Ogni scena del montaggio con sole immagini richiede un’immagine.');
canvas.width=format==='landscape'?Math.round(resolution*16/9):resolution;canvas.height=format==='portrait'?Math.round(resolution*16/9):resolution;
const portrait=format==='portrait'?canvas:document.createElement('canvas');
const avatar=visuals?null:new Avatar(portrait,project.settings,resolution);if(avatar)await avatar.ready;
const images=new Map();
for(const scene of project.scenes||[])if(scene.image&&!images.has(scene.image)){const img=new Image();await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=()=>reject(Error('Immagine scena non disponibile'));img.src=scene.image;});images.set(scene.image,img);}
let external;
if(project.external_video){external=document.createElement('video');external.muted=true;external.preload='auto';external.src=`/output/${encodeURIComponent(id)}/external.mp4`;await new Promise((resolve,reject)=>{external.onloadeddata=resolve;external.onerror=()=>reject(Error('Video realistico non disponibile'));});}
const ctx=canvas.getContext('2d'),w=canvas.width,h=canvas.height,k=resolution/720;
function lines(text,x,y,maxWidth,fontSize,lineHeight,maxLines=5){ctx.font=`600 ${fontSize}px -apple-system,sans-serif`;ctx.textAlign='left';const result=[];let line='';for(const word of text.split(/\s+/)){const next=line?line+' '+word:word;if(ctx.measureText(next).width>maxWidth&&line){result.push(line);line=word;}else line=next;}if(line)result.push(line);result.slice(0,maxLines).forEach((l,i)=>ctx.fillText(l,x,y+i*lineHeight,maxWidth));return result.length;}
function photoOverlay(caption,name){if(!visuals){ctx.fillStyle='#101a20cc';ctx.fillRect(0,0,w,76*k);ctx.fillStyle='white';ctx.font=`600 ${22*k}px sans-serif`;ctx.textAlign='left';ctx.fillText(name+' · PERSONAGGIO VIRTUALE',28*k,48*k,w-50*k);}if(caption){ctx.fillStyle='#101a20ed';ctx.fillRect(24*k,h*.75,w-48*k,h*.22);ctx.fillStyle='white';lines(caption,44*k,h*.8,w-88*k,30*k,40*k,5);}}
window.renderFrame=async time=>{
 const point=timelineAt(project,time),scene=(project.scenes||[]).find(s=>time>=s.start&&time<s.end)||(project.scenes||[]).at(-1),settings=scene?.settings||project.settings;
 if(external){const target=Math.min(time,Math.max(0,external.duration-.05));if(Math.abs(external.currentTime-target)>.0001)await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Decodifica video esterno scaduta')),10000);external.onseeked=()=>{clearTimeout(timer);resolve();};external.currentTime=target;});const scale=Math.max(w/external.videoWidth,h/external.videoHeight),vw=external.videoWidth*scale,vh=external.videoHeight*scale;ctx.drawImage(external,(w-vw)/2,(h-vh)/2,vw,vh);photoOverlay(point.caption,settings.name);}
 else if(scene?.image){const img=images.get(scene.image),scale=Math.max(w/img.width,h/img.height),iw=img.width*scale,ih=img.height*scale;ctx.drawImage(img,(w-iw)/2,(h-ih)/2,iw,ih);photoOverlay(point.caption,settings.name);}
 else {avatar.setAppearance(settings);await avatar.ready;avatar.hideLabels=format!=='portrait';avatar.draw(time,point.amplitude,format==='portrait'?point.caption:'',point.progress,point.shape,project.rubric?.name||'');if(format!=='portrait'){ctx.fillStyle=settings.background;ctx.fillRect(0,0,w,h);const pw=h*9/16;ctx.drawImage(portrait,0,0,pw,h);const x=pw+24*k,right=w-x-30*k;ctx.fillStyle=settings.accent;lines(settings.name.toUpperCase(),x,64*k,right,22*k,30*k);ctx.fillStyle='#ecf2e8';lines(project.title,x,130*k,right,format==='landscape'?36*k:25*k,format==='landscape'?46*k:34*k,3);ctx.fillStyle='#0a1116';ctx.fillRect(x-12*k,h*.46,right+20*k,h*.38);ctx.fillStyle='#f1f5ef';lines(point.caption,x,h*.53,right,format==='landscape'?30*k:23*k,format==='landscape'?43*k:34*k,6);ctx.fillStyle='#91a58a';lines('PERSONAGGIO VIRTUALE · VOCE SINTETICA',x,h-48*k,right,12*k,18*k,2);}}
 return canvas.toDataURL('image/png');
};
window.renderCover=async()=>{if(!external&&!project.scenes&&format==='portrait')return avatar.cover(project.episode?.cover||project.title||project.settings.name,project.rubric?.name||'');await window.renderFrame(0);if(format==='portrait')photoOverlay(project.title,project.settings.name);return canvas.toDataURL('image/png');};
await window.renderFrame(0);window.renderReady=true;

import {Avatar,timelineAt} from './character-renderer.js';
export class LiveCanvas {
 constructor(canvas,settings){this.canvas=canvas;canvas.width=1280;canvas.height=720;this.ctx=canvas.getContext('2d');this.portrait=document.createElement('canvas');this.avatar=new Avatar(this.portrait,settings,360);this.avatar.hideLabels=true;this.settings=settings;}
 lines(text,x,y,width,size=32,lineHeight=44,max=4,color='#edf5e9'){
  const c=this.ctx;c.fillStyle=color;c.font=`550 ${size}px -apple-system, BlinkMacSystemFont, sans-serif`;c.textAlign='left';let line='',lines=[];
  for(const word of text.split(/\s+/)){const next=line?line+' '+word:word;if(c.measureText(next).width>width&&line){lines.push(line);line=word;}else line=next;}
  if(line)lines.push(line);if(lines.length>max){lines=lines.slice(0,max);lines[max-1]=lines[max-1].replace(/\s+\S+$/,'')+'…';}lines.forEach((l,i)=>c.fillText(l,x,y+i*lineHeight,width));
 }
 draw(state,project,time,idleTime){
  const c=this.ctx,current=state.current,config=state.config||{},settings=current?.settings||state.character_settings||this.settings,accent=settings.accent||'#b4fa86';
  const playing=state.phase==='running'&&current&&project;
  const p=playing?timelineAt(project,time):{caption:'',amplitude:0,progress:0,shape:'closed'};
  this.avatar.setAppearance(settings);this.avatar.draw(playing?time:idleTime,p.amplitude,'',p.progress,p.shape);
  c.fillStyle='#111b1e';c.fillRect(0,0,1280,720);
  const glow=c.createRadialGradient(250,260,30,250,300,700);glow.addColorStop(0,accent+'18');glow.addColorStop(1,'#111b1e');c.fillStyle=glow;c.fillRect(0,0,1280,720);
  c.drawImage(this.portrait,25,20,382.5,680);
  c.strokeStyle='#b6d6c02a';c.beginPath();c.moveTo(435,55);c.lineTo(435,656);c.stroke();
  c.textAlign='left';c.font='600 18px -apple-system, sans-serif';c.fillStyle=accent;c.fillText((settings.name||'NOVA').toUpperCase()+' / LIVE STUDIO',486,77);
  c.font='400 12px -apple-system, sans-serif';c.fillStyle='#91a897';c.fillText('PERSONAGGIO VIRTUALE · VOCE SINTETICA',486,105);
  const label=state.phase==='paused'?'PAUSA':state.phase==='emergency'?'SESSIONE INTERROTTA':state.phase==='finished'?'A PRESTO':state.phase==='idle'?'IN ATTESA':current?.kind==='reply'?'DALLA CONVERSAZIONE':current?'IN SCENA':'TRA UN INTERVENTO E L’ALTRO';
  c.fillStyle='#22342d';c.beginPath();c.roundRect(486,144,Math.min(680,label.length*8+30),32,7);c.fill();c.fillStyle=accent;c.font='600 12px -apple-system, sans-serif';c.fillText(label,500,165);
  this.lines(current?.title||config.title||'Piccole cose umane',486,226,718,42,52,2);
  c.fillStyle='#0b1318aa';c.beginPath();c.roundRect(470,340,748,224,18);c.fill();
  const text=state.phase==='paused'?'Facciamo una piccola pausa.':state.phase==='emergency'?'La sessione è stata interrotta.':state.phase==='finished'?'Grazie per essere stati qui. Alla prossima conversazione.':p.caption||(!current?config.tagline||'Un robot, tre rubriche e le vostre domande.':'');
  this.lines(text,498,396,686,30,44,4);
  const a=p.amplitude;for(let i=0;i<28;i++){const h=3+(Math.sin(idleTime*8+i*.8)*.5+.5)*a*24;c.fillStyle=accent;c.fillRect(490+i*6,604-h/2,3,h);}
  c.fillStyle='#93aa98';c.font='400 14px -apple-system, sans-serif';c.fillText(state.phase==='running'?'Una piccola idea alla volta.':'Lo studio resta qui.',690,610);
  c.fillStyle='#ffffff18';c.fillRect(486,642,716,3);c.fillStyle=accent;c.fillRect(486,642,716*Math.min(1,p.progress),3);
  const next=state.queue?.find(q=>q.state==='ready');c.font='400 12px -apple-system, sans-serif';c.fillStyle='#7f9788';c.fillText(next?'TRA POCO  /  '+next.title:'SCENE ORIGINALI · STORIE E OSSERVAZIONI CREATIVE',486,675,718);
 }
}

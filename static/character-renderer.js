import {Avatar as RobotAvatar,timelineAt} from './avatar.js';
export {timelineAt};
export class Avatar {
 constructor(canvas,settings,width=360){this.canvas=canvas;this.width=width;canvas.width=width;canvas.height=Math.round(width*16/9);this.ctx=canvas.getContext('2d');this.setAppearance(settings);}
 setAppearance(settings){this.settings={...this.settings,...settings};const c=this.settings.character||{kind:'robot',id:'nova'};const key=c.id+':'+c.revision+':'+c.kind+':'+c.image;if(key===this.key){this.robot?.setAppearance(this.settings);return;}this.key=key;this.character=c;if(c.kind==='robot'&&this.robot){this.robot.setAppearance(this.settings);return;}this.robot?.dispose();this.robot=null;this.image=null;if(c.kind==='robot'){this.robot=new RobotAvatar(this.canvas,this.settings,this.width);this.ready=Promise.resolve();}else{const img=new Image();this.ready=new Promise((resolve,reject)=>{img.onload=()=>{if(this.key===key)this.image=img;resolve();};img.onerror=()=>reject(Error('Immagine del personaggio non disponibile.'));});this.ready.catch(()=>{});img.src=c.image;}}
 draw(time=0,amplitude=0,caption='',progress=0,shape=null,rubric=''){
  if(this.robot){this.robot.hideLabels=this.hideLabels;this.robot.draw(time,amplitude,caption,progress,shape,rubric);return;}
  const {canvas,ctx:c,settings:s,character:p}=this,w=canvas.width,h=canvas.height,k=w/720;
  c.fillStyle=s.background||'#162226';c.fillRect(0,0,w,h);
  if(this.image){const ratio=this.image.height/this.image.width,iw=w*.92,ih=iw*ratio,x=(w-iw)/2,y=h*.17;c.save();const zoom=1+Math.sin(time*.6)*.006;c.translate(w/2,y+ih/2);c.scale(zoom,zoom);c.translate(-w/2,-y-ih/2);c.drawImage(this.image,x,y,iw,ih);
   if(p.kind==='illustrated'&&amplitude>.05&&shape!=='closed'){
    // Keep the opening inside the painted smile, with restrained movement.
    const span=iw*(p.mouth_width??.14),mx=x+iw*(p.mouth_x??.51),my=y+ih*(p.mouth_y??.45)+span*.1;
    const mw=span*(shape==='round'?.52:.72),mh=span*(shape==='round'?.22:.15)*Math.min(1,amplitude*2);
    c.fillStyle='#39263b';c.beginPath();c.moveTo(mx-mw/2,my);
    c.quadraticCurveTo(mx,my+mh*.12,mx+mw/2,my);
    c.quadraticCurveTo(mx,my+mh,mx-mw/2,my);c.fill();
   }
   c.restore();}
  if(!this.hideLabels){c.fillStyle=s.accent;c.font=`600 ${22*k}px -apple-system,sans-serif`;c.fillText((s.name||p.name).toUpperCase(),44*k,80*k);c.fillStyle='#d2ddd9';c.font=`400 ${17*k}px -apple-system,sans-serif`;c.fillText(p.kind==='illustrated'?'PERSONAGGIO ILLUSTRATO · ANIMAZIONE 2D':'RITRATTO NARRATO · ANTEPRIMA LOCALE',44*k,115*k);}
  if(caption){c.font=`600 ${30*k}px -apple-system,sans-serif`;const lines=[];let line='';for(const word of caption.split(/\s+/)){const next=line?line+' '+word:word;if(c.measureText(next).width>w-100*k&&line){lines.push(line);line=word;}else line=next;}if(line)lines.push(line);const lh=40*k,bh=lines.length*lh+30*k,by=h*.74;c.fillStyle='#091317ee';c.beginPath();c.roundRect(30*k,by,w-60*k,bh,15*k);c.fill();c.fillStyle='#f4f6f2';c.textAlign='center';lines.forEach((l,i)=>c.fillText(l,w/2,by+36*k+i*lh));c.textAlign='left';}
  c.fillStyle='#ffffff22';c.fillRect(44*k,h-55*k,w-88*k,3*k);c.fillStyle=s.accent;c.fillRect(44*k,h-55*k,(w-88*k)*Math.max(0,Math.min(1,progress)),3*k);
 }
 cover(title,rubric=''){if(this.robot)return this.robot.cover(title,rubric);this.draw(0,0,title,0);return this.canvas.toDataURL('image/png');}
}

import * as THREE from './vendor/three.module.js';

// The character lives in this module only. Replace the group with a rigged GLB
// later while retaining setAppearance(), draw() and the audio timeline contract.
export class Avatar {
  constructor(canvas, settings, width = 720) {
    this.canvas = canvas;
    canvas.width = width; canvas.height = width * 16 / 9;
    this.ctx = canvas.getContext('2d');
    this.renderer = new THREE.WebGLRenderer({antialias: true, alpha: true, preserveDrawingBuffer: true});
    this.renderer.setSize(width, canvas.height);
    this.renderer.setPixelRatio(1);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.3;
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(34, 9 / 16, 0.1, 100);
    this.camera.position.set(0, 1.5, 7.4);
    this.camera.lookAt(0, 1.35, 0);
    this.scene.add(new THREE.HemisphereLight(0xd6f3ff, 0x2a353b, 2.2));
    const key = new THREE.DirectionalLight(0xffffff, 3.2);
    key.position.set(-3, 5, 5); this.scene.add(key);
    const rim = new THREE.DirectionalLight(0xa5ffd1, 2.5);
    rim.position.set(3, 2, -3); this.scene.add(rim);
    this.bodyMaterial = new THREE.MeshStandardMaterial({color: settings.color, roughness: .38, metalness: .18});
    this.dark = new THREE.MeshStandardMaterial({color: 0x132329, roughness: .28, metalness: .25});
    this.accentMaterial = new THREE.MeshStandardMaterial({color: settings.accent, emissive: settings.accent, emissiveIntensity: .22, roughness: .4});
    this.character = new THREE.Group(); this.scene.add(this.character);
    const ellipsoid = (parent, position, scale, material) => {
      const mesh = new THREE.Mesh(new THREE.SphereGeometry(1, 40, 28), material);
      mesh.position.set(...position); mesh.scale.set(...scale); parent.add(mesh); return mesh;
    };
    this.torso = ellipsoid(this.character, [0, .55, 0], [.72, .91, .42], this.bodyMaterial);
    ellipsoid(this.character, [0, 1.26, 0], [.23, .34, .23], this.dark);
    this.head = new THREE.Group(); this.head.position.set(0, 1.99, 0); this.character.add(this.head);
    ellipsoid(this.head, [0, 0, 0], [.67, .72, .53], this.bodyMaterial);
    ellipsoid(this.head, [0, -.015, .40], [.53, .43, .17], this.dark);
    this.eyes = [-1, 1].map(side => ellipsoid(this.head, [side * .22, .09, .55], [.085, .12, .035], this.accentMaterial));
    this.mouth = ellipsoid(this.head, [0, -.20, .562], [.17, .027, .026], this.accentMaterial);
    [-1, 1].forEach(side => {
      ellipsoid(this.head, [side * .66, -.04, 0], [.095, .22, .22], this.dark);
      ellipsoid(this.head, [side * .72, -.04, .03], [.04, .10, .10], this.accentMaterial);
    });
    this.arms = [-1, 1].map(side => {
      const group = new THREE.Group(); group.position.set(side * .7, .96, 0);
      ellipsoid(group, [side * .09, -.4, 0], [.19, .54, .22], this.bodyMaterial);
      ellipsoid(group, [side * .09, -.87, .03], [.19, .23, .2], this.dark);
      this.character.add(group); return group;
    });
    ellipsoid(this.character, [0, .79, .4], [.115, .115, .035], this.accentMaterial);
    this.settings = settings;
  }
  setAppearance(settings) {
    this.settings = {...this.settings, ...settings};
    this.bodyMaterial.color.set(this.settings.color);
    this.accentMaterial.color.set(this.settings.accent);
    this.accentMaterial.emissive.set(this.settings.accent);
  }
  draw(time = 0, amplitude = 0, caption = '', progress = 0, shape = null, rubric = '') {
    const {ctx, canvas, settings} = this;
    const w = canvas.width, h = canvas.height, s = w / 720;
    this.character.position.y = Math.sin(time * 1.5) * .035;
    this.head.rotation.set(Math.sin(time * 1.7) * .025 + amplitude * .03, Math.sin(time * .8) * .10, Math.sin(time * 1.2) * .025);
    const blink = time % 4.8 > 4.61 ? .15 : 1;
    this.eyes.forEach(eye => {eye.scale.y = .12 * blink;});
    const mouth = {closed:[.17,.022], round:[.105,.085], wide:[.215,.055], open:[.155,.12], soft:[.175,.066]}[shape];
    this.mouth.scale.y = mouth ? .022 + (mouth[1] - .022) * Math.min(1, amplitude * 2.5) : .027 + amplitude * .09;
    this.mouth.scale.x = mouth ? mouth[0] : .17 - amplitude * .025;
    this.arms[0].rotation.z = -.09 - amplitude * .08;
    this.arms[1].rotation.z = .09 + Math.sin(time * 1.2) * amplitude * .16;
    this.renderer.render(this.scene, this.camera);
    ctx.fillStyle = settings.background; ctx.fillRect(0, 0, w, h);
    const glow = ctx.createRadialGradient(w*.5, h*.39, w*.04, w*.5, h*.42, w*.72);
    glow.addColorStop(0, '#ffffff16'); glow.addColorStop(1, '#ffffff00');
    ctx.fillStyle = glow; ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = '#ffffff0c'; ctx.lineWidth = s;
    for (let x = 0; x < w; x += 80*s) {ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();}
    for (let y = 0; y < h; y += 80*s) {ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();}
    ctx.strokeStyle = settings.accent + '20'; ctx.lineWidth = 1.5*s;
    ctx.beginPath(); ctx.ellipse(w/2, h*.43, w*.36, w*.43, 0, 0, Math.PI*2); ctx.stroke();
    const shadow = ctx.createRadialGradient(w/2, h*.72, 0, w/2, h*.72, w*.35);
    shadow.addColorStop(0, '#00000055'); shadow.addColorStop(1, '#00000000');
    ctx.save(); ctx.translate(0, h*.54); ctx.scale(1, .25); ctx.fillStyle = shadow; ctx.fillRect(0, 0, w, h); ctx.restore();
    ctx.drawImage(this.renderer.domElement, 0, 0);
    if (!this.hideLabels) {
    ctx.fillStyle = settings.accent; ctx.beginPath(); ctx.arc(63*s, 99*s, 5*s, 0, Math.PI*2); ctx.fill();
    ctx.textAlign = 'left'; ctx.font = `600 ${20*s}px -apple-system, BlinkMacSystemFont, sans-serif`;
    ctx.fillStyle = '#ecf2ee'; ctx.fillText(settings.name.toUpperCase(), 80*s, 106*s);
    ctx.fillStyle = '#b8c3bd'; ctx.font = `400 ${16*s}px -apple-system, sans-serif`;
    ctx.fillText('PERSONAGGIO VIRTUALE', 56*s, 138*s);
    if (rubric) {ctx.fillStyle = settings.accent; ctx.font = `600 ${23*s}px -apple-system, sans-serif`; ctx.fillText(rubric.toUpperCase(), 56*s, 195*s, w - 140*s);}
    }
    if (caption) {
      ctx.font = `600 ${31*s}px -apple-system, BlinkMacSystemFont, sans-serif`;
      const lines = [], words = caption.split(/\s+/); let line = '';
      for (const word of words) {
        const next = line ? line + ' ' + word : word;
        if (ctx.measureText(next).width > w - 180*s && line) {lines.push(line); line = word;} else line = next;
      }
      if (line) lines.push(line);
      const boxHeight = lines.length * 42*s + 36*s, y = h * .71;
      ctx.fillStyle = '#0a1116e8'; ctx.beginPath(); ctx.roundRect(44*s, y, w - 140*s, boxHeight, 20*s); ctx.fill();
      ctx.textAlign = 'center'; ctx.fillStyle = '#f5f7f6';
      lines.forEach((text, i) => ctx.fillText(text, (w-52*s)/2, y + (43 + i*42)*s));
    }
    ctx.fillStyle = '#ffffff22'; ctx.fillRect(56*s, h - 95*s, w - 112*s, 3*s);
    ctx.fillStyle = settings.accent; ctx.fillRect(56*s, h - 95*s, (w - 112*s) * Math.max(0, Math.min(1, progress)), 3*s);
  }
  cover(title, rubric = '') {
    this.draw(1.2, 0, '', 0, 'closed', rubric);
    const {ctx, canvas, settings} = this, w = canvas.width, h = canvas.height, s = w/720;
    const shade = ctx.createLinearGradient(0, h*.55, 0, h*.92);
    shade.addColorStop(0, '#101a2000'); shade.addColorStop(1, settings.background);
    ctx.fillStyle=shade; ctx.fillRect(0,h*.55,w,h*.45);
    ctx.font=`750 ${52*s}px -apple-system, BlinkMacSystemFont, sans-serif`;
    const lines=[];
    for(const paragraph of title.split(/\n/)) {
      let line='';
      for(const word of paragraph.split(/\s+/)) {
        const next=line ? line+' '+word : word;
        if(ctx.measureText(next).width > w-152*s && line) {lines.push(line);line=word;} else line=next;
      }
      if(line) lines.push(line);
    }
    const y=h*.70;
    ctx.fillStyle='#101a20ed';ctx.beginPath();ctx.roundRect(36*s,y-66*s,w-72*s,Math.min(lines.length,4)*60*s+67*s,20*s);ctx.fill();
    ctx.fillStyle=settings.accent;ctx.fillRect(60*s,y-38*s,48*s,4*s);
    ctx.textAlign='left';ctx.fillStyle='#f5f7f6';
    lines.slice(0,4).forEach((text,i)=>ctx.fillText(text,60*s,y+i*60*s,w-120*s));
    return canvas.toDataURL('image/png');
  }
  dispose() {
    const geometries = new Set(), materials = new Set();
    this.scene.traverse(object => {
      if (object.geometry) geometries.add(object.geometry);
      for (const material of (Array.isArray(object.material) ? object.material : [object.material])) {
        if (material) materials.add(material);
      }
    });
    geometries.forEach(geometry => geometry.dispose());
    materials.forEach(material => material.dispose());
    this.renderer.dispose();
    this.renderer.forceContextLoss();
  }
}

export function timelineAt(project, time) {
  const caption = project.captions.find(c => time >= c.start && time < c.end)?.text || '';
  const index = Math.floor(time * project.envelope_fps);
  const amplitude = project.envelope[index] || 0;
  const shape = project.phonemes?.find(p => time >= p.start && time < p.end)?.shape || (project.phonemes?.length ? 'closed' : null);
  return {caption, amplitude, shape, progress: time / project.duration};
}

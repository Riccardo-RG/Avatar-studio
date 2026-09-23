export const languageNames={it:'Italiano',en:'English',es:'Español'};
export function languageField(name,value='it',label='Lingua del contenuto'){
 const wrap=document.createElement('label');wrap.textContent=label;const select=document.createElement('select');select.name=name;for(const [id,title]of Object.entries(languageNames))select.append(new Option(title,id));select.value=value in languageNames?value:'it';wrap.append(select);return wrap;
}
export function setVoices(select,catalog,language,preferred){
 const available=catalog.filter(v=>v.language===language);select.replaceChildren();for(const voice of available)select.append(new Option(voice.id==='piper:paola'?'Paola · neurale locale':voice.id,voice.id));
 if(!available.length){select.append(new Option('Installa una voce per questa lingua sul Mac',''));select.disabled=true;return '';}
 select.disabled=false;const choices={it:['piper:paola','Alice'],en:['Samantha','Daniel','Karen'],es:['Mónica','Paulina']}[language]||[];
 select.value=available.some(v=>v.id===preferred)?preferred:choices.find(id=>available.some(v=>v.id===id))||available[0].id;return select.value;
}
export const usualVoice=(character,language)=>character?.voices_by_language?.[language]||(language==='it'?character?.voice:'');

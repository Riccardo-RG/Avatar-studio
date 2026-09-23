"""Content language and matching local voices; interface language is independent."""
LANGUAGES={'it':'Italiano','en':'English','es':'Español'}
PREFERRED={'it':('piper:paola','Alice'),'en':('Samantha','Daniel','Karen'),'es':('Mónica','Paulina')}

def code(value='it'):
    if value not in LANGUAGES:raise ValueError('Scegli italiano, inglese oppure spagnolo.')
    return value

def apply(config,data=None,catalog=None):
    import media
    data=data or {};lang=code(data.get('language',config.get('language','it')))
    catalog=media.voice_catalog() if catalog is None else catalog
    available=[v['id'] for v in catalog if v['language']==lang]
    if not available:raise ValueError('Nessuna voce locale per '+LANGUAGES[lang]+'. Installa una voce nelle impostazioni di accessibilità del Mac e riavvia lo studio.')
    requested=data.get('voice')
    if requested and requested not in available:raise ValueError('La voce scelta non corrisponde alla lingua del contenuto o non è disponibile sul Mac.')
    character=config.get('character',{})
    usual=character.get('voices_by_language',{}).get(lang) or (character.get('voice',config.get('voice')) if lang=='it' else None)
    voice=requested or (usual if usual in available else next((v for v in PREFERRED[lang] if v in available),available[0]))
    return {**config,'language':lang,'voice':voice}

def instruction(value):
    lang=code(value)
    return {'it':'Scrivi il contenuto in italiano naturale.','en':'Write the content in natural English.','es':'Escribe el contenido en español natural.'}[lang]+' Questa lingua ha priorità sulle eventuali indicazioni di lingua nella scheda del personaggio. Mantieni la sua personalità, senza tradurre nomi propri o inventare fatti.'

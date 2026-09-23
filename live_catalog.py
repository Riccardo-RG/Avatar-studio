"""Editable, bounded replies: chat text is never a prompt or a shell command."""
REPLIES = [
 {'id':'saluto','name':'Un saluto','triggers':['ciao','buongiorno','buonasera','salve'],
  'text':'Ciao e benvenuto! Qui un piccolo robot prova a capire gli umani. Puoi scegliere una rubrica: abitudini, esperimenti oppure domande impossibili.'},
 {'id':'identita','name':'Chi sei?','triggers':['chi sei','come ti chiami','sei un robot','sei vero'],
  'text':'Sono un personaggio virtuale, con una voce sintetica e una grande curiosità per le abitudini umane. Le mie storie sono scene inventate. La vostra chat, invece, è qui davvero.'},
 {'id':'formato','name':'Di cosa parliamo?','triggers':['di cosa parli','cosa fai','quali rubriche','argomenti'],
  'text':'Abbiamo tre rubriche: Manuale degli umani, Un piccolo esperimento e Domanda impossibile. Piccole scene quotidiane, gesti da provare e scelte divertenti. Quale preferisci?'},
 {'id':'frigo','name':'Il frigorifero','triggers':['frigorifero','frigo'],
  'text':'Per ora il frigorifero non ha ricevuto aggiornamenti. Però ho capito una cosa: quando lo riaprite, state controllando anche la vostra speranza nella cena.'},
 {'id':'scelta','name':'Annulla o salva','triggers':['annulla','salva'],
  'text':'Io sceglierei salva, per tenere da parte i momenti belli. Però annulla sarebbe comodissimo quando mando un messaggio nella chat sbagliata. Voi da che parte state?'}
]
DEFAULTS={'title':'NOVA · Piccole cose umane','tagline':'Un robot, tre rubriche e le vostre domande.',
          'autopilot':True,'loop':False,'auto_replies':True,'defer_render':True,'gap_seconds':4,'max_minutes':20,'playlist':[],
          'replies':REPLIES}

# Avatar Studio Live — guida alla regia locale

La nuova sezione **Diretta** è disponibile in [Avatar Studio](http://127.0.0.1:8765/#live). La scena si muove e parla in tempo reale: usa l’avatar 3D e le tracce vocali, senza riprodurre gli MP4 già montati. Lo studio non avvia trasmissioni, non pubblica video e non invia messaggi alle chat.

## La prima prova sul Mac

1. Avvia `Avvia Avatar Studio.command` e apri **Diretta**.
2. Premi **Apri scena e audio**. Nella nuova scheda premi **Attiva questa uscita audio**. Per le prove tieni la scena aperta, preferibilmente in una finestra separata.
3. Torna alla regia e premi **Avvia sessione**. Partono gli episodi selezionati nella scaletta, uno alla volta. Il monitor della regia riceve immagini leggere e rimane silenzioso.
4. Prova un messaggio, ad esempio “Chi sei?” o “Ciao”. Quando una risposta prevista è attiva, viene preparata e pronunciata dopo l’intervento corrente.
5. **Pausa** conserva il punto della voce; **Riprendi** continua. **Salta** passa oltre l’intervento corrente. **Stop** interrompe la voce, svuota la coda e invalida gli interventi ancora in preparazione.

Se la scena perde il collegamento per circa quattro secondi, la regia si mette in pausa. Se la scena non riesce a raggiungere il server, interrompe localmente l’audio. Al ritorno del collegamento occorre premere **Riprendi**. Il riavvio del server lascia sempre la sessione ferma.

Solo una scena alla volta controlla l’audio. Un’altra scheda può mostrare la scena, ma non acquisisce automaticamente l’uscita. Il pulsante **Attiva questa uscita audio** permette il trasferimento esplicito; il trasferimento mette la sessione in pausa.

## Scaletta, durata e risposte

Le impostazioni della sessione permettono di modificare titolo, sottotitolo, pausa fra interventi, durata massima, episodi scelti e ripetizione. La scaletta segue l’ordine del piano editoriale. Senza ripetizione, la sessione finisce al termine degli episodi e delle risposte già in coda. Con ripetizione, continua fino al limite di durata. Il limite iniziale è venti minuti e si può impostare fra uno e centoventi minuti.

Le modifiche alla selezione degli episodi entrano in vigore dal prossimo avvio. I testi degli episodi sono copiati all’avvio della sessione. Titolo della scena, pausa, limite e opzioni automatiche possono essere salvati anche durante la sessione.

La scaletta usa l’audio già disponibile quando voce e ritmo corrispondono alle impostazioni attuali. Altrimenti lo risintetizza. I nuovi interventi usano la voce selezionata nello studio. Il primo uso della voce neurale può richiedere alcuni secondi.

**Un intervento dalla regia** consente di aggiungere fino a seicento caratteri alla coda. La coda accetta dodici interventi. La produzione vocale procede su un solo lavoratore per contenere il carico sul Mac. Durante il primo caricamento di un nuovo testo può esserci una pausa; i file preparati vengono riutilizzati nelle prove successive.

Le cinque risposte iniziali sono modificabili nella sezione **Le risposte automatiche del personaggio**. Ogni risposta ha un testo preciso e parole o frasi che la attivano. Non è una conversazione AI libera: la risposta automatica proviene dai testi previsti. Le domande nuove restano in revisione. Puoi scrivere una risposta o preparare una bozza AI, correggerla e premere **Metti in voce**.

Le bozze usano il motore e il budget delle impostazioni dello studio. La configurazione attuale resta locale con budget esterno zero. Il modello Qwen piccolo può sbagliare italiano e contenuto: nessuna bozza generativa viene messa in voce automaticamente.

## Messaggi e filtro

Il filtro basilare trattiene link, indirizzi e-mail, numeri simili a recapiti, alcune richieste di istruzioni e alcuni temi estranei al formato. Non è una moderazione completa e non sostituisce i controlli della piattaforma. Le risposte automatiche pronunciano soltanto i testi configurati: non ripetono direttamente nomi o messaggi ricevuti.

Un partecipante può attivare al massimo una risposta automatica ogni dieci secondi; la stessa risposta ha un intervallo minimo di trenta secondi per tutta la chat. I duplicati vengono ignorati. Messaggi recenti e stato della regia rimangono in memoria; non viene creata una cronologia permanente delle chat. La scheda mostra gli ultimi sessanta messaggi.

## Scena per OBS

Indirizzo da usare come sorgente Browser:

```text
http://127.0.0.1:8765/live-scene.html?obs=1
```

Imposta la sorgente a **1280 × 720**, con frequenza personalizzata **30 fps**. La sorgente Browser di OBS carica una pagina tramite URL e permette di impostare dimensioni e frequenza; la fluidità effettiva dipende dal carico del Mac. [Guida ufficiale alla sorgente Browser](https://obsproject.com/kb/browser-source).

Nelle proprietà della sorgente seleziona **Control audio via OBS**. È il comando previsto dal componente Browser per indirizzare l’audio a OBS. Le autorizzazioni della pagina possono restare senza accesso ai comandi di OBS: questa scena non li usa. [Opzioni del componente ufficiale OBS Browser](https://github.com/obsproject/obs-browser/blob/master/data/locale/en-US.ini).

Chiudi l’altra uscita audio del browser prima di passare a OBS. Se compare il pulsante di attivazione, usa l’interazione della sorgente per premerlo, poi riprendi dalla regia. Verifica il livello della sorgente nel mixer registrando prima una breve prova. Nel formato OBS, i controlli spariscono dopo l’attivazione; non fanno parte del canvas del programma.

**OBS non è stato trovato nelle cartelle Applicazioni controllate durante questo sviluppo.** Il canvas, la voce e la registrazione sono collaudati in Chrome; il caricamento dentro OBS e una trasmissione effettiva richiedono ancora una prova con OBS installato e il tuo account. Nessuna chiave di streaming viene richiesta o gestita da Avatar Studio.

## Chat Twitch: sola lettura

Il collegamento implementato è per il canale dell’utente che autorizza il token. Serve un **User Access Token** con il solo permesso `user:read:chat`. Inseriscilo nel campo protetto della regia oppure configura `TWITCH_ACCESS_TOKEN` nell’ambiente del server. Non inserire una chiave di streaming.

L’adattatore valida il token, ricava utente e applicazione e sottoscrive `channel.chat.message` tramite EventSub WebSocket. Gestisce riconnessione, ping del protocollo, revoca e convalida periodica. Non chiede permessi di scrittura e non contiene una chiamata per inviare messaggi. [Autenticazione dei chatbot installati](https://dev.twitch.tv/docs/chat/authenticating/) e [trasporto EventSub WebSocket](https://dev.twitch.tv/docs/eventsub/handling-websocket-events/).

Il token va ottenuto per la tua applicazione e il tuo account attraverso il flusso ufficiale. La regia non include ancora una schermata OAuth completa né il rinnovo con refresh token. Quando il token scade occorre ricollegarlo. [Guida ufficiale all’autenticazione Twitch](https://dev.twitch.tv/docs/authentication/).

## Chat YouTube: sola lettura

Servono un token OAuth autorizzato alla lettura della chat e l’ID della chat di una diretta attiva. Inseriscili nella regia, oppure usa `YOUTUBE_ACCESS_TOKEN` e `YOUTUBE_LIVE_CHAT_ID` nell’ambiente del server. L’ID della chat non è l’indirizzo del video. Le API Live richiedono OAuth e credenziali del tuo progetto Google. [Autorizzazione YouTube Live](https://developers.google.com/youtube/v3/live/authentication).

L’adattatore usa `liveChatMessages.list`, conserva il token di pagina e rispetta almeno l’intervallo indicato dalla risposta, con un minimo locale di quindici secondi. Ignora la cronologia ricevuta alla connessione per non rispondere a messaggi vecchi. Ogni collegamento si ferma a cento letture; le chiamate consumano quota API del tuo progetto. Per un impiego continuativo, Google indica il metodo `streamList` come percorso preferibile: questa versione usa il metodo di lettura periodica con un limite esplicito. [Riferimento ufficiale](https://developers.google.com/youtube/v3/live/docs/liveChatMessages/list).

I token forniti dalla pagina sono trasmessi soltanto al server locale e al relativo servizio ufficiale, restano nella memoria del processo del connettore e non vengono scritti nei progetti, nei log o nei file di configurazione. Dopo l’invio il campo della pagina viene svuotato. I connettori non si ricollegano automaticamente al riavvio del server.

**I collegamenti a Twitch e YouTube sono predisposti e collaudati con dati di protocollo simulati. Non sono stati provati con account reali**, perché non sono stati forniti token o una diretta attiva. Si possono scollegare singolarmente dalla regia.

## Registrazione e ripristino

Nella scena aperta in un browser normale, **Registra prova** cattura il canvas insieme alla voce. **Ferma registrazione**, poi **Salva registrazione** produce un WebM nei download del browser. Il test di sviluppo salva anche un MP4 di esempio in `output/live-demo.mp4` dopo la conversione con FFmpeg. La conversione mantiene l’ultimo fotogramma fino alla fine dell’audio quando le due tracce della registrazione browser terminano in momenti diversi.

Per convertire una tua registrazione locale, scegli un nome MP4 che non esiste ancora:

```sh
python3 convert-live-recording.py /percorso/prova.webm /percorso/prova.mp4
```

Il browser può perdere fotogrammi mentre registra sul Mac impegnato in altre applicazioni. Il file MP4 viene normalizzato a 24 fps duplicando i fotogrammi necessari; questo non crea movimento aggiuntivo. La fluidità della trasmissione effettiva va verificata in OBS.

Configurazione della regia e risposte previste sono in `data/live.json`. Le nuove tracce vocali sono in `output/live/`. `data/backup-v2/` conserva codice e impostazioni della seconda edizione. I video, i pacchetti e il piano precedenti rimangono disponibili.

Il collaudo della nuova versione è descritto in `VERIFICA-LIVE.md`. Per eseguire i test di logica:

```sh
python3 -m unittest test_core test_studio test_live -v
```

`test-chat-bridge.cjs` controlla l’estrazione degli eventi e il dominio di riconnessione. `check-live.cjs`, con il server aperto, esegue una sessione locale di prova e ne registra il risultato: non collegarlo a una sessione che stai usando pubblicamente.

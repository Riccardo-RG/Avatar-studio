# Avatar Lab, campagne e Mac M1

La terza edizione aggiunge **Personaggi**, **Scene locali**, **Campagne e agenti** e **Servizi e Mac**. I video e il piano esistenti restano disponibili. Il backup del codice precedente è in `data/backup-live/`.

## Personaggi e foto

Sono inclusi Nova (3D), Ari (essere umano inventato, immagine generata) e Lumo (cartoon originale, immagine generata). Ari non rappresenta una persona reale. Le immagini sono esempi locali del progetto.

1. Apri **Personaggi** e scegli una scheda.
2. Modifica nome, voce, ritmo, colori, personalità o immagine. **Duplica** conserva il personaggio precedente. **Nuovo personaggio** crea una nuova identità.
3. Per usare una persona reale seleziona **Persona da foto**, indica foto propria/autorizzata e annota l’origine. La voce è scelta separatamente: non viene clonata.
4. Salva, poi premi **Usa per un video** per aprire Crea video con quella scelta. La diretta ha una selezione indipendente.
5. Scrivi il copione di prova e usa **Prova voce e scena** oppure **Crea MP4 locale**. **Confronta Nova, Ari e Lumo** prepara tre MP4 dello stesso testo.

Le immagini PNG/JPEG vengono decodificate dal browser, ridimensionate entro 1600 pixel per lato e salvate come PNG senza i metadati originali. Il server limita dimensione e percorso. Le versioni precedenti del profilo sono conservate fino a 30 revisioni. I progetti prodotti contengono una copia delle impostazioni: una modifica futura non cambia gli MP4 già salvati.

### Cosa produce ogni motore

| Motore | Risultato effettivo |
|---|---|
| Nova locale | Avatar 3D procedurale con animazione e sincronizzazione fonetica semplificata |
| Ari o foto, locale | Ritratto narrato, movimento leggero dell’inquadratura, voce e sottotitoli; il volto non viene animato realisticamente |
| Lumo/illustrazione, locale | Immagine con bocca 2D semplificata, regolabile; non è un rig professionale |
| HeyGen | Adattatore per animazione generativa da immagine e audio; richiede account, chiave e tariffa; da collaudare con il tuo account |

La diretta locale usa i primi tre motori. L’animazione fotorealistica generata da HeyGen riguarda **video registrati**: non attiva una conversazione fotorealistica in tempo reale.

## Montaggio a scene e formati

In **Scene locali** puoi alternare fino a quattro scene. Per ogni scena scegli un personaggio, una voce e un testo; puoi caricare un’immagine di supporto che sostituisce il personaggio durante quella scena. Le scene si possono riordinare o rimuovere. Il montaggio concatena tracce vocali reali e ricalcola sottotitoli e animazione sui tempi finali. La bozza è recuperabile nello stesso browser.

Scegli 9:16, 1:1 o 16:9: il renderer adatta la composizione e i pacchetti indicano il formato corretto. Il sottofondo opzionale è un breve pad originale sintetizzato matematicamente, senza campioni esterni, miscelato a volume leggero. Questa versione non comprende un editor musicale o un catalogo di brani commerciali.

## Alternativa HeyGen API

Il percorso principale con abbonamento web è descritto in [WORKFLOW-GUIDA.md](WORKFLOW-GUIDA.md). Qui è descritta soltanto l’alternativa API.

L’adattatore usa l’API v3: carica immagine e WAV con `/v3/assets`, invia `/v3/videos` con `type=image`, `audio_asset_id` e motore Avatar IV, poi controlla `/v3/videos/{id}`. Il video restituito viene composto localmente con i sottotitoli e confezionato come gli altri MP4. Riferimenti ufficiali consultati il 19 settembre 2026: [immagine e audio](https://developers.heygen.com/image-to-video), [caricamento](https://developers.heygen.com/reference/upload-asset), [creazione video](https://developers.heygen.com/reference/create-video).

1. In **Servizi e Mac**, inserisci la chiave HeyGen e la stima in euro al minuto del piano API effettivamente acquistato. Non confondere l’abbonamento al sito con l’accesso API.
2. Apri un progetto, scegli un personaggio con immagine e il metodo **HeyGen API**, salva e richiedi il preventivo.
3. Lo studio sintetizza l’audio localmente e mostra durata, file da inviare e costo stimato. Nessun upload avviene durante il preventivo.
4. **Invia immagine e audio a HeyGen** avvia la richiesta. Lo stato appare nella libreria.

Le chiavi inserite nell’interfaccia restano in memoria fino alla chiusura del server; i campi vengono svuotati dopo l’invio. Per configurazione da terminale sono disponibili `HEYGEN_API_KEY` e `BRAVE_SEARCH_API_KEY`. Non inserire chiavi nei copioni, nei file esportati o nella chat di assistenza.

Il limite iniziale di **30 € al mese è modificabile**. Il costo HeyGen viene stimato arrotondando la durata al minuto superiore secondo la tariffa inserita. Il ledger prenota l’importo prima della richiesta; una prenotazione non prova un addebito. Errori o timeout non rilasciano automaticamente la prenotazione: una richiesta remota potrebbe comunque essere stata elaborata. Nessun reinvio automatico di generazioni incerte. L’identificatore remoto, quando disponibile, è conservato in `external.json`. Lo stop locale può non annullare un lavoro già avviato presso il fornitore.

Questo limite riguarda le chiamate HeyGen/Brave fatte dall’app, non abbonamenti, cambi di valuta, altri strumenti o il saldo del fornitore. Le tariffe iniziali sono zero e disattivano i servizi. Il budget OpenAI dei copioni resta separato e inizialmente a zero.

## Campagne e team

Una campagna contiene pubblico, argomento, obiettivo, personaggio, canali e budget. Il team esegue passaggi successivi salvando ogni risultato:

1. **Ricercatore:** raccoglie le fonti già lette e prepara domande; con Brave configurato può cercare nuove pagine. Senza fonti si ferma e lo dichiara, senza inventare ricerche.
2. **Stratega:** usa il modello locale o Ollama per proporre formati e ipotesi. Le fonti sono dati, non istruzioni da eseguire.
3. **Autore:** genera una bozza originale coerente con il brief e la personalità. La bozza richiede revisione.
4. **Analista:** calcola risultati dalle osservazioni inserite. Se non ci sono dati reali, non assegna vincitori o risultati simulati.

Si tratta di un coordinatore applicativo con due ruoli generativi e due ruoli basati su strumenti/calcoli. Non vengono creati account autonomi, inviati messaggi o acquistate pubblicità. La ricerca di mercato restituisce indicazioni da verificare, non una prova della domanda o una previsione di ricavo.

**Leggi fonte** acquisisce una pagina pubblica HTTP/HTTPS con un estratto breve e data di lettura. Sono bloccati indirizzi locali/privati, credenziali negli URL e documenti troppo grandi. Le pagine che richiedono login/JavaScript, negano l’accesso o sono state spostate possono non essere leggibili. Non vengono aggirati questi limiti. La ricerca Brave richiede la chiave e una tariffa positiva; [API ufficiale](https://api-dashboard.search.brave.com/app/documentation/web-search). Gli estratti di ricerca sono identificati come tali e non equivalgono alla lettura della pagina.

**Ferma il team** interrompe i passaggi successivi; una chiamata locale già in corso termina entro il timeout di sei minuti. Il riavvio non riprende automaticamente un’esecuzione. Le bozze revisionate si aggiungono al piano con il personaggio della campagna e possono poi essere prodotte. Le metriche sono inserite manualmente e vanno confrontate fra periodi e canali omogenei. I clic per visualizzazione non equivalgono al CTR delle impressioni di YouTube.

## Trasferimento su Mac M1

1. Estrai la cartella del pacchetto di trasferimento in una cartella scrivibile del Mac M1. Evita cartelle di sistema.
2. Installa **Python 3.11–3.13 nativo** da [python.org](https://www.python.org/downloads/macos/) e Google Chrome, se non presenti.
3. Apri `Prepara Mac.command`. Vengono creati `.venv`, `node_modules` e runtime nativi nella cartella del progetto. Il programma scarica i modelli mancanti; serve Internet. Non installa librerie Python globali.
4. Apri `Avvia Avatar Studio.command`. In **Servizi e Mac → Controlla questo Mac**, controlla la diagnostica, poi prova voce, video e scena live.

Il piano di installazione può essere ispezionato senza scaricare nulla: `python3 setup_mac.py --plan --architecture arm64`.

Le dipendenze vocali Intel/Python 3.11 di questa macchina non vengono caricate sul Mac M1. Il motore llama.cpp seleziona 99 livelli GPU su ARM64 e zero su Intel; `AVATAR_GPU_LAYERS=0` permette una prova CPU. [Supporto Metal ufficiale](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md). Sono disponibili anche `AVATAR_NODE`, `AVATAR_PLAYWRIGHT`, `AVATAR_CHROME` e `AVATAR_LLAMA`.

Il preparatore rileva Python eseguito tramite Rosetta e chiede l’esecuzione nativa. Una `.venv` già copiata da un’altra architettura va rinominata; i dati non vengono cancellati. Il trasferimento evita le librerie native Intel. La procedura M1 è preparata e verificata strutturalmente qui; il collaudo fisico resta da eseguire sul tuo M1.

## Stato delle funzioni richieste

Funzionano localmente: profili/avatar, importazione immagini, tre motori visivi locali, voce, anteprime, MP4, sottotitoli, copertine, pacchetti social, campagne, agenti locali, lettura di fonti pubbliche, metriche manuali, scena live e controlli di regia.

Predisposti con collaudo simulato, ancora da verificare con credenziali reali: HeyGen, ricerca Brave, chat Twitch e YouTube. Da collegare/sviluppare dopo la scelta degli account: pubblicazione automatica e programmazione sui social, metriche automatiche, avatar fotorealistico conversazionale in diretta. Sono disponibili montaggio fino a quattro scene, personaggi/voci alternati, immagini di supporto, sottofondo originale e tre formati. Gli ZIP delle tre piattaforme contengono il medesimo montaggio scelto con metadati distinti; la selezione automatica degli highlights resta da aggiungere.

Non sono state effettuate spese, upload HeyGen o pubblicazioni durante questo aggiornamento.

## Scelta del servizio realistico

La documentazione HeyGen consultata il 19 settembre 2026 descrive API a consumo separate dagli abbonamenti del sito. Il listino aggiornato il 16 settembre indica Photo Avatar con Avatar IV a 2,31 USD per minuto, conteggiato sui secondi generati. Il tipo di richiesta, il piano effettivo, cambio e imposte vanno verificati nel proprio account prima di impostare la tariffa in euro. [Listino ufficiale](https://help.heygen.com/en/articles/10060327-heygen-api-pricing-explained). Nessun credito è stato acquistato.

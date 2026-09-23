# Registrazioni, risultati e interventi in conversazione

Queste funzioni completano il percorso personale: registri sul Mac, ricavi clip, prepari i post e confronti i contatori disponibili. Gli account e le prove reali si collegano alla fine seguendo `SERVIZI-ESTERNI.md` e `TESTING-FINALE.md`.

## Da una registrazione a una clip

1. Apri **Clip e registrazioni**. Importa MP4, MOV, MKV o WebM, fino a 2 GB, oppure scegli un video già completato nello studio. L'importazione crea una copia locale in `data/recordings/`; non modifica il file originale. Sono ammesse registrazioni da un secondo a otto ore.
2. Imposta inizio e fine, oppure usa **Qui inizia / Qui finisce** mentre rivedi il filmato. Ogni clip dura da 1 a 180 secondi.
3. Scegli verticale 9:16, quadrato o orizzontale 16:9. Puoi mantenere tutta l'immagine oppure riempire il formato tagliandone i bordi. Il cursore sposta il ritaglio orizzontalmente; controlla volti e testo nell'anteprima.
4. I video dello studio conservano i loro sottotitoli. Per una registrazione importata puoi aggiungere un file SRT con i tempi della registrazione intera. Non viene eseguita una trascrizione audio. Se il filmato ha già scritte impresse, seleziona **La registrazione ha già sottotitoli visibili** per evitare un secondo livello. Questa scelta vale per il taglio in preparazione: ricontrollala quando cambi sorgente.
5. Per le registrazioni importate, indica facoltativamente i personaggi presenti. È un riferimento per lo storico, non una sostituzione delle persone nel filmato. Per i video dello studio l'associazione deriva dal progetto e dalle scene comprese nel taglio.
6. **Riproduci il taglio** controlla intervallo, inquadratura e sottotitoli disponibili. **Proponi intervalli** suggerisce tagli temporali, basati sui sottotitoli o distribuiti nel filmato: non sceglie con l'AI i momenti migliori.
7. **Crea clip sul Mac** accoda il rendering. Nella libreria trovi MP4 H.264/AAC, copertina, SRT con tempi riallineati e pacchetti social. Il rendering rispetta l'opzione che rimanda i nuovi lavori alla fine della regia locale.

L'anteprima dipende dai codec supportati dal browser. Alcuni MOV/MKV leggibili da FFmpeg non sono riproducibili direttamente in Chrome: usa un MP4 H.264/AAC o esporta un breve taglio e controllalo nella libreria. L'anteprima dei sottotitoli è indicativa: controlla sempre l'MP4 finale, specialmente dopo un ritaglio. Le scritte già impresse possono essere tagliate insieme all'immagine.

Il pacchetto di trasferimento M1 comprende anche le copie delle registrazioni importate: filmati grandi aumentano lo spazio e il tempo richiesti per l'esportazione. I rendering interrotti da un riavvio vengono segnalati; non ripartono da soli.

## Preparare un file per Instagram

Dopo aver collegato il tuo bucket Cloudflare R2, prepara e salva un post Instagram. Nella scheda scegli **Prepara file sul mio storage**: controlla dimensione, bucket e URL pubblico, poi conferma **Carica sul mio storage pubblico**. Limite dell'uploader: 150 MB.

Il comando carica il file e verifica che l'URL pubblico restituisca esattamente quel video. Poi inserisce l'URL nel post e richiede una nuova revisione/approvazione. **Non pubblica il Reel**. La pubblicazione resta nel flusso separato della coda.

Se la rete si interrompe, prepara nuovamente il piano: lo studio controlla lo stesso oggetto identificato dall'impronta del video, evitando una seconda copia quando il primo upload è riuscito. Se il dominio non serve ancora il file, correggi la configurazione R2 e ripeti la verifica. I file rimangono sul tuo bucket fino a quando li rimuovi tu; mantienili disponibili durante l'elaborazione del Reel. Puoi continuare a caricare manualmente su un altro storage HTTPS e incollare il suo URL.

## Leggere e confrontare i risultati

In **Risultati** compaiono solo i post confermati come pubblicati dai servizi. Un invio ancora da completare nella posta TikTok non equivale a una pubblicazione. I riferimenti aggiunti manualmente allo storico del personaggio non acquisiscono automaticamente contatori.

- Filtra per piattaforma e personaggio; seleziona fino a tre post per confrontarli. Su finestre strette la tabella scorre lateralmente.
- **Leggi i risultati adesso** consulta gli account collegati. L'aggiornamento periodico è facoltativo, da 15 minuti a 24 ore, mentre il server e il Mac sono accesi. Dopo ogni riavvio torna spento.
- **Esporta CSV** scarica l'ultima lettura di ogni post, con la differenza rispetto alla precedente. Un valore mancante resta vuoto, non diventa zero. Una differenza negativa può dipendere da rettifiche del servizio.
- Le fotografie successive dei contatori non vengono sommate. Per confrontare contenuti considera piattaforma, data di pubblicazione e tempi delle letture. Sono disponibili solo i contatori implementati dai connettori, non ricavi, retention o CTR.

Letture fallite, per esempio per token scaduti, sono visibili sulla scheda e attendono l'intervallo impostato prima di un nuovo tentativo periodico. La frequenza usa le quote API dei tuoi account; non è un servizio attivo quando il Mac è spento.

## Un messaggio della chat all'avatar realistico

Questo percorso richiede una sessione Tavus configurata e avviata dal personaggio scelto in **Diretta**. Non avvia automaticamente una sessione a pagamento né una trasmissione Twitch/YouTube.

1. **Apri conversazione** collega la stanza privata. Microfono e videocamera partono spenti. Una sola finestra dello studio può controllare gli invii; chiudi la stanza nella prima finestra prima di usarne un'altra. Se una finestra si blocca, il controllo scade dopo 45 secondi senza aggiornamenti.
2. Da un messaggio in regia scegli **Prepara per Tavus**. Il riferimento appare nel riquadro di revisione; non viene ancora inviato nulla. Puoi anche usare un testo manuale.
3. Scegli **Pronuncia esattamente il testo rivisto** e scrivi la risposta, oppure **Genera una risposta alla domanda rivista** e correggi la domanda. Nel secondo caso il servizio genera la risposta: il contenuto pronunciato non è approvato parola per parola.
4. Rileggi e premi **Invia testo rivisto**. Il testo raggiunge il servizio esterno della stanza. **Interrompi voce Tavus** invia una richiesta d'interruzione separata.
5. Il registro distingue invio al canale ed esito incerto. Non costituisce conferma di ricezione o pronuncia. Lo stesso messaggio della chat non viene inoltrato due volte nella sessione, neppure dopo un esito incerto; non ci sono reinvii automatici. Il registro persistente contiene ID, tempi, modalità e impronte, non il testo integrale della chat.
6. Per finire usa **Termina sul servizio**. Chiudere la finestra locale della stanza non equivale a confermare la chiusura remota. Dopo un riavvio dello studio verifica la sessione esistente sul fornitore.

La chat non viene inoltrata in massa e lo studio non invia risposte scritte a Twitch/YouTube. Per trasmettere il video della stanza controlla cattura e audio in OBS. La qualità, la latenza e gli effetti effettivi dei comandi Tavus/Daily vanno ancora collaudati sul tuo account; lo sviluppo ha usato un SDK simulato e test del protocollo documentato.

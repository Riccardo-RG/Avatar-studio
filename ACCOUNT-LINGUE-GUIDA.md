# Più account e tre lingue

## Cambiare account rapidamente

In **Collegamenti**, le schede YouTube, Instagram e TikTok hanno il menu **Account salvato**. Il profilo già presente si chiama inizialmente **Principale**. Puoi rinominarlo, per esempio «Lumo Italia», e aggiungerne altri con **Aggiungi account** (fino a 20 per piattaforma).

Ogni profilo mantiene nome, identificativo del canale e configurazione propri. Le credenziali sono separate: un account appena aggiunto non eredita token, client secret o identità del precedente. Inserisci i suoi collegamenti e usa **Verifica identità**. Per YouTube anche il login Google resta associato al profilo da cui lo hai aperto, se nel frattempo cambi selezione.

Lo switch sceglie il profilo da configurare e quello proposto per un **nuovo** post. In **Pubblicazione → Prepara un post** trovi sempre **Account destinatario**: scegli esplicitamente dove deve andare quel video. Ogni post salvato conserva la destinazione, indipendentemente dagli switch successivi. Puoi preparare lo stesso video per account diversi; una seconda voce per lo stesso video e lo stesso account viene bloccata. Cambiare destinatario di un post richiede di salvarlo e rivedere l'approvazione.

Gli invii, i controlli remoti e le metriche usano il profilo del post. Se è scollegato o l'identità restituita non corrisponde, il lavoro si ferma: non passa all'account selezionato nel menu. Durante un'operazione le credenziali del profilo coinvolto non sono modificabili; gli altri profili restano selezionabili. In **Risultati** puoi filtrare anche per account.

**Scollega** disattiva solo il profilo mostrato e ne rimuove le credenziali dalla sessione. La scheda e i riferimenti ai post rimangono. Nomi e configurazione sono persistenti; token e password inseriti nell'interfaccia restano in memoria e vanno reinseriti dopo il riavvio del server. Le precedenti variabili d'ambiente social si riferiscono soltanto al profilo **Principale**, non vengono condivise con i profili aggiunti.

Questo switch riguarda YouTube, Instagram e TikTok. L'account che trasmette tramite OBS si sceglie ancora in OBS; i collegamenti della chat hanno i propri campi nella regia. Non cambia automaticamente neppure l'account di HeyGen, Tavus o dello storage.

## Italiano, inglese e spagnolo

L'interfaccia resta in italiano. Le lingue dei contenuti disponibili sono **Italiano, English, Español**.

In **Crea video**, **Lingua del contenuto** filtra le voci compatibili e guida le nuove bozze AI. La scelta è ricordata insieme al copione, senza cambiare la lingua della diretta. La voce italiana iniziale è Paola/Piper; inglese e spagnolo usano le voci di macOS effettivamente disponibili, con Samantha e Mónica come prime scelte quando presenti. Se manca una voce, installala nelle impostazioni di accessibilità/voce del Mac e riavvia lo studio. Non viene sostituita automaticamente con una voce di un'altra lingua.

Ogni personaggio può avere una voce abituale italiana, inglese e spagnola nella sua scheda. Sono voci diverse, non una clonazione multilingua della stessa identità vocale. Per una continuità timbrica più stretta occorrerà valutare un motore vocale apposito in futuro.

**Cambiare lingua non traduce il testo già scritto.** Puoi scriverlo tu oppure usare **Prepara versione nella lingua scelta** (da 2 a 1800 caratteri in ingresso): lo studio mostra originale e bozza modificabile. Solo **Usa questa versione** sostituisce il copione. Controlla sempre completezza, significato, numeri, nomi e tono. Il modello locale piccolo può sbagliare; una bozza non è una traduzione certificata. Il titolo e l'argomento restano da adattare separatamente. Una copia del testo precedente è conservata nel browser sotto `avatar-before-translation`.

Per conservare entrambe le versioni come contenuti separati, salva prima l'originale nel piano o come video, poi salva la versione tradotta come un nuovo episodio/video con un titolo riconoscibile. Gli MP4 già creati non vengono sovrascritti. I sottotitoli seguono il testo pronunciato: non sono tracce tradotte aggiuntive.

## Lingua nei diversi percorsi

| Percorso | Dove si sceglie | Comportamento |
|---|---|---|
| Video singolo | Crea video | Voce compatibile, nuove bozze e metadati nella lingua scelta |
| Episodio | Modifica episodio | Lingua salvata nella revisione e usata nel rendering |
| Montaggio | Lingua di ciascuna scena | Puoi affiancare scene in lingue diverse con le relative voci |
| Prova personaggio / HeyGen | Lingua accanto al copione di prova | Stessa traccia locale scelta per anteprima e invio HeyGen; qualità esterna da verificare |
| Campagna | Lingua nel brief | Lingua del copione dell'autore, conservata quando lo porti nel piano |
| Regia locale | Lingua degli interventi della regia | Lingua degli interventi manuali e delle nuove bozze di risposta; gli episodi già prodotti conservano la propria lingua |
| Tavus | Lingua in Diretta, poi nuovo piano Tavus | Indicazione inviata nel contesto; serve verificare supporto e qualità del Face/PAL configurato |

La strategia della campagna e i resoconti dell'interfaccia restano in italiano. La ricerca Brave attuale usa ancora il filtro italiano: la lingua del copione non equivale automaticamente a una ricerca di mercato nel paese estero.

Per cambiare lingua alla regia locale, fermala e svuota gli interventi preparati. Il cambio disattiva le vecchie risposte automatiche: riscrivile nella lingua corretta e rileggile prima di riattivarle. Non traduce la chat né converte i vecchi episodi in tempo reale. Per Tavus rifai il piano se cambi personaggio o lingua prima dell'avvio; la qualità effettiva va provata con il servizio collegato.

## Cosa aspettarsi dai movimenti

Il robot locale ha animazione 3D procedurale; il cartoon ha movimenti semplificati e bocca animata. Una foto o un ritratto locale rimane un'immagine narrata, non diventa un attore umano completo. HeyGen è il percorso opzionale per un video del volto animato; Tavus è quello per una conversazione fotorealistica.

La regia permette interventi testuali, risposte selezionate, pausa, salto e stop. Nella stanza Tavus puoi inviare un testo/domanda rivisti e chiedere un'interruzione. Gesti, pose, espressioni facciali comandate e movimento corporeo umano completo non sono implementati.

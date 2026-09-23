# Video, personaggi e pubblicazione personale

Guida dettagliata alle schede, alle voci e ai diversi flussi: **[PERSONAGGI-GUIDA.md](PERSONAGGI-GUIDA.md)**.

## Scegli il personaggio ogni volta

Il primo riquadro di **Crea video** contiene schede visive e il selettore «Personaggio di questo video». **Diretta** ha «Personaggio della prossima diretta», indipendente dal primo. Nel piano puoi assegnare un avatar a ciascun episodio, nel montaggio a ciascuna scena. Un personaggio salvato può essere modificato in seguito; i video già prodotti conservano il proprio aspetto e le impostazioni originali.

Durante una live la scelta della sessione resta fissata anche se modifichi la scheda o scegli un altro avatar per un video. Per cambiare personaggio in regia premi Stop, seleziona quello nuovo e avvia una nuova sessione.

La selezione di un ritratto in **Crea video** produce il percorso locale. Per animare realisticamente il volto usa la prova HeyGen dalla scheda Personaggi. La conversazione Tavus usa invece il Face ID e PAL ID associati alla singola scheda del personaggio, con chiave e tariffa nei Collegamenti.

## Schede e storico essenziale

In **Personaggi → Attività e riferimenti** trovi titolo, data, tipo, stato e link di video, campagne, sessioni locali e post. Il registro riusa gli identificatori dei contenuti senza duplicare copioni o media. Un montaggio con più personaggi compare nelle rispettive schede. Le versioni dell'aspetto sono conservate separatamente nella scheda.

Lo stato distingue *Creato sul Mac*, *Approvato, non inviato*, *Elaborazione sul servizio* e *Confermato sul servizio*. Una sessione della regia viene descritta come locale: non certifica che OBS stesse trasmettendo. Per contenuti pubblicati manualmente o una registrazione Twitch, **Aggiungi un link esterno** conserva titolo e collegamento dichiarati da te. La rimozione del riferimento non cancella il post remoto. Le vecchie dirette antecedenti all'introduzione del registro non possono essere ricostruite; i vecchi video Nova già salvati sono riconosciuti.

## Lavorare durante una live

Puoi scrivere copioni, scegliere un altro personaggio, preparare il piano e revisionare post mentre la regia continua. La voce della live e quella del video usano configurazioni separate. Per proteggere la fluidità sul Mac M1, **Rimanda i nuovi rendering alla fine della regia live** è attivo inizialmente: i lavori restano in coda durante esecuzione e pausa e ripartono a fine regia o dopo Stop.

Disattivando questa opzione consenti il rendering simultaneo, da collaudare sul tuo Mac. Il controllo non interrompe un rendering già iniziato, non rileva streaming avviati indipendentemente da OBS e non copre la stanza Tavus separata. Anche la generazione AI locale di copioni può impegnare la CPU: durante il primo collaudo osserva le prestazioni. Se vuoi attendere anche la chiusura effettiva della trasmissione, termina OBS prima di fermare la regia. Tieni fuori dal mixer OBS l'audio delle anteprime.

## Prepara e approva

1. Completa un video e apri **Pubblicazione → Prepara un post**.
2. Scegli il video e il canale. Lo studio prepara una copia MP4 con audio AAC 48 kHz, lasciando intatto l'originale.
3. Controlla il file, titolo, descrizione, destinazione/visibilità, data e fuso IANA (ad esempio `Europe/Rome`). L'orario viene interpretato nel fuso scritto; gli orari ambigui o inesistenti al cambio dell'ora sono respinti.
4. Per Instagram inserisci anche l'URL HTTPS pubblico del **File preparato**. Il testo deve rispettare il limite di 2200 caratteri, senza tagli silenziosi.
5. Salva **da revisionare**, poi **Approva questo video**. Per più post seleziona le caselle e **Approva gruppo settimanale**: devono appartenere alla stessa settimana ISO e allo stesso fuso. Puoi filtrare per settimana.
6. **Simula** verifica riferimenti, file e approvazione senza fare richieste alle piattaforme. Ti mostra cosa manca per l'invio reale.

L'approvazione riguarda quella versione di file, testo, canale verificato, destinazione e orario. Una modifica la annulla. I post preparati prima del collegamento dell'account devono essere salvati e approvati nuovamente dopo aver verificato il canale. Le date nel vecchio **Piano contenuti** restano solo organizzative: programma l'invio nella sezione Pubblicazione.

## Attivazione reale, soltanto dopo il collaudo

**Abilita invii reali** abilita l'invio dei post approvati arrivati all'orario previsto. Mac e server devono restare accesi, senza sospensione. Il controllo avviene ogni 15 secondi; upload ed elaborazione possono aggiungere ritardo. Non è un servizio cloud sempre acceso. Dopo ogni riavvio l'invio è disattivato.

Se l'orario è passato da oltre un'ora il post richiede riprogrammazione e nuova approvazione. Se il Mac si spegne durante un upload, il post diventa **Da verificare**; nessun nuovo upload viene avviato automaticamente per quell'esito incerto. Usa **Controlla stato remoto** e il pannello del servizio. Lo stop locale non ritira un contenuto già ricevuto dal provider e non cancella post pubblicati.

**YouTube:** il caricamento può restare privato per limiti del progetto API; lo stato riporta la visibilità effettiva. **TikTok:** il video arriva nella posta e richiede completamento nell'app. **Instagram:** la pubblicazione è pubblica e richiede lo storage HTTPS. Le istruzioni complete sono in `SERVIZI-ESTERNI.md`.

**Aggiorna metriche** legge contatori disponibili dal servizio per un post confermato. Un dato mancante appare come «non disponibile». Le letture sono fotografie successive, non incrementi da sommare; non vengono inventati visualizzazioni, ricavi o CTR. I dati delle campagne inseriti a mano restano separati. **Esporta registro** salva i riferimenti della coda in JSON.

Sono presenti due post del video pilota usati per la simulazione di sviluppo (YouTube privato e bozza TikTok): non sono stati inviati e non hanno account associati. Puoi annullarli oppure riprogrammarli dopo aver collegato i tuoi account.

Per ricavare clip dalle registrazioni, caricare il file sul tuo R2, confrontare i contatori o preparare interventi selezionati per Tavus: **CLIP-RISULTATI-GUIDA.md**.

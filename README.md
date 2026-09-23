# Avatar Studio

Avatar Studio è un'app personale per macOS che organizza la creazione di video brevi con personaggi virtuali. Unisce copioni, voce, sottotitoli, progetti salvati, generazione o importazione del video, montaggio verticale e preparazione dei file per i social. È un'app locale per un singolo utente, non un servizio SaaS.

## Cosa puoi fare

- Gestire personaggi e progetti, conservando copioni, materiali e revisioni.
- Preparare copioni da un'idea o da un piano editoriale e produrre voce italiana con sintesi locale.
- Creare scene locali con avatar 3D, illustrazioni o ritratti narrati, poi aggiungere sottotitoli e montaggio.
- Usare il flusso **Prepara → genera → importa → rifinisci** per creare un video con HeyGen dal sito e completarlo nello Studio.
- Esportare MP4 verticali, copertine, sottotitoli e pacchetti di materiali per YouTube, TikTok e Instagram.
- Organizzare campagne e contenuti; usare gli strumenti locali per la regia e le dirette.

**Limite importante:** la modalità locale crea personaggi stilizzati o ritratti narrati. Non anima realisticamente un volto umano. Per quel flusso, il progetto supporta la generazione tramite il sito HeyGen; è disponibile anche un'integrazione API facoltativa, separata dall'abbonamento web.

## Requisiti

- macOS 13.5 o successivo;
- Python 3.11, 3.12 o 3.13 installato per macOS;
- Google Chrome.

La preparazione installa le dipendenze nella cartella del progetto e scarica i modelli vocali e linguistici necessari. Node e il motore locale dei copioni vengono installati per l'architettura del Mac. Occorre una connessione Internet durante la preparazione.

## Avvio

Clona il repository, apri `Prepara Mac.command` e attendi che termini. Poi apri `Avvia Avatar Studio.command`; l'app si apre nel browser e resta in esecuzione sul Mac finché la finestra del terminale è attiva. Per fermarla, premi Ctrl+C in quella finestra.

Per avviarla manualmente dopo la preparazione:

```sh
.venv/bin/python app.py
```

Il server ascolta su `127.0.0.1:8765`, quindi l'interfaccia è raggiungibile dal Mac locale. Non esporre questa porta pubblicamente.

## Flusso per un video realistico

1. In **Progetti**, scegli un personaggio con un'immagine e prepara copione, voce e sottotitoli.
2. Scarica i materiali preparati e apri HeyGen dal progetto.
3. Genera e scarica il video dal sito HeyGen.
4. Importa l'MP4 nello stesso progetto, controlla taglio, formato e sottotitoli, poi esporta il risultato.

HeyGen richiede un account e il suo abbonamento o credito API. L'integrazione API è facoltativa; l'abbonamento al sito non comprende automaticamente l'accesso API.

## Servizi e dati

La sintesi vocale e il motore locale dei copioni non richiedono un account cloud. OpenAI, HeyGen API, ricerca web e collegamenti ai social sono integrazioni facoltative che richiedono credenziali proprie. L'uso di un servizio esterno può inviare al fornitore i dati necessari a quella funzione; controlla i contenuti prima di inviarli.

Configurazioni, token, progetti, registrazioni e risultati locali sono esclusi da Git. Non inserire chiavi API nel codice o nei file da pubblicare: configura i segreti solo nell'ambiente locale. I file generati e i modelli scaricati restano nella cartella del progetto.

## Sviluppo

Il backend usa la libreria HTTP standard di Python e l'interfaccia usa JavaScript e CSS. Le dipendenze Python sono elencate in `requirements-mac.txt`; il runtime Node è configurato in `package.json` e preparato localmente.

Per eseguire la suite di test:

```sh
.venv/bin/python -m unittest discover -p 'test_*.py' -v
```

## Licenza

Questo repository al momento non dichiara una licenza complessiva. Le dipendenze e i modelli scaricati possono avere condizioni proprie: consulta i rispettivi avvisi prima di redistribuire l'app o i materiali.

# LMU Setup Manager

🇬🇧 [Read this README in English](readme.md)

<p align="center">
  <a href="https://github.com/Seroper-real/lmu-setup-manager/releases/latest/download/lmu-setup-manager_Windows.zip">
    <img src="https://img.shields.io/github/v/release/Seroper-real/lmu-setup-manager?label=DOWNLOAD&style=for-the-badge&color=brightgreen" alt="Download">
  </a>
  <a href="https://ko-fi.com/seroper">
    <img src="https://img.shields.io/badge/Ko--fi-Offrimi%20un%20caff%C3%A8-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white" alt="Sostienimi su Ko-fi">
  </a>
</p>

Un **setup manager** desktop per *Le Mans Ultimate*. Installa i setup nel gioco, tiene il catalogo di quelli che hai, li sostituisce quando esce una versione più recente e ti permette di ripulirli — tutto da un'unica finestra.

I setup entrano in due modi:

- **Automaticamente da TrackTitan** — tutto il tuo abbonamento in una sola esecuzione, invece di prenderli uno a uno dal sito.
- **Manualmente** — trascini un qualsiasi `.zip` che già possiedi (archivi GO Setups, il setup di un amico, uno tuo) e indichi all'app a quale auto e pista appartiene.

In entrambi i casi vengono gestiti allo stesso modo: elencati, aggiornati ed eliminabili dall'app. Nessun file da creare o modificare a mano.

<details>
<summary><b>Prima di iniziare — cos'è e cosa non è questo tool</b></summary>

- **Non aggira paywall o limitazioni**. L'integrazione con TrackTitan richiede un account TrackTitan con **abbonamento attivo**: senza, quella parte semplicemente non funziona, ma puoi comunque usare l'app per gestire i setup che aggiungi a mano.
- Le informazioni vengono recuperate tramite le **stesse API usate dall'app web ufficiale di TrackTitan**.
- Questo progetto **non è affiliato, supportato né approvato da TrackTitan**, ed è pensato **solo per uso personale**.

</details>

---

## Prerequisiti

- Un PC Windows
- Le Mans Ultimate installato
- Un account TrackTitan con abbonamento ai setup LMU

---

## Passo 1 — Installazione

1. [Scarica](https://github.com/Seroper-real/lmu-setup-manager/releases/latest/download/lmu-setup-manager_Windows.zip) il file `.zip`
2. Estrailo dove preferisci
3. Avvia l'`.exe` contenuto dentro

Non c'è nessun installer e non viene scritto nulla nella cartella del programma: puoi spostarla o eliminarla in seguito senza perdere setup o impostazioni.

> L'app parte in italiano. Puoi cambiare lingua da **Impostazioni → Lingua**.

---

## Passo 2 — Scegli la modalità

Apri **Impostazioni → Modalità di funzionamento** e scegline una. La scelta ha effetto immediato, senza riavviare.

| Modalità | Nell'app | Cosa fa | Ti serve |
| :--- | :--- | :--- | :--- |
| `full` *(predefinita)* | **Diretta** | Scarica da TrackTitan e installa direttamente in LMU su questo PC | Login TrackTitan + cartella LMU |
| `master` | **Solo Upload** | Scarica da TrackTitan e pubblica sul tuo Dropbox (nessuna installazione locale) | Login TrackTitan + app Dropbox |
| `slave` | **Solo installazione** | Prende i setup dal tuo Dropbox e li installa in LMU su questo PC | App Dropbox (basta la sola lettura) + cartella LMU |

**Su un solo PC usa Diretta.** Le altre due hanno senso solo se usi Le Mans Ultimate su **più di un tuo PC** e vuoi spostare i setup tra di essi tramite il tuo Dropbox — vedi [Modalità nel dettaglio](#modalità-nel-dettaglio).

---

## Passo 3 — Prima esecuzione, in base alla modalità

### Diretta — il caso normale

1. **Impostazioni → Token TrackTitan → Ottieni automaticamente.** Si apre una finestra di login TrackTitan dentro l'app. Accedi come faresti normalmente: la finestra si chiude da sola e i tre token vengono compilati e salvati.
2. **Impostazioni → Cartella setup Le Mans Ultimate.** Controlla il percorso. Se il gioco non è nella posizione Steam predefinita, premi **Sfoglia…** e punta a:
   `…\Le Mans Ultimate\UserData\player\Settings`
3. Vai nella tab **Download** e premi **Avvia download**.

> Alla primissima esecuzione l'app ti avvisa che i setup HYMO installati *prima* di usare questo tool non sono visibili da qui. È consigliato eliminare quei vecchi setup HYMO da LMU, così l'app può gestire tutto in modo pulito da quel momento in poi.

### Solo Upload — il PC che ha il tuo abbonamento

1. Crea una volta sola un'app Dropbox — vedi [Creare la tua app Dropbox](#creare-la-tua-app-dropbox) (circa 3 minuti, niente codice).
2. **Impostazioni → Token TrackTitan → Ottieni automaticamente**, come per la modalità Diretta.
3. **Impostazioni → Credenziali Dropbox.** Incolla `DROPBOX_APP_KEY` e `DROPBOX_APP_SECRET`, poi clicca **Ottieni automaticamente** accanto al refresh token e scegli **Token Lettura/Scrittura**. Approva l'app nella pagina Dropbox che si apre, incolla il codice breve nell'app e viene salvato.
4. Controlla il campo **cartella Dropbox condivisa** (default `/lmu-setups`): dovrà essere identico sull'altro PC.
5. Tab **Download** → **Avvia download**.

Qui non serve il percorso LMU: non viene installato nulla in locale.

### Solo installazione — i tuoi altri PC

**Su questa macchina non servono abbonamento né token TrackTitan.**

1. **Impostazioni → Credenziali Dropbox.** Incolla gli stessi `DROPBOX_APP_KEY` e `DROPBOX_APP_SECRET` dell'altro PC, clicca **Ottieni automaticamente** e scegli **Token Sola Lettura**: quella credenziale non potrà mai scrivere né eliminare nulla nel tuo Dropbox.
2. Imposta la **cartella Dropbox condivisa** con lo stesso valore usato in Solo Upload.
3. **Impostazioni → Cartella setup Le Mans Ultimate** — controlla il percorso, **Sfoglia…** se serve.
4. Tab **Download** → **Avvia download**.

---

## L'app, tab per tab

**Download** — Mostra la modalità attiva, il pulsante **Avvia download** / **Interrompi** e un flusso di attività in tempo reale con tutto ciò che viene installato o caricato. Vengono scaricati solo i setup nuovi e aggiornati, quindi una seconda esecuzione subito dopo la prima non ha quasi nulla da fare.

**Setup installati** — Tutto ciò che l'app ha installato, raggruppato per pista e auto, con il logo della classe dell'auto e un link **Hotlap** che apre il giro su YouTube di TrackTitan per quel setup. Puoi cercare per pista o auto ed eliminare un singolo setup, un'intera auto, tutti quelli di una pista o tutti in blocco.

**Carica Setup** — Trascina un `.zip` (o clicca per sceglierlo), seleziona il tipo (**GO Setups** o **HYMO**), la pista e l'auto, e premi **Carica setup**. In Diretta/Solo installazione viene installato direttamente in LMU; in Solo Upload viene pubblicato sul tuo Dropbox per gli altri PC. Pista e auto vengono indovinate dal nome del file quando possibile. È il modo più semplice per aggiungere archivi [GO Setups](#setup-go).

**Associazioni manuali** — I nomi di piste e auto che hai associato a mano (vedi [Quando un setup non viene riconosciuto](#quando-un-setup-non-viene-riconosciuto)). Ricercabili, paginati, con eliminazione singola o totale.

**Impostazioni** — Lingua, modalità di funzionamento, cartella LMU, token TrackTitan, credenziali Dropbox, più un blocco **Impostazioni avanzate** richiuso (ogni campo ha un tooltip ⓘ che lo spiega) e una [Zona pericolosa](#zona-pericolosa).

> Nelle Impostazioni non c'è un pulsante Salva: l'app chiede se salvare quando esci dalla tab o chiudi la finestra.

---

## Cose che ti capiteranno

### Quando un setup non viene riconosciuto

Un setup viene installato solo quando l'app riesce a capire **a quale pista e a quale auto** appartiene. Se una delle due non trova corrispondenza, quel setup viene saltato: non finisce mai in una cartella con il nome sbagliato.

Al termine di un'esecuzione l'app raccoglie tutto ciò che ha saltato e apre la finestra **Setup non riconosciuti**, che elenca una sola volta ogni pista o auto sconosciuta. Per ognuna scegli la pista/auto corretta dal menu a tendina, poi premi **Salva e Risegui** per elaborarli subito, oppure **Salva e Chiudi** per farlo alla prossima esecuzione. Le tue scelte vengono salvate in locale e riutilizzate per sempre: le ritrovi nella tab **Associazioni manuali**.

Se nemmeno nel menu compare la pista o l'auto giusta, usa **Copia elenco** e apri una issue: va aggiornata la mappatura integrata, cosa che facciamo noi senza che tu debba aggiornare l'app.

### Token che scadono

I token TrackTitan scadono regolarmente. Quando succede l'app te lo dice con un popup **Autenticazione scaduta**: basta premere di nuovo **Ottieni automaticamente** nelle Impostazioni e rilanciare.

Le credenziali Dropbox invece non scadono: il refresh token si genera una volta sola e si rinnova da solo.

### Setup aggiornati

Quando TrackTitan pubblica una nuova versione di un setup che hai già, l'app se ne accorge e lo sostituisce — in LMU, e su Dropbox in Solo Upload. Non devi tenere traccia delle versioni tu.

---

## Sostieni il mio lavoro

Se trovi utile questo progetto e vuoi supportarne lo sviluppo, offrimi un caffè! Ogni piccolo contributo aiuta a mantenere attivo il progetto. Grazie di cuore!

[![](https://storage.ko-fi.com/cdn/kofi3.png?v=3)](https://ko-fi.com/seroper)

---
---

# Avanzato / Riferimento

Tutto quello che segue è materiale di approfondimento: non ti serve nulla di questo per usare l'app.

## Modalità nel dettaglio

Per impostazione predefinita il tool gira in modalità **Diretta** (`full`) e fa tutto su una sola macchina: scarica da TrackTitan, installa in LMU e tiene traccia di ciò che è installato in un database locale.

Se usi Le Mans Ultimate su **più di un tuo PC**, le altre due modalità ti permettono di spostare i setup tramite il **tuo Dropbox**, invece di estrarre i token e interrogare TrackTitan da ogni macchina:

- **Solo Upload** (`master`) — gira sul PC con il tuo abbonamento TrackTitan. Scarica i setup, li reimpacchetta e li copia sul tuo Dropbox in `<cartella Dropbox>/<Auto>/<Pista>/HYMO-<pista>_<auto>_<id>_<timestamp>.zip`. Non tiene alcun database locale: capisce cosa pubblicare confrontando TrackTitan con ciò che c'è già nella cartella. Quando un setup viene aggiornato, il nuovo zip viene caricato per primo e solo dopo il vecchio viene eliminato.
- **Solo installazione** (`slave`) — gira sui tuoi altri PC. Elenca quella stessa cartella, salta ciò che il database locale ha già alla stessa versione o più recente, scarica il resto e lo installa. Ricostruisce i dettagli di ogni setup da un `.metadata.json` incluso nello zip, quindi una macchina in Solo installazione finisce con esattamente gli stessi record di una in Diretta.

Solo il lato TrackTitan è soggetto a rate limit (circa un setup ogni paio di secondi, quindi una prima esecuzione completa richiede sui 20–30 minuti). I caricamenti su Dropbox avvengono in parallelo in background e non si sommano a quel tempo.

## Creare la tua app Dropbox

Serve per Solo Upload e Solo installazione. Circa tre minuti, una volta sola.

### 1. Crea l'app

Vai nella [Dropbox App Console](https://www.dropbox.com/developers/apps) e premi **Create app**:

- Scegli **Scoped access**
- Scegli **App folder** — l'app vedrà solo `/Apps/<NomeApp>/` e non l'intero Dropbox
- Assegna un nome univoco

La tab **Settings** della tua nuova app Dropbox mostra ora **App key** e **App secret**: sono `DROPBOX_APP_KEY` e `DROPBOX_APP_SECRET`.

> Con l'accesso **App folder**, la cartella Dropbox che imposti nell'app è relativa alla cartella dell'app: `/lmu-setups` si trova fisicamente in `/Apps/<NomeApp>/lmu-setups`. Continua a scrivere `/lmu-setups`.

### 2. Abilita i permessi

Apri la tab **Permissions** e spunta:

| Scope | Serve a |
| :--- | :--- |
| `files.metadata.read` | Solo Upload + Solo installazione (elenco della cartella) |
| `files.content.read` | Solo installazione (download dei setup) |
| `files.content.write` | Solo Upload (upload e sostituzione dei setup) |

Premi **Submit** in fondo alla pagina, altrimenti non viene salvato nulla.

### 3. Ottieni il refresh token

Usa **Ottieni automaticamente** nelle Impostazioni dell'app, come descritto nel [Passo 3](#solo-upload--il-pc-che-ha-il-tuo-abbonamento). Scegli **Lettura/Scrittura** sul PC in Solo Upload e **Sola Lettura** su quelli in Solo installazione: un refresh token di sola lettura non può mai essere ampliato in seguito, quindi quella macchina è fisicamente incapace di danneggiare la tua cartella.

<details>
<summary>Generare il refresh token a mano</summary>

Apri questo URL nel browser, sostituendo `<SOSTITUISCI_CON_APP_KEY>` con la tua:

```
https://www.dropbox.com/oauth2/authorize?client_id=<SOSTITUISCI_CON_APP_KEY>&token_access_type=offline&response_type=code
```

Per una credenziale di sola lettura, aggiungi in fondo a quell'URL `&scope=files.metadata.read%20files.content.read`.

Autorizza l'app. Dropbox mostra un breve **codice di accesso**: non è il refresh token, è monouso e scade in pochi minuti. Scambialo senza lasciare la pagina:

1. Resta sulla pagina Dropbox che mostra il codice.
2. Apri gli strumenti per sviluppatori (`F12`) e vai sulla scheda **Console**.
3. Incolla lo snippet qui sotto, sostituendo i tre segnaposto, e premi Invio.

```js
(async () => {
  const APP_KEY    = 'INCOLLA_APP_KEY';
  const APP_SECRET = 'INCOLLA_APP_SECRET';
  const CODE       = 'INCOLLA_IL_CODICE_DI_QUESTA_PAGINA';

  const res = await fetch('https://api.dropbox.com/oauth2/token', {
    method: 'POST',
    headers: { Authorization: 'Basic ' + btoa(`${APP_KEY}:${APP_SECRET}`) },
    body: new URLSearchParams({ code: CODE, grant_type: 'authorization_code' }),
  });
  const data = await res.json();
  if (!data.refresh_token) return console.error('Dropbox ha restituito un errore:', data);
  console.log(`DROPBOX_APP_KEY=${APP_KEY}\nDROPBOX_APP_SECRET=${APP_SECRET}\nDROPBOX_REFRESH_TOKEN=${data.refresh_token}`);
})();
```

La console stampa i tre valori, pronti da incollare nella tab Impostazioni dell'app.

**Risoluzione problemi**

- La prima volta che incolli nella console di Chrome/Edge, il browser rifiuta e ti chiede di scrivere `allow pasting` e premere Invio. Fallo una volta sola, poi incolla di nuovo.
- Il codice della pagina Dropbox sostituisce `console.log` con un proprio wrapper e allega una voce `Error` richiudibile (serve a catturare lo stack per il loro logging). È innocua: ignorala.
- Se vedi `invalid_grant`, il codice è già stato usato oppure è scaduto: ricarica l'URL di autorizzazione per ottenerne uno nuovo.
- **Non** incollare l'`access_token` presente nella risposta: gli access token iniziano con `sl.` e smettono di funzionare dopo poche ore. Ti serve `refresh_token`.

Preferisci il terminale?

```bash
curl -u APP_KEY:APP_SECRET \
  -d code=IL_TUO_CODICE \
  -d grant_type=authorization_code \
  https://api.dropbox.com/oauth2/token
```

</details>

## Estrarre i token TrackTitan a mano

Serve solo se **Ottieni automaticamente** non funziona.

1. Effettua il login su https://app.tracktitan.io nel tuo browser.
2. Apri gli strumenti per sviluppatori (`F12`, oppure `Cmd + Option + I` su macOS) e vai nella tab **Console**.
3. Incolla questa singola riga e premi Invio:

```
(()=>{let a,b,u;document.cookie.split(';').forEach(c=>{const[k,v]=c.trim().split(/=(.*)/s);/\.accessToken$/.test(k)&&(a=v);/\.idToken$/.test(k)&&(b=v);/\.LastAuthUser$/.test(k)&&(u=v);});console.log(`ACCESS_TOKEN_LIST=${a}\nACCESS_TOKEN_DOWNLOAD=${b}\nUSER_ID=${u}`);})();
```

4. Verrà stampato qualcosa di simile:

```
ACCESS_TOKEN_LIST=eyJraWQiOiIzNDd2Q3lpWllCRWdJSkw3...
ACCESS_TOKEN_DOWNLOAD=eyJraWQiOiI3MEoyS3lmVHZQXC9ocUJ0...
USER_ID=123cdvf-34fd...
```

5. Incolla ogni valore nel campo corrispondente in **Impostazioni → Token TrackTitan**.

> Token e credenziali Dropbox sono dati sensibili: **non condividerli mai**.

## Setup GO

I setup gestiti da questo tool in modo completo provengono da TrackTitan e sono pubblicati con il marchio **HYMO**. **GO Setups** è un provider di terze parti separato, solo *compatibile* con questo tool: l'app non comunica mai con i sistemi di GO e non pubblica nulla per suo conto. Gli archivi li fornisci tu.

**Per aggiungerne uno:** usa la tab **Carica Setup** — trascina lo zip, scegli il tipo **GO Setups**, seleziona pista e auto, conferma. In Diretta/Solo installazione viene installato in locale; in Solo Upload viene pubblicato su Dropbox perché gli altri tuoi PC lo prendano. Un secondo caricamento per la stessa auto e pista sostituisce l'archivio precedente.

Dettagli:

- Gli archivi GO vivono nella stessa struttura Dropbox di quelli HYMO, in `<cartella Dropbox>/<Auto>/<Pista>/`, con il prefisso `GO-` nel nome. Funziona anche trascinare uno zip in quella cartella a mano, purché il nome inizi per `GO`.
- I file di telemetria MoTeC di un archivio GO (`.ld`/`.ldx`) vengono installati insieme ai suoi setup `.svm`, di proposito: GO li distribuisce insieme, quindi vengono copiati e ripuliti insieme.
- GO non fornisce alcun segnale affidabile di "questo è cambiato", quindi ogni esecuzione in Solo installazione riscarica ogni archivio GO che trova. È previsto. Se poi venga effettivamente reinstallato dipende solo dal contenuto: l'app calcola un'impronta del download e salta la reinstallazione se non è cambiato nulla. Questo significa anche che un archivio può essere rinominato sul posto senza perdere lo storico di installazione: solo spostarlo in una cartella `<Auto>/<Pista>` diversa ne avvia uno nuovo e scollegato.
- I setup GO compaiono nella tab **Setup installati** come tutti gli altri, con un piccolo badge **GO** accanto.

## Mappatura piste e auto

I nomi grezzi di piste e auto di TrackTitan vengono confrontati con una mappatura inclusa nell'app (`config/mapping.json`) tramite pattern matching case-insensitive. Quel file viene aggiornato automaticamente da GitHub all'avvio, così piste e auto nuove possono essere aggiunte senza che tu debba aggiornare l'app — puoi disattivarlo da **Impostazioni avanzate → Tracciati remoti**.

Tutto ciò che la mappatura integrata non riconosce passa alle tue **Associazioni manuali**, aggiunte tramite la finestra di fine esecuzione descritta [qui sopra](#quando-un-setup-non-viene-riconosciuto). Se nessuno dei due livelli trova corrispondenza, il setup viene saltato invece di essere installato con un nome inventato.

La mappatura delle auto contiene anche la classe di ogni vettura: è ciò che disegna i loghi GT3/GTE/Hypercar/P2/P3 nella tab **Setup installati**.

## Dove vengono salvati i dati

| Cosa | Dove |
| :--- | :--- |
| Impostazioni, credenziali, associazioni manuali (`settings.db`) | `%LOCALAPPDATA%\lmu-setup-manager` |
| Registro dei setup installati (`data.db`) | `%LOCALAPPDATA%\lmu-setup-manager` |
| File di log | `logs\` accanto all'`.exe` (uno al giorno, i vecchi vengono eliminati da soli) |
| Download temporanei | `downloads\` accanto all'`.exe` |

Poiché impostazioni e database dei setup installati vivono nella cartella dati utente, **sopravvivono a reinstallazioni e aggiornamenti di versione**: puoi eliminare o spostare senza problemi la cartella del programma estratto.

Eliminare il database dei setup installati significa **ricominciare tutti i download da zero**: l'app non sa più cosa aveva già installato.

## Impostazioni avanzate

In **Impostazioni → Impostazioni avanzate** (richiuse di default). Ogni campo ha un tooltip ⓘ nell'app; i valori predefiniti vanno bene e raramente c'è bisogno di toccarli.

| Gruppo | Cosa contiene |
| :--- | :--- |
| Logging | Livello minimo dei messaggi scritti nel file di log |
| Rete | Dimensione pagina TrackTitan, timeout delle richieste e ritardo minimo/massimo tra una richiesta e l'altra |
| Download e setup | Quali estensioni contano come file di setup, se pulire la cartella di download, se sovrascrivere i setup esistenti e se eliminare la versione precedente |
| Tracciati remoti | Aggiornamento automatico della mappatura piste/auto: on/off, URL di origine, timeout |
| Dropbox (avanzate) | Timeout API e quanti caricamenti avvengono in parallelo |

## Zona pericolosa

In fondo alle **Impostazioni**, protetta da una conferma con conto alla rovescia:

- **Pulisci setup Dropbox** — elimina tutti i setup presenti nella tua cartella Dropbox condivisa. Non tocca nulla in locale.
- **Ripristina impostazioni di fabbrica** — elimina tutti i setup installati dall'app più tutti i dati dell'applicazione (impostazioni, credenziali, database). Il tuo Dropbox resta intatto.

Entrambe le operazioni sono irreversibili.

## Sandbox (per chi sviluppa)

Serve a sviluppare e testare l'applicativo stesso. Ogni flag sostituisce un sistema esterno con una controparte locale, così puoi eseguire il programma su una macchina senza abbonamento TrackTitan e senza Le Mans Ultimate installato. Sono opzioni da riga di comando — non viene scritto nulla nelle tue impostazioni/credenziali reali — e si combinano liberamente.

```
python src/main.py --sandbox                     # mocka tutto
python src/main.py --mock-tracktitan --mock-lmu  # mocka questi due, Dropbox reale
python src/main.py --sandbox --mode master       # sandbox, forzando una modalità
```

| Flag | Effetto |
| :--- | :--- |
| `--sandbox` | Scorciatoia per tutti e tre i `--mock-*` qui sotto |
| `--mock-tracktitan` | Legge i setup dal catalogo di esempio in `sandbox/tracktitan/` invece di chiamare l'API TrackTitan. Nessun token richiesto |
| `--mock-lmu` | Installa in `sandbox/lmu/Settings/` invece che nella cartella del gioco. Usa un database separato, quindi i record della tua installazione reale restano intatti |
| `--mock-dropbox` | Usa la cartella locale `sandbox/dropbox/` invece di Dropbox. Nessuna credenziale richiesta |
| `--mock-base-path PATH` | Dove risiede la sandbox. Default: `sandbox` |
| `--mode {full,master,slave}` | Forza la modalità salvata solo per questa esecuzione |

Ogni flag rimuove anche il relativo controllo sulle credenziali: `--sandbox --mode master` e poi `--sandbox --mode slave` eseguono un giro completo pubblica → installa senza alcuna credenziale configurata. Ogni esecuzione in sandbox scrive un avviso `SANDBOX ACTIVE` nei log, così non puoi confonderla con una reale. Funzionano anche le variabili d'ambiente equivalenti `MOCK_TRACKTITAN` / `MOCK_LMU` / `MOCK_DROPBOX` / `MODE`, e `.vscode/launch.json` include un profilo di debug per ogni combinazione.

`sandbox/dropbox/` include già un setup GO di esempio per ogni pista (placeholder sintetici `.svm`/`.ld`/`.ldx`, non dati reali), quindi `--mock-lmu --mock-dropbox --mode slave` li installa tutti subito. Per provare a mano il percorso di aggiornamento, esegui due volte di fila: la seconda esecuzione dovrebbe registrare "unchanged since last install" senza toccare nulla; modifica il contenuto di un membro e riesegui per vedere il percorso di aggiornamento versione reinstallare e ripulire i file vecchi.

## Eseguire e compilare dai sorgenti

```bash
pip install -r requirements.txt
python src/main.py
```

`build.bat` produce l'`.exe` standalone per Windows in `dist/` tramite PyInstaller. Le release vengono compilate automaticamente da GitHub Actions quando viene pushato un tag `v*`.

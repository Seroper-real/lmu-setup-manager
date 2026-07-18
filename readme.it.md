# LMU Setup Manager for Le Mans Ultimate

🇬🇧 [Read this README in English](readme.md)

<p align="center">
  <a href="https://github.com/Seroper-real/lmu-setup-manager/releases/latest/download/lmu-setup-manager_Windows.zip">
    <img src="https://img.shields.io/github/v/release/Seroper-real/lmu-setup-manager?label=DOWNLOAD&style=for-the-badge&color=brightgreen" alt="Download">
  </a>
</p>

## Introduzione

Questo progetto è nato **esclusivamente per comodità personale**.

Lo scopo è automatizzare il download e l'installazione dei setup di **TrackTitan** per *Le Mans Ultimate*, evitando di doverli scaricare manualmente uno a uno dal sito. Tutto si gestisce da un'app grafica — nessun file da creare o modificare a mano.

⚠️ **Avviso importante**

- Questo tool **non aggira paywall o limitazioni**
- È **obbligatorio** avere un account TrackTitan con **abbonamento attivo**
- Le informazioni vengono recuperate tramite le **stesse API utilizzate dall'app web ufficiale**
- I token di autenticazione devono essere **ottenuti manualmente dal browser**

Questo progetto:

- **Non è affiliato a TrackTitan**
- **Non è supportato né approvato da TrackTitan**
- È pensato **solo per uso personale**

Senza un abbonamento attivo, il programma **non funzionerà**.

---

## Prerequisiti

- Account TrackTitan valido con abbonamento ai setup LMU
- PC Windows
- Le Mans Ultimate installato

---

## Avvio rapido

### 1. Scarica ed estrai

1. [Scarica](https://github.com/Seroper-real/lmu-setup-manager/releases/latest/download/lmu-setup-manager_Windows.zip) il file `.zip`
2. Estrai il contenuto in una cartella a tua scelta
3. Avvia l'`.exe` contenuto dentro

### 2. Scegli la tua modalità

Apri la tab **Impostazioni** (o il selettore modalità nella tab Download) e scegli:

| Modalità             | Cosa fa                                                                        | Ti serve                                          |
| :-------------------- | :-------------------------------------------------------------------------------- | :--------------------------------------------------- |
| `full` (predefinita) | Scarica da TrackTitan e installa direttamente in LMU su questo PC                 | Token TrackTitan + percorso LMU                     |
| `master`             | Scarica da TrackTitan e carica sul tuo Dropbox (nessuna installazione locale)     | Token TrackTitan + credenziali Dropbox               |
| `slave`              | Scarica i setup dal tuo Dropbox e installa in LMU su questo PC                    | Credenziali Dropbox (sola lettura) + percorso LMU     |

La scelta ha effetto immediato, senza bisogno di riavviare. `master`/`slave` sono utili solo se usi LMU su più di un tuo PC — vedi [Modalità nel dettaglio](#modalità-nel-dettaglio) più sotto. Su un solo PC, resta su `full`.

### 3. Inserisci le tue credenziali

Sempre nella tab **Impostazioni**, incolla i tuoi token nei campi corrispondenti:

- **Token TrackTitan** (`full`/`master`) — vedi la [guida dedicata](#token-tracktitan) più sotto
- **Credenziali Dropbox** (`master`/`slave`) — vedi la [guida dedicata](#credenziali-dropbox) più sotto

Ogni campo nelle Impostazioni ha anche un link "Guarda qui" che ti porta direttamente alla guida corrispondente.

### 4. Imposta il percorso LMU

Necessario per `full`/`slave`. Controlla il campo del percorso LMU nelle Impostazioni — usa il pulsante **Sfoglia** se è sbagliato o il gioco non è installato nel percorso predefinito.

### 5. Avvia il programma

Premi **Start** nella tab Download 🚀

---

<a id="token-tracktitan"></a>

## 🔑 Come ottenere i token TrackTitan

Necessari per le modalità `full` e `master`.

1. Effettua il login su https://app.tracktitan.io
2. Apri la console del browser
   - Windows/Linux: `F12` oppure `Ctrl + Shift + I`
   - Mac: `Cmd + Option + I`
3. Vai nella tab **Console**, incolla questa riga e premi Invio:

```
(()=>{let a,b,u;document.cookie.split(';').forEach(c=>{const[k,v]=c.trim().split(/=(.*)/s);/\.accessToken$/.test(k)&&(a=v);/\.idToken$/.test(k)&&(b=v);/\.LastAuthUser$/.test(k)&&(u=v);});console.log(`ACCESS_TOKEN_LIST=${a}\nACCESS_TOKEN_DOWNLOAD=${b}\nUSER_ID=${u}`);})();
```

4. La console stamperà qualcosa di simile:

```
ACCESS_TOKEN_LIST=eyJraWQiOiIzNDd2Q3lpWllCRWdJSkw3...
ACCESS_TOKEN_DOWNLOAD=eyJraWQiOiI3MEoyS3lmVHZQXC9ocUJ0...
USER_ID=123cdvf-34fd...
```

5. Incolla ogni valore nel campo TrackTitan corrispondente nella tab Impostazioni dell'app e premi **Salva**.

> ⚠️ I token **scadono**. Se vedi un popup con errore `401 Unauthorized`, ripeti questi 5 passaggi e risalva.

---

<a id="credenziali-dropbox"></a>

## 📦 Crea e ottieni le credenziali Dropbox

Necessarie per le modalità `master` e `slave`. Richiede circa cinque minuti e va fatto una volta sola (il refresh token non scade).

### 1. Crea l'app

Vai nella [Dropbox App Console](https://www.dropbox.com/developers/apps) e premi **Create app**:

- Scegli **Scoped access**
- Scegli **App folder** — l'app vedrà solo `/Apps/<NomeApp>/` e non l'intero Dropbox
- Assegna un nome univoco all'app

La tab **Settings** della tua nuova app Dropbox mostra ora **App key** e **App secret**: sono `DROPBOX_APP_KEY` e `DROPBOX_APP_SECRET`.

> Con l'accesso **App folder**, il percorso della cartella Dropbox che imposti nelle Impostazioni dell'app è relativo alla cartella dell'app: `/lmu-setups` si trova fisicamente in `/Apps/<NomeApp>/lmu-setups`. Continua a scrivere `/lmu-setups`.

### 2. Abilita i permessi

Apri la tab **Permissions** e spunta:

| Scope                  | Serve a                                    |
| :---------------------- | :------------------------------------------- |
| `files.metadata.read` | MASTER + SLAVE (elenco della cartella)       |
| `files.content.read`  | SLAVE (download dei setup)                   |
| `files.content.write` | MASTER (upload e sostituzione dei setup)     |

Premi **Submit** in fondo alla pagina, altrimenti le modifiche non vengono salvate.

### 3. Genera il refresh token

**Consigliato: dall'app**

1. Incolla `DROPBOX_APP_KEY` e `DROPBOX_APP_SECRET` nei campi corrispondenti nella tab Impostazioni dell'app.
2. Clicca **Ottieni automaticamente** accanto al campo Refresh Token — si apre la pagina di autorizzazione Dropbox nel browser.
3. Autorizza l'app. Dropbox mostra un breve **codice di accesso**.
4. Torna nell'app, incolla il codice nella finestra appena comparsa e clicca **Conferma**.

L'app scambia il codice per te e compila automaticamente `DROPBOX_REFRESH_TOKEN` — clicca **Salva** e hai finito, non serve il metodo manuale qui sotto.

<details>
<summary>Alternativa: generalo manualmente</summary>

Apri questo URL nel browser, sostituendo `<SOSTITUISCI_CON_APP_KEY>` con la tua:

```
https://www.dropbox.com/oauth2/authorize?client_id=<SOSTITUISCI_CON_APP_KEY>&token_access_type=offline&response_type=code
```

Autorizza l'app. Dropbox mostra allora un breve **codice**: non è il refresh token, è monouso e scade in pochi minuti. Scambialo senza lasciare la pagina:

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

La console stampa i tre valori, pronti da incollare nella tab Impostazioni dell'app:

```
DROPBOX_APP_KEY=abc123...
DROPBOX_APP_SECRET=def456...
DROPBOX_REFRESH_TOKEN=8vTq...
```

<details>
<summary>Risoluzione problemi con la console e alternativa via curl</summary>

- La prima volta che incolli nella console di Chrome/Edge, il browser rifiuta e ti chiede di scrivere `allow pasting` e premere Invio. Fallo una volta sola, poi incolla di nuovo.
- Il codice della pagina Dropbox sostituisce `console.log` con un proprio wrapper, che allega una voce `Error` richiudibile (serve a catturare lo stack per il loro logging). Compare subito sotto l'output ed è innocua: ignorala.
- Se la console mostra `invalid_grant`, il codice è già stato usato oppure è scaduto: ricarica l'URL di autorizzazione per ottenerne uno nuovo ed esegui di nuovo lo snippet.

Preferisci il terminale? Usa curl:

```bash
curl -u APP_KEY:APP_SECRET \
  -d code=IL_TUO_CODICE \
  -d grant_type=authorization_code \
  https://api.dropbox.com/oauth2/token
```

Nel JSON di risposta, il campo `refresh_token` è il tuo `DROPBOX_REFRESH_TOKEN`. **Non** incollare l'`access_token` presente nella stessa risposta: gli access token iniziano con `sl.` e smettono di funzionare dopo poche ore.

</details>

</details>

### 4. Token di sola lettura per il PC SLAVE (opzionale)

Se stai configurando un secondo PC in modalità `slave`, non riusare lì il token del MASTER: generane uno secondo, di sola lettura. Il pulsante **Ottieni automaticamente** nell'app richiede sempre l'accesso completo, quindi questo va fatto a mano: ripeti i passaggi sopra aggiungendo il parametro `scope` ridotto nell'URL di autorizzazione:

```
https://www.dropbox.com/oauth2/authorize?client_id=<SOSTITUISCI_CON_APP_KEY>&token_access_type=offline&response_type=code&scope=files.metadata.read%20files.content.read
```

Il refresh token che ne risulta porta con sé solo quei due scope, e in fase di rinnovo gli scope non possono mai essere ampliati: questa credenziale non potrà mai scrivere nella tua cartella. Usa il token completo su MASTER e questo di sola lettura su SLAVE.

### 5. Inserisci le credenziali nell'app

Incolla i tre valori nei campi Dropbox corrispondenti nella tab Impostazioni dell'app:

```
DROPBOX_APP_KEY=...
DROPBOX_APP_SECRET=...
DROPBOX_REFRESH_TOKEN=...
```

Infine imposta la cartella Dropbox nelle Impostazioni (default `/lmu-setups`) — deve essere la stessa su MASTER e SLAVE. Premi **Salva**.

> Mantieni private queste credenziali, esattamente come i token TrackTitan.

---

## Note Importanti

- I token **scadono**: in caso di errore `401 Unauthorized` (te lo segnala un popup), ripeti la procedura e risalvale nelle Impostazioni
- **Non condividere mai** le tue credenziali
- I download avvengono con un piccolo delay per simulare un comportamento umano (un download ogni ~2 secondi, tempo totale 20–30 minuti)
- I setup già installati, e tutte le tue impostazioni/credenziali, sono salvati nella cartella dati per-utente del sistema operativo (es. `%LOCALAPPDATA%\lmu-setup-manager` su Windows) — sopravvivono a reinstallazioni e aggiornamenti di versione, quindi puoi eliminare o spostare la cartella del programma estratto senza problemi
- Eliminare il database dei setup installati significa **ricominciare i download da zero**
- Per interrompere un'esecuzione usa il pulsante **Stop** nella tab Download (oppure chiudi semplicemente la finestra dell'app)

---

## ☕ Sostieni il mio lavoro

Se trovi utile questo progetto e vuoi supportarne lo sviluppo, offrimi un caffè!

Ogni piccolo contributo aiuta a mantenere attivo il progetto. Grazie di cuore!

[![](https://storage.ko-fi.com/cdn/kofi3.png?v=3)](https://ko-fi.com/seroper)

---

## Avanzato / Riferimento

Tutto quello che segue è materiale di approfondimento — non ti serve per far partire il programma. La tab Impostazioni dell'app ha un tooltip ⓘ su ogni campo avanzato, quindi qui ci limitiamo ai concetti invece di ripetere la documentazione campo per campo.

### Modalità nel dettaglio

Per impostazione predefinita il tool gira in modalità **FULL** e fa tutto su una sola macchina: scarica da TrackTitan e installa in LMU.

Se usi Le Mans Ultimate su **più di un tuo PC**, puoi spostare i tuoi setup tramite il **tuo Dropbox** invece di estrarre i token e interrogare TrackTitan su ogni macchina. Due modalità aggiuntive lo rendono possibile:

- **MASTER** — da eseguire sul PC che ha i tuoi token TrackTitan. Scarica i tuoi setup e li copia in una cartella del **tuo** Dropbox (uno zip per setup, con nome `{track}_{car}_{id}_{timestamp}.zip`). Quando un setup viene aggiornato, la vecchia copia viene sostituita automaticamente.
- **SLAVE** — da eseguire sull'altro tuo PC. Installa i setup direttamente dalla tua cartella Dropbox in LMU. **Qui non servono i token TrackTitan** — basta l'accesso in lettura alla tua cartella Dropbox.

### Mapping piste

I nomi dei tracciati TrackTitan vengono associati automaticamente alle cartelle LMU tramite una mappatura inclusa nell'app e tenuta aggiornata da sola — non serve alcun intervento da parte tua.

Se una pista non corrisponde a nulla, i setup vengono copiati in una cartella `<NOME_PISTA> - HYMO`, così le piste non mappate sono facili da individuare. Correggile in qualsiasi momento con l'azione **Correggi** accanto ad esse nella tab Setup installati — scegli la cartella LMU giusta dall'elenco. La correzione viene salvata localmente e ha effetto immediato, nessun file da modificare.

### Sandbox (per chi sviluppa)

Serve a sviluppare e testare l'applicativo stesso. Ogni flag sostituisce un sistema esterno con una controparte locale, così puoi eseguire il programma su una macchina senza abbonamento TrackTitan e senza Le Mans Ultimate installato. Sono opzioni da riga di comando — non viene scritto nulla nelle tue impostazioni/credenziali reali — e si combinano liberamente.

```
python src/main.py --sandbox                    # mocka tutto
python src/main.py --mock-tracktitan --mock-lmu  # mocka questi due, Dropbox reale
python src/main.py --sandbox --mode master       # sandbox, forzando una modalità
```

| Flag                          | Effetto                                                                                                                     |
| :----------------------------- | :----------------------------------------------------------------------------------------------------------------------------- |
| `--sandbox`                   | Scorciatoia per tutti e tre i `--mock-*` qui sotto.                                                                          |
| `--mock-tracktitan`           | Legge i setup dal catalogo di esempio in `sandbox/tracktitan/` invece di chiamare l'API TrackTitan. Nessun token richiesto. |
| `--mock-lmu`                  | Installa in `sandbox/lmu/Settings/` invece che nella cartella del gioco. Usa un database separato, quindi i record della tua installazione reale restano intatti. |
| `--mock-dropbox`              | Usa la cartella locale `sandbox/dropbox/` invece di Dropbox. Nessuna credenziale richiesta.                                  |
| `--mock-base-path PATH`       | Dove risiede la sandbox. Default: `sandbox`.                                                                                |
| `--mode {full,master,slave}` | Forza la modalità salvata solo per questa esecuzione.                                                                       |

Ogni flag rimuove anche il relativo controllo sulle credenziali: `--sandbox --mode master` e poi `--sandbox --mode slave` eseguono un giro completo pubblica → installa senza alcuna credenziale configurata. Ogni esecuzione in sandbox scrive un avviso `SANDBOX ACTIVE` nei log, così non puoi confonderla con una reale. Funzionano anche le variabili d'ambiente equivalenti `MOCK_TRACKTITAN` / `MOCK_LMU` / `MOCK_DROPBOX` / `MODE`, e `.vscode/launch.json` include un profilo di debug per ogni combinazione.

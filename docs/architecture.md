# Documentazione Architetturale QwenTTS All-in-One

Questa documentazione descrive l'architettura tecnica del progetto QwenTTS All-in-One. È pensata per essere letta da un LLM o da uno sviluppatore per comprendere rapidamente dove intervenire per modifiche future.

## 📂 Struttura del Progetto

```
C:\PYTHONWS\PROGETTI\QWENTTS
│   download_models.bat      # Script per scaricare i modelli HuggingFace
│   README.md                # Documentazione generale utente
│   requirements.txt         # Dipendenze Python pip
│   setup.bat                # Script di installazione automatica (venv, ffmpeg, dependencies)
│   start.bat                # Script di avvio del server Flask
│
├───backend                  # Logica Server Side (Python/Flask)
│   │   app.py               # Entry point Flask, definisce le API REST
│   │   model_manager.py     # Gestione singleton dei modelli AI, lazy loading, inferenza
│   │   chimera_maker.py     # Gestione pipeline ibrida (Reference + TTS) e crossfading
│   │   personality_manager.py # CRUD per le personalità vocali su file system
│   │
├───docs                     # Documentazione tecnica
│       architecture.md      # Questo file
│
├───frontend                 # Interfaccia Utente (Web)
│       index.html           # Struttura HTML Single Page Application
│       script.js            # Logica frontend, gestione stato, chiamate API, WebSocket/SSE
│       style.css            # Stile glassmorphic, design system, animazioni
│
├───models                   # Directory per i pesi dei modelli (scaricati da HF)
│   ├───base                 # Modello Qwen3-TTS-Base (Clonazione)
│   ├───custom               # Modello Qwen3-TTS-CustomVoice (Preset)
│   └───design               # Modello Qwen3-TTS-VoiceDesign (Descrizione)
│
├───output                   # Directory temporanea per file generati e upload
│
└───saved_personalities      # Storage persistente per le personalità utente
```

---

## 🐍 Backend (Python/Flask)

Il backend è un server Flask leggero che funge da wrapper per i modelli PyTorch di QwenTTS.

### 1. `backend/app.py`
**Ruolo**: Controller API & Entry Point.
**Descrizione**: Gestisce le richieste HTTP, il routing e lo streaming degli eventi (SSE) per la progress bar.

**Funzioni Chiave**:
- `@app.route("/api/generate_stream")`: Endpoint principale. Utilizza un thread separato per l'inferenza e un generatore Python per inviare eventi SSE (`text/event-stream`) al client con lo stato di avanzamento reale (tokenizzazione, inferenza, encoding).
- `generate_with_progress()`: Funzione interna complessa che gestisce il ciclo di vita della generazione:
    1.  Switch modello (se necessario).
    2.  Caricamento personalità (se richiesta).
    3.  Stima tempi.
    4.  Chiamata a `manager.generate()`.
    5.  Conversione post-processo (WAV -> MP3 opzionale).
- `@app.route("/api/switch_model")`: Endpoint per forzare il cambio modello (Hot-swap VRAM).
- `@app.route("/api/personality/*")`: Endpoints CRUD che delegano a `PersonalityManager`.

**Modifiche Future**:
- Aggiungere nuovi endpoint API qui.
- Modificare la logica di streaming o gestione errori HTTP.

### 2. `backend/model_manager.py`
**Ruolo**: Core Logic AI & Resource Management.
**Descrizione**: Implementa il pattern Singleton. Gestisce il ciclo di vita dei modelli QwenTTS e Whisper, ottimizzando l'uso della VRAM (che è critica su GPU da 8GB).

**Classi & Metodi**:
- `ModelManager`: Classe principale.
- `load_model(target_type: str)`: Scarica il modello corrente (`unload_model()`, liberando CUDA cache) e carica quello richiesto. Questo è fondamentale per evitare OOM (Out Of Memory).
- `generate(params)`: Dispatcher che chiama il metodo specifico (`_generate_clone`, `_generate_custom`, `_generate_design`) in base al modello attivo.
- `_generate_multi_segment(...)`: Logica avanzata per gestire testi con tag emotivi (es: `[felice] Ciao [triste] Addio`). Carica i sample audio corrispondenti alla personalità e concatena l'audio risultante.
- `transcribe(...)`: Usa OpenAI Whisper (`large-v3` o `base`) per trascrivere audio di riferimento (usato per clonazione e dataset personalità).

**Modifiche Future**:
- Modificare parametri di inferenza (temperature, top_k, ecc.).
- Cambiare logica di gestione memoria.
- Integrare nuovi modelli AI.

### 4. `backend/chimera_maker.py`
**Ruolo**: Audio Hybridization Engine.
**Descrizione**: Modulo specializzato per la pipeline "Chimera". Combina la voce reale dell'utente (per il timbro) con l'espressività generata dall'AI.

**Funzionalità Core**:
- `create_chimera_reference()`: Prende un audio utente e un audio AI (emotivo), e li fonde.
- **Crossfading Intelligente**: Applica dissolvenze incrociate (50-200ms) per rendere impercettibile la giunzione tra i due audio.
- Gestione segmenti temporali: Taglia e incolla i segmenti audio (es. prendere i primi 5s).

### 3. `backend/personality_manager.py`
**Ruolo**: Data Persistence Layer.
**Descrizione**: Gestisce il salvataggio e recupero delle "Personalità" (profili vocali custom). Non usa database, ma file system (JSON + WAV).

**Struttura Dati**:
Ogni personalità è una cartella in `saved_personalities/<nome_sanitizzato>/` contenente:
- `config.json`: Metadati e mappa emozioni -> file audio.
- `*.wav`: I file audio di riferimento per le varie emozioni.

**Modifiche Future**:
- Cambiare formato di storage (es. database SQL).
- Aggiungere metadati alle personalità.

---

## 💻 Frontend (HTML/JS/CSS)

Interfaccia web moderna (Glassmorphism) senza framework pesanti (Vanilla JS).

### 1. `frontend/index.html`
**Ruolo**: Struttura.
**Descrizione**: Contiene il layout, modali, e container.
**Sezioni**:
- `#homepage`: Schermata iniziale di selezione modello.
- `#main-app`: L'applicazione vera e propria (nascosta inizialmente).
- Pannelli dinamici: `#panel-base` (Clonazione), `#panel-custom` (Preset), `#panel-design`.

### 2. `frontend/script.js`
**Ruolo**: Comportamento & State Management.
**Descrizione**: Gestisce tutta la logica client-side.
**Flussi principali**:
- `setupHomepage()`: Gestisce la transizione iniziale Homepage -> App.
- `switchTab(modelType)`: Chiama `/api/switch_model` e gestisce le animazioni di cambio pannello.
- `generate(params)`: Effettua la richiesta POST a `/api/generate_stream` e legge lo stream SSE. Decodifica i chunk JSON (`data: {...}`) per aggiornare la progress bar e gestire l'URL audio finale.
- `setupPersonalityBuilder()`: Logica per il modale di creazione personalità (Manual & Smart Mode).
- **Gestione Chimera**: UI per il mixaggio voce utente/AI, con slider per crossfade e temperatura.

### 3. `frontend/style.css`
**Ruolo**: Styling & Design System.
**Descrizione**: CSS moderno con CSS Variables.
**Caratteristiche**:
- Tema "Aqua Green" (`--primary-gradient`, ecc.).
- Animazioni keyframe (`fadeIn`, `slideUp`, `ripple`).
- Interfaccia responsive.

---

## ⚙️ Scripts di Automazione

### 1. `setup.bat`
Automazione completa per Windows:
1. Controlla Python 3.13.10.
2. Crea `venv`.
3. Installa dipendenze (`requirements.txt`).
4. **Installa FFmpeg portatile**: Scarica, estrae e copia `ffmpeg.exe` dentro `venv/Scripts` per renderlo disponibile al path senza installazione di sistema.

### 2. `download_models.bat`
Usa `huggingface-cli` per scaricare i 3 modelli Qwen (~15GB) nelle cartelle corrette.

### 3. `start.bat`
Attiva il venv e lancia `python backend/app.py`.

---

## 🔄 Flusso di Generazione (Data Flow)

1. **User Action**: Clic su "Genera Audio".
2. **Frontend**: Raccoglie parametri, disabilita UI, apre connessione SSE a `/api/generate_stream`.
3. **Backend (Main Thread)**: Riceve richiesta.
4. **Backend (Gen Thread)**:
    - Controlla modello caricato vs richiesto.
    - Se diverso -> `model_manager.load_model()` (Scarica vecchio, carica nuovo, 10-30s).
    - Invia evento SSE `stage: "Switch modello..."`.
    - Esegue inferenza `manager.generate()`.
    - Salva WAV temporaneo -> Converte MP3 (opzionale).
    - Invia evento SSE `done: true, url: ...`.
5. **Frontend**: Riceve URL, abilita player audio, mostra tasto download.

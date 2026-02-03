# QwenTTS All-in-One

Applicazione web per Text-to-Speech con **Qwen3-TTS**, ottimizzata per **RTX 2070 (8GB VRAM)** tramite strategia **Lazy Loading con Hot-Swapping**.

## 🎯 Caratteristiche

- **3 Modelli TTS in un'unica interfaccia:**
  - **Voice Clone** - Clona qualsiasi voce da un audio di riferimento
  - **Custom Voice** - Usa speaker predefiniti (Vivian, Ryan, Alya, ecc.) con controllo emotivo
  - **Voice Design** - Crea voci personalizzate da descrizione testuale
  - **Chimera Pipeline** - Generazione ibrida (Timbro Reale + Emotività AI) per realismo estremo

- **Personality Builder 2.0:**
  - **Smart Mode**: Creazione automatica di personalità multilingua/multi-emozione da un singolo file.
  - **Manuale**: Controllo granulare su ogni singolo sample emotivo.

- **Gestione Intelligente VRAM:**
  - Un solo modello in GPU alla volta (~4.5GB)
  - Hot-swapping automatico al cambio tab
  - Pulizia completa memoria con `gc.collect()` + `torch.cuda.empty_cache()`

- **Interfaccia Web Moderna:**
  - Design dark mode con animazioni fluide
  - Overlay di caricamento durante gli swap
  - Monitoraggio in tempo reale della VRAM

---

## 📋 Requisiti

| Requisito | Valore |
|-----------|--------|
| **Python** | 3.13.10 |
| **GPU** | NVIDIA RTX 2070 (8GB VRAM) |
| **RAM** | 32GB (consigliato) |
| **Disco** | ~15GB per i 3 modelli 1.7B |
| **Software** | **FFmpeg** (necessario per MP3) |

---

## 🚀 Installazione

### 0. Prerequisiti
1. Installare [Python 3.10+](https://www.python.org/)
2. Installare [FFmpeg](https://ffmpeg.org/download.html) e aggiungerlo al PATH di sistema (necessario per elaborazione audio e MP3).
3. Installare driver NVIDIA aggiornati e [CUDA Toolkit 12.x](https://developer.nvidia.com/cuda-toolkit).

### 1. Crea Ambiente Virtuale

```bash
# Crea ambiente virtuale con venv (integrato in Python)
python -m venv venv

# Attiva l'ambiente
# Su Windows:
venv\Scripts\activate

# Su Linux/Mac:
source venv/bin/activate
```

### 2. Installa Dipendenze

```bash
# Aggiorna pip
python -m pip install --upgrade pip

# Installa pacchetti Python
pip install -r requirements.txt

# Flash Attention 2 (opzionale ma consigliato)
pip install -U flash-attn --no-build-isolation
```

### 3. Scarica i Modelli

Esegui questi comandi per scaricare i 3 modelli in locale:

```bash
# Installa Hugging Face CLI (se non già installato)
pip install -U "huggingface_hub[cli]"

# Scarica Base (Voice Clone)
huggingface-cli download Qwen/Qwen3-TTS-12Hz-1.7B-Base --local-dir ./models/base

# Scarica CustomVoice (Speaker Preset)
huggingface-cli download Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice --local-dir ./models/custom

# Scarica VoiceDesign (Creazione Voci)
huggingface-cli download Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign --local-dir ./models/design
```

**Nota:** Il download totale è ~15GB. Richiederà tempo a seconda della tua connessione.

---

## 🎮 Utilizzo

### Avvio Rapido

**Windows:**
```bash
.\start.bat
```

**Manuale:**
```bash
# Attiva ambiente virtuale
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Avvia server
python backend/app.py
```

Poi apri il browser su: **http://localhost:5000**

---

## 📖 Guida d'Uso

### 1. Voice Clone (Base)
1. Clicca sul tab **🎤 Clonazione**
2. Carica un file audio di riferimento (WAV/MP3)
3. Usa la **Waveform interattiva** per selezionare il segmento da clonare
4. Clicca **Estrai Testo dal Segmento** per trascrivere automaticamente con Whisper
5. Modifica il testo di riferimento se necessario
6. Inserisci il testo da sintetizzare
7. Premi **Genera Audio** (segui il progresso nella barra di caricamento)

### 2. Custom Voice
1. Clicca sul tab **🗣️ Voci Preset**
2. Seleziona uno speaker (Vivian, Ryan, Alya, Leo, Sophia, Lucas)
3. Inserisci il testo da sintetizzare
4. (Opzionale) Aggiungi istruzioni emotive es: "Parla con tono allegro"
5. Premi **Genera Audio**

#### 🔧 Chimera Adjustments
Selezionando una voce Custom, puoi attivare la pipeline **Chimera**:
- Usa lo slider **Temperature** per variare la creatività dell'intonazione.
- Usa lo slider **Crossfade** per gestire la fusione tra la voce base e l'emozione generata.

### 3. Voice Design
1. Clicca sul tab **✨ Voice Design**
2. Descrivi la voce desiderata (es: "Voce maschile giovane, tono professionale")
3. Inserisci il testo da sintetizzare
4. Premi **Genera Audio**

---

## 🏗️ Struttura del Progetto

```
QwenTTS/
├── backend/
│   ├── app.py              # Server Flask con API REST e SSE
│   ├── model_manager.py    # Gestione lazy loading modelli e Whisper
│   └── chimera_maker.py    # Pipeline ibrida audio crossfading
├── frontend/
│   ├── index.html          # Interfaccia web con WaveSurfer.js
│   ├── style.css           # Stili dark mode
│   └── script.js           # Logica client-side
├── models/                 # Modelli scaricati (15GB)
│   ├── base/
│   ├── custom/
│   └── design/
├── output/                 # Audio generati e temporanei
├── requirements.txt        # Dipendenze Python
└── start.bat               # Script avvio Windows
```

---

## 🔧 API Endpoints

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/status` | GET | Stato modello corrente e VRAM |
| `/api/switch_model` | POST | Hot-swap del modello |
| `/api/generate_stream` | POST | Generazione audio TTS con eventi SSE (progresso real-time) |
| `/api/transcribe` | POST | Trascrizione audio con Whisper |
| `/api/upload_temp` | POST | Upload audio temporaneo per elaborazione |
| `/api/audio/<file>` | GET | Download audio generati |
| `/api/speakers` | GET | Lista speaker CustomVoice |

---

## 💡 Note Tecniche

### Gestione Memoria GPU

L'architettura **Lazy Loading** garantisce che:
- Un solo modello sia in VRAM alla volta (~4.5GB)
- Il cambio modello richiede 5-10 secondi
- La pulizia memoria è completa tramite:
  ```python
  del model
  gc.collect()
  torch.cuda.empty_cache()
  torch.cuda.synchronize()
  ```

### Monitoraggio VRAM

Usa `nvidia-smi` per verificare l'utilizzo in tempo reale:
```bash
nvidia-smi -l 1
```

---

## 🐛 Troubleshooting

### Errore "CUDA out of memory"
- Assicurati che nessun altro processo usi la GPU
- Riavvia il server per pulire la VRAM

### Modello non trovato
- Verifica che i modelli siano in `./models/base`, `./models/custom`, `./models/design`
- Rilancia i comandi di download

### Flash Attention non si installa
- Salta l'installazione, il sistema userà il fallback automatico
- L'inferenza sarà leggermente più lenta ma funzionante

---

## 📝 License

Questo progetto utilizza i modelli Qwen3-TTS. Consulta la [licenza ufficiale](https://github.com/QwenLM/Qwen3-TTS) per i termini d'uso.

---

## 🙏 Credits

- **Qwen Team** - Sviluppatori di Qwen3-TTS
- **Alibaba Cloud** - Ricerca e training dei modelli

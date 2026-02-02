const API_BASE = '';
let currentModel = null;
let currentCloudFilename = null;
let currentCloudPath = null;
let wavesurfer = null;
let wsRegions = null;

// Inizializzazione
document.addEventListener('DOMContentLoaded', async () => {
    await loadStatus();
    await loadSpeakers();
    setupTabs();
    setupFileUpload();

    document.getElementById('extract-text-btn').addEventListener('click', extractText);
});

// Carica stato iniziale
async function loadStatus() {
    try {
        const res = await fetch(`${API_BASE}/api/status`);
        const data = await res.json();
        updateStatusBar(data);
        currentModel = data.model_loaded;
    } catch (e) {
        console.error('Errore caricamento stato:', e);
    }
}

// Carica lista speaker
async function loadSpeakers() {
    try {
        const res = await fetch(`${API_BASE}/api/speakers`);
        const speakers = await res.json();
        const select = document.getElementById('speaker-select');
        select.innerHTML = speakers.map(s =>
            `<option value="${s.id}">${s.name} (${s.gender}, ${s.lang})</option>`
        ).join('');
    } catch (e) {
        console.error('Errore caricamento speakers:', e);
    }
}

// Setup tabs
function setupTabs() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.model));
    });
}

// Cambio tab con hot-swap modello
async function switchTab(modelType) {
    // Mostra loading se modello diverso
    if (currentModel !== modelType) {
        showLoading(`Caricamento modello ${modelType} in GPU...`, false);

        try {
            const res = await fetch(`${API_BASE}/api/switch_model`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model_type: modelType })
            });

            const data = await res.json();
            if (!data.success) {
                throw new Error(data.error || 'Errore switch modello');
            }

            currentModel = modelType;
            updateStatusBar(data.status);
        } catch (e) {
            alert('Errore: ' + e.message);
            hideLoading();
            return;
        }

        hideLoading();
    }

    // Aggiorna UI tabs
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.model === modelType);
    });

    // Mostra panel corretto
    document.querySelectorAll('.panel').forEach(p => p.classList.add('hidden'));
    document.getElementById(`panel-${modelType}`).classList.remove('hidden');
}

// Setup upload file audio e WaveSurfer
function setupFileUpload() {
    const input = document.getElementById('ref-audio');

    // Init WaveSurfer
    try {
        wavesurfer = WaveSurfer.create({
            container: '#waveform',
            waveColor: '#4F4A85',
            progressColor: '#383351',
            url: '',
            height: 80,
        });

        // Init Regions
        wsRegions = wavesurfer.registerPlugin(WaveSurfer.Regions.create());

        wsRegions.on('region-created', (region) => {
            // Keep only one region
            if (wsRegions.getRegions().length > 1) {
                wsRegions.getRegions()[0].remove();
            }
        });

        wsRegions.on('region-updated', (region) => {
            updateRegionInfo(region);
        });
    } catch (e) {
        console.error("WaveSurfer init error", e);
    }

    input.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        // Reset
        if (wsRegions) wsRegions.clearRegions();
        const btn = document.getElementById('extract-text-btn');
        if (btn) btn.disabled = true;

        // Carica visualmente
        if (wavesurfer) await wavesurfer.loadBlob(file);

        // Upload al server
        await uploadFile(file);

        // Abilita estrazione
        if (btn) btn.disabled = false;

        // Add default region (first 10s or full)
        if (wavesurfer && wsRegions) {
            const duration = await wavesurfer.getDuration();
            wsRegions.addRegion({
                start: 0,
                end: Math.min(10, duration),
                content: 'Segmento Clonazione',
                color: 'rgba(0, 255, 0, 0.1)'
            });
        }
    });
}

function updateRegionInfo(region) {
    const start = region.start.toFixed(2);
    const end = region.end.toFixed(2);
    const dur = (region.end - region.start).toFixed(2);
    const info = document.getElementById('region-info');
    if (info) info.textContent = `${dur}s (${start}s - ${end}s)`;
}

async function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    showLoading("Caricamento audio...", false);
    try {
        const res = await fetch(`${API_BASE}/api/upload_temp`, {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (data.success) {
            currentCloudFilename = data.filename;
            currentCloudPath = data.path;
        } else {
            alert("Errore upload: " + data.error);
        }
    } catch (e) {
        console.error(e);
        alert("Errore upload file");
    } finally {
        hideLoading();
    }
}

async function extractText() {
    if (!currentCloudFilename) return;

    const regions = wsRegions.getRegions();
    let start = 0;
    let end = null;

    if (regions.length > 0) {
        start = regions[0].start;
        end = regions[0].end;
    }

    showLoading("Trascrizione in corso (Whisper)...", false);
    try {
        const res = await fetch(`${API_BASE}/api/transcribe`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                filename: currentCloudFilename,
                start,
                end
            })
        });
        const data = await res.json();
        if (data.text) {
            document.getElementById('ref-text').value = data.text;
        } else if (data.error) {
            alert("Errore trascrizione: " + data.error);
        }
    } catch (e) {
        console.error(e);
        alert("Errore chiamata trascrizione");
    } finally {
        hideLoading();
    }
}

// Generazione Base (Clone)
async function generateBase() {
    const text = document.getElementById('target-text-base').value.trim();
    const refText = document.getElementById('ref-text').value.trim();
    const language = document.getElementById('lang-base').value;
    const format = document.getElementById('format-base').value;

    if (!text || !refText || !currentCloudPath) {
        alert('Compila tutti i campi e carica un audio di riferimento');
        return;
    }

    // Get region if available
    let start = null;
    let end = null;
    if (wsRegions) {
        const regions = wsRegions.getRegions();
        if (regions.length > 0) {
            start = regions[0].start;
            end = regions[0].end;
        }
    }

    await generate({
        expected_model: 'base',
        text,
        ref_text: refText,
        ref_audio: currentCloudPath, // Use server path
        start_time: start,
        end_time: end,
        language,
        format
    });
}

// Generazione Custom Voice
async function generateCustom() {
    const text = document.getElementById('target-text-custom').value.trim();
    const speaker = document.getElementById('speaker-select').value;
    const instruct = document.getElementById('instruct-custom').value.trim();
    const language = document.getElementById('lang-custom').value;
    const format = document.getElementById('format-custom').value;

    if (!text) {
        alert('Inserisci il testo da sintetizzare');
        return;
    }

    await generate({
        expected_model: 'custom',
        text,
        speaker,
        instruct,
        language,
        format
    });
}

// Generazione Voice Design
async function generateDesign() {
    const text = document.getElementById('target-text-design').value.trim();
    const instruct = document.getElementById('voice-description').value.trim();
    const language = document.getElementById('lang-design').value;
    const format = document.getElementById('format-design').value;

    if (!text || !instruct) {
        alert('Inserisci sia la descrizione vocale che il testo');
        return;
    }

    await generate({
        expected_model: 'design',
        text,
        instruct,
        language,
        format
    });
}

// Funzione generica di generazione con SSE
async function generate(params) {
    showLoading('Inizializzazione...', true);  // true = mostra progress
    disableButtons(true);

    try {
        // Usa endpoint streaming con fetch
        const response = await fetch(`${API_BASE}/api/generate_stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params)
        });

        // Legge lo stream
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = JSON.parse(line.slice(6));

                    if (data.error) {
                        throw new Error(data.error);
                    }

                    // Aggiorna progresso
                    if (data.progress !== undefined) {
                        updateProgress(data.progress, data.stage, data.eta);
                    }

                    // Se completato, mostra audio
                    if (data.done && data.audio_url) {
                        const audio = document.getElementById('output-audio');
                        const downloadLink = document.getElementById('download-link');

                        audio.src = data.audio_url;
                        audio.classList.remove('hidden');

                        // Configura link download
                        downloadLink.href = data.audio_url;
                        downloadLink.download = `qwen-tts-${Date.now()}.${params.format || 'wav'}`;
                        downloadLink.classList.remove('hidden');

                        document.getElementById('output-placeholder').classList.add('hidden');
                        audio.play();
                    }
                }
            }
        }

    } catch (e) {
        alert('Errore: ' + e.message);
    } finally {
        hideLoading();
        disableButtons(false);
    }
}

// Aggiorna UI progresso
function updateProgress(percent, stage, eta) {
    document.getElementById('progress-fill').style.width = `${percent}%`;
    document.getElementById('progress-percent').textContent = `${percent}%`;
    document.getElementById('loading-text').textContent = stage;

    if (eta > 0) {
        document.getElementById('progress-eta').textContent = `Tempo stimato: ${eta}s`;
    } else {
        document.getElementById('progress-eta').textContent = 'Completamento...';
    }
}

// Helpers UI
function showLoading(text, showProgress = false) {
    document.getElementById('loading-text').textContent = text;
    document.getElementById('loading-overlay').classList.remove('hidden');

    const progressContainer = document.getElementById('progress-container');
    if (showProgress) {
        progressContainer.classList.remove('hidden');
        // Reset progresso
        document.getElementById('progress-fill').style.width = '0%';
        document.getElementById('progress-percent').textContent = '0%';
        document.getElementById('progress-eta').textContent = 'Calcolo...';
    } else {
        progressContainer.classList.add('hidden');
    }
}

function hideLoading() {
    document.getElementById('loading-overlay').classList.add('hidden');
}

function disableButtons(disabled) {
    document.querySelectorAll('.generate-btn').forEach(btn => {
        btn.disabled = disabled;
    });
}

function updateStatusBar(status) {
    document.getElementById('model-status').textContent =
        status.model_loaded ? `Modello: ${status.model_loaded}` : 'Nessun modello';
    document.getElementById('vram-status').textContent =
        `VRAM: ${status.vram_used_gb} GB`;
}

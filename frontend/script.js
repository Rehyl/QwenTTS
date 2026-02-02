const API_BASE = '';
let currentModel = null;
let currentCloudFilename = null;
let currentCloudPath = null;
let wavesurfer = null;
let wsRegions = null;
let emotionRowCounter = 0;
let currentMode = 'manual'; // 'manual' or 'personality'
let selectedPersonality = null;

// Inizializzazione
document.addEventListener('DOMContentLoaded', async () => {
    setupHomepage();
    await loadStatus();
    await loadSpeakers();
    await loadPersonalities();
    setupTabs();
    setupFileUpload();
    setupPersonalityBuilder();
    setupModeToggle();

    document.getElementById('extract-text-btn').addEventListener('click', extractText);
});

// === Homepage Setup ===
function setupHomepage() {
    const modelCards = document.querySelectorAll('.model-card');
    const homepage = document.getElementById('homepage');
    const mainApp = document.getElementById('main-app');

    modelCards.forEach(card => {
        card.addEventListener('click', async () => {
            const modelType = card.dataset.model;

            // Animate homepage out
            homepage.style.animation = 'fadeOut 0.4s ease forwards';

            // Wait for animation
            await new Promise(resolve => setTimeout(resolve, 400));
            homepage.classList.add('hidden');

            // Show main app and load model
            mainApp.classList.remove('hidden');
            mainApp.style.animation = 'fadeIn 0.5s ease forwards';

            // Switch to selected model
            await switchTab(modelType);
        });
    });
}

// Add fadeOut animation
const style = document.createElement('style');
style.textContent = `
    @keyframes fadeOut {
        from { opacity: 1; transform: scale(1); }
        to { opacity: 0; transform: scale(0.95); }
    }
    @keyframes ripple {
        from {
            transform: scale(0);
            opacity: 0.6;
        }
        to {
            transform: scale(4);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// === Button Ripple Effect ===
function createRipple(event) {
    const button = event.currentTarget;
    const ripple = document.createElement('span');
    const rect = button.getBoundingClientRect();

    const size = Math.max(rect.width, rect.height);
    const x = event.clientX - rect.left - size / 2;
    const y = event.clientY - rect.top - size / 2;

    ripple.style.width = ripple.style.height = `${size}px`;
    ripple.style.left = `${x}px`;
    ripple.style.top = `${y}px`;
    ripple.style.position = 'absolute';
    ripple.style.borderRadius = '50%';
    ripple.style.background = 'rgba(255, 255, 255, 0.5)';
    ripple.style.pointerEvents = 'none';
    ripple.style.animation = 'ripple 0.6s ease-out';

    button.style.position = 'relative';
    button.style.overflow = 'hidden';
    button.appendChild(ripple);

    ripple.addEventListener('animationend', () => ripple.remove());
}

// Add ripple to all buttons
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('button').forEach(btn => {
        btn.addEventListener('click', createRipple);
    });
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

    // Mostra panel corretto con animazione
    const allPanels = document.querySelectorAll('.panel');
    const targetPanel = document.getElementById(`panel-${modelType}`);

    // Fade out current panel
    allPanels.forEach(p => {
        if (!p.classList.contains('hidden')) {
            p.style.animation = 'fadeOut 0.2s ease forwards';
        }
    });

    // Wait for fade out
    await new Promise(resolve => setTimeout(resolve, 200));
    allPanels.forEach(p => p.classList.add('hidden'));

    // Fade in target panel
    targetPanel.classList.remove('hidden');
    targetPanel.style.animation = 'slideUp 0.4s ease forwards';
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
    const language = document.getElementById('lang-base').value;
    const format = document.getElementById('format-base').value;

    if (!text) {
        alert('Inserisci il testo da sintetizzare');
        return;
    }

    const params = {
        expected_model: 'base',
        text,
        language,
        format
    };

    // Check mode
    if (currentMode === 'personality') {
        // Personality mode
        const personalityName = document.getElementById('personality-select').value;
        if (!personalityName) {
            alert('Seleziona una personalità');
            return;
        }

        params.personality_name = personalityName;
    } else {
        // Manual mode
        const refText = document.getElementById('ref-text').value.trim();

        if (!refText || !currentCloudPath) {
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

        params.ref_text = refText;
        params.ref_audio = currentCloudPath;
        params.start_time = start;
        params.end_time = end;
    }

    await generate(params);
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

// Load personalities from backend
async function loadPersonalities() {
    try {
        const res = await fetch(`${API_BASE}/api/personality/list`);
        const data = await res.json();

        const select = document.getElementById('personality-select');
        select.innerHTML = '<option value="">-- Seleziona una personalità --</option>';

        if (data.personalities && data.personalities.length > 0) {
            data.personalities.forEach(p => {
                const option = document.createElement('option');
                option.value = p.name;
                option.textContent = `${p.original_name || p.name} (${p.emotion_count} emozioni)`;
                select.appendChild(option);
            });
        }
    } catch (e) {
        console.error('Errore caricamento personalità:', e);
    }
}

// Setup personality builder modal
function setupPersonalityBuilder() {
    const modal = document.getElementById('personality-builder-modal');
    const openBtn = document.getElementById('personality-builder-btn');
    const closeBtn = document.getElementById('close-builder-btn');
    const addEmotionBtn = document.getElementById('add-emotion-btn');
    const saveBtn = document.getElementById('save-personality-btn');

    openBtn.addEventListener('click', () => {
        modal.classList.remove('hidden');
        // Add one emotion row by default
        document.getElementById('emotion-rows-container').innerHTML = '';
        emotionRowCounter = 0;
        addEmotionRow();
    });

    closeBtn.addEventListener('click', () => {
        modal.classList.add('hidden');
    });

    // Close on backdrop click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.add('hidden');
        }
    });

    addEmotionBtn.addEventListener('click', addEmotionRow);
    saveBtn.addEventListener('click', savePersonality);
}

// Add emotion row
function addEmotionRow() {
    const container = document.getElementById('emotion-rows-container');
    const index = emotionRowCounter++;

    const row = document.createElement('div');
    row.className = 'emotion-row';
    row.dataset.index = index;

    row.innerHTML = `
        <div class="emotion-row-header">
            <span class="emotion-row-title">Emozione #${index + 1}</span>
            <button class="emotion-remove-btn" data-index="${index}">&times;</button>
        </div>
        <div class="emotion-row-fields">
            <input type="text" class="emotion-tag" placeholder="Tag (es. neutro)" required />
            <input type="file" class="emotion-audio" accept="audio/*" required />
            <textarea class="emotion-ref-text full-width" rows="2" placeholder="Testo di riferimento..." required></textarea>
        </div>
    `;

    container.appendChild(row);

    // Add remove listener
    row.querySelector('.emotion-remove-btn').addEventListener('click', () => {
        row.remove();
    });
}

// Save personality
async function savePersonality() {
    const name = document.getElementById('personality-name-input').value.trim();
    if (!name) {
        alert('Inserisci un nome per la personalità');
        return;
    }

    const emotionRows = document.querySelectorAll('.emotion-row');
    if (emotionRows.length === 0) {
        alert('Aggiungi almeno un\'emozione');
        return;
    }

    // Build emotions array and FormData
    const formData = new FormData();
    formData.append('name', name);

    const emotions = [];
    let hasErrors = false;

    emotionRows.forEach((row, idx) => {
        const tag = row.querySelector('.emotion-tag').value.trim();
        const audioFile = row.querySelector('.emotion-audio').files[0];
        const refText = row.querySelector('.emotion-ref-text').value.trim();

        if (!tag || !audioFile || !refText) {
            alert(`Compila tutti i campi per l'Emozione #${idx + 1}`);
            hasErrors = true;
            return;
        }

        emotions.push({ tag, ref_text: refText });
        formData.append(`audio_${tag}`, audioFile);
    });

    if (hasErrors) return;

    formData.append('emotions', JSON.stringify(emotions));

    // Send to backend
    showLoading('Creazione personalità in corso...', false);
    try {
        const res = await fetch(`${API_BASE}/api/personality/create`, {
            method: 'POST',
            body: formData
        });

        const data = await res.json();

        if (data.success) {
            alert(`Personalità "${name}" creata con successo!`);
            document.getElementById('personality-builder-modal').classList.add('hidden');
            await loadPersonalities();
        } else {
            alert('Errore: ' + (data.error || 'Errore sconosciuto'));
        }
    } catch (e) {
        alert('Errore creazione personalità: ' + e.message);
    } finally {
        hideLoading();
    }
}

// Setup mode toggle
function setupModeToggle() {
    const modeBtns = document.querySelectorAll('.mode-btn');
    const manualGroup = document.querySelector('.manual-mode-group');
    const personalityGroup = document.querySelector('.personality-select-group');
    const personalitySelect = document.getElementById('personality-select');

    modeBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const mode = btn.dataset.mode;

            // Update buttons
            modeBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // Update mode
            currentMode = mode;

            // Toggle visibility
            if (mode === 'manual') {
                manualGroup.classList.remove('hidden');
                personalityGroup.classList.add('hidden');
                document.querySelector('.tag-toolbar-container').classList.add('hidden');
            } else {
                manualGroup.classList.add('hidden');
                personalityGroup.classList.remove('hidden');
            }
        });
    });

    // Personality select change
    personalitySelect.addEventListener('change', async (e) => {
        const personalityName = e.target.value;

        if (!personalityName) {
            document.querySelector('.tag-toolbar-container').classList.add('hidden');
            selectedPersonality = null;
            return;
        }

        // Load personality details
        try {
            const res = await fetch(`${API_BASE}/api/personality/${personalityName}`);
            const personality = await res.json();

            if (personality.error) {
                alert('Errore caricamento personalità: ' + personality.error);
                return;
            }

            selectedPersonality = personality;

            // Build tag toolbar
            const toolbar = document.getElementById('tag-toolbar');
            toolbar.innerHTML = '';

            Object.keys(personality.emotions).forEach(tag => {
                const btn = document.createElement('button');
                btn.className = 'tag-btn';
                btn.textContent = `[${tag}]`;
                btn.addEventListener('click', () => insertTag(tag));
                toolbar.appendChild(btn);
            });

            document.querySelector('.tag-toolbar-container').classList.remove('hidden');
        } catch (e) {
            alert('Errore caricamento personalità: ' + e.message);
        }
    });
}

// Insert tag at cursor position
function insertTag(tag) {
    const textarea = document.getElementById('target-text-base');
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const text = textarea.value;

    const tagText = `[${tag}] `;
    const newText = text.substring(0, start) + tagText + text.substring(end);

    textarea.value = newText;
    textarea.focus();
    textarea.setSelectionRange(start + tagText.length, start + tagText.length);
}

function updateStatusBar(status) {
    document.getElementById('model-status').textContent =
        status.model_loaded ? `Modello: ${status.model_loaded}` : 'Nessun modello';
    document.getElementById('vram-status').textContent =
        `VRAM: ${status.vram_used_gb} GB`;
}

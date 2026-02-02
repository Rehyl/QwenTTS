import os
import uuid
import soundfile as sf
import json
import time
import threading
from flask import (
    Flask,
    request,
    jsonify,
    send_from_directory,
    send_file,
    Response,
    stream_with_context,
)
from flask_cors import CORS
from pathlib import Path

from model_manager import ModelManager

app = Flask(__name__, static_folder="../frontend")
CORS(app)

manager = ModelManager()
OUTPUT_DIR = Path(__file__).parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(app.static_folder, path)


@app.route("/api/status", methods=["GET"])
def get_status():
    """Ritorna quale modello è attualmente caricato"""
    return jsonify(manager.get_status())


@app.route("/api/switch_model", methods=["POST"])
def switch_model():
    """Cambia modello attivo (con hot-swap della VRAM)"""
    data = request.json
    model_type = data.get("model_type")

    if model_type not in ["base", "custom", "design"]:
        return jsonify({"error": "Tipo modello non valido"}), 400

    try:
        manager.load_model(model_type)
        return jsonify(
            {
                "success": True,
                "model_loaded": model_type,
                "status": manager.get_status(),
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/generate_stream", methods=["POST"])
def generate_stream():
    """Genera audio TTS con progresso streaming tramite SSE"""
    data = request.json
    expected_model = data.get("expected_model")
    audio_format = data.get("format", "wav").lower()

    # Il controllo del modello viene fatto nel thread di generazione per gestire lo switch automatico
    pass

    def generate_with_progress():
        """Generatore per SSE con aggiornamenti progresso REALI"""

        # Stato condiviso tra thread
        progress_state = {
            "progress": 0,
            "stage": "Inizializzazione...",
            "eta": 0,
            "done": False,
            "error": None,
            "audio_url": None,
        }

        def generation_thread():
            """Thread che esegue la generazione effettiva"""
            try:
                # Stima durata basata sulla lunghezza del testo
                text_length = len(data.get("text", ""))
                estimated_seconds = max(5, text_length * 0.1)

                progress_state["stage"] = "Preparazione modello..."
                progress_state["eta"] = int(estimated_seconds)

                # Check e switch modello se necessario
                if manager.current_model_type != expected_model:
                    progress_state["stage"] = f"Switch modello: {expected_model}..."
                    manager.load_model(expected_model)

                time.sleep(0.5)

                # Fase 2: Tokenizzazione (20%)
                progress_state["progress"] = 20
                progress_state["stage"] = "Tokenizzazione in corso..."
                progress_state["eta"] = int(estimated_seconds * 0.8)
                time.sleep(0.3)

                # Fase 3: Generazione (25-70% con aggiornamenti progressivi)
                progress_state["progress"] = 25
                progress_state["stage"] = "Generazione audio (inferenza GPU)..."
                progress_state["eta"] = int(estimated_seconds * 0.75)

                # Avvia generazione effettiva
                start_time = time.time()
                result = {"wavs": None, "sr": None, "error": None}

                def actual_generation():
                    try:
                        result["wavs"], result["sr"] = manager.generate(data)
                    except Exception as e:
                        result["error"] = str(e)

                gen_thread = threading.Thread(target=actual_generation)
                gen_thread.start()

                # Simula progresso incrementale mentre la generazione è in corso
                while gen_thread.is_alive():
                    elapsed = time.time() - start_time
                    # Progresso stimato: da 25% a 70% in base al tempo trascorso
                    estimated_progress = min(
                        70, 25 + int((elapsed / estimated_seconds) * 45)
                    )
                    progress_state["progress"] = estimated_progress
                    remaining = max(1, int(estimated_seconds - elapsed))
                    progress_state["eta"] = remaining
                    time.sleep(0.5)  # Aggiorna ogni 500ms

                gen_thread.join()

                if result["error"]:
                    raise Exception(result["error"])

                wavs, sr = result["wavs"], result["sr"]

                # Fase 4: Post-processing (75%)
                progress_state["progress"] = 75
                progress_state["stage"] = "Salvataggio file WAV..."
                progress_state["eta"] = 2
                time.sleep(
                    0.4
                )  # Permette al loop SSE di catturare questo aggiornamento

                # Salva file
                base_filename = uuid.uuid4().hex
                temp_wav_path = OUTPUT_DIR / f"{base_filename}.wav"
                sf.write(str(temp_wav_path), wavs[0], sr)

                # Fase 5: Conversione (85%)
                if audio_format == "mp3":
                    progress_state["progress"] = 85
                    progress_state["stage"] = "Conversione in MP3..."
                    progress_state["eta"] = 1
                    time.sleep(
                        0.4
                    )  # Permette al loop SSE di catturare questo aggiornamento
                    try:
                        from pydub import AudioSegment

                        mp3_path = OUTPUT_DIR / f"{base_filename}.mp3"
                        audio = AudioSegment.from_wav(str(temp_wav_path))
                        audio.export(str(mp3_path), format="mp3", bitrate="192k")
                        temp_wav_path.unlink()
                        audio_url = f"/api/audio/{base_filename}.mp3"
                    except ImportError:
                        audio_url = f"/api/audio/{base_filename}.wav"
                else:
                    audio_url = f"/api/audio/{base_filename}.wav"

                # Fase 6: Finalizzazione (95%)
                progress_state["progress"] = 95
                progress_state["stage"] = "Finalizzazione..."
                progress_state["eta"] = 0
                time.sleep(
                    0.4
                )  # Permette al loop SSE di catturare questo aggiornamento

                # Completato (100%)
                progress_state["progress"] = 100
                progress_state["stage"] = "Completato!"
                progress_state["eta"] = 0
                progress_state["audio_url"] = audio_url
                time.sleep(
                    0.4
                )  # Permette al loop SSE di catturare questo aggiornamento PRIMA di done=True
                progress_state["done"] = True

            except Exception as e:
                progress_state["error"] = str(e)

        # Avvia thread generazione
        thread = threading.Thread(target=generation_thread)
        thread.start()

        # Stream aggiornamenti progresso in tempo reale
        last_progress = -1
        last_heartbeat = time.time()
        while not progress_state["done"] and not progress_state["error"]:
            current_time = time.time()
            # Invia aggiornamento se progresso è cambiato O se è passato troppo tempo (heartbeat)
            if (
                progress_state["progress"] != last_progress
                or (current_time - last_heartbeat) > 2
            ):
                update = {
                    "progress": progress_state["progress"],
                    "stage": progress_state["stage"],
                    "eta": progress_state["eta"],
                }
                yield f"data: {json.dumps(update)}\n\n"
                last_progress = progress_state["progress"]
                last_heartbeat = current_time
            time.sleep(0.3)  # Controlla ogni 300ms

        # Invia risultato finale o errore
        if progress_state["error"]:
            yield f"data: {json.dumps({'error': progress_state['error']})}\n\n"
        else:
            final = {
                "progress": 100,
                "stage": "Completato!",
                "eta": 0,
                "audio_url": progress_state["audio_url"],
                "done": True,
            }
            yield f"data: {json.dumps(final)}\n\n"

    return Response(
        stream_with_context(generate_with_progress()), mimetype="text/event-stream"
    )


@app.route("/api/audio/<filename>")
def serve_audio(filename):
    """Serve file audio generati"""
    # Determina mimetype in base all'estensione
    mimetype = "audio/mpeg" if filename.endswith(".mp3") else "audio/wav"
    return send_file(OUTPUT_DIR / filename, mimetype=mimetype)


@app.route("/api/speakers", methods=["GET"])
def get_speakers():
    """Ritorna lista speaker disponibili per CustomVoice"""
    speakers = [
        {"id": "Vivian", "name": "Vivian", "lang": "Chinese", "gender": "Female"},
        {"id": "Ryan", "name": "Ryan", "lang": "English", "gender": "Male"},
        {"id": "Alya", "name": "Alya", "lang": "English", "gender": "Female"},
        {"id": "Leo", "name": "Leo", "lang": "Chinese", "gender": "Male"},
        {"id": "Sophia", "name": "Sophia", "lang": "English", "gender": "Female"},
        {"id": "Lucas", "name": "Lucas", "lang": "English", "gender": "Male"},
    ]
    return jsonify(speakers)


@app.route("/api/upload_temp", methods=["POST"])
def upload_temp():
    """Carica un file audio temporaneo per l'elaborazione"""
    if "file" not in request.files:
        return jsonify({"error": "Nessun file caricato"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Nessun file selezionato"}), 400

    filename = f"{uuid.uuid4().hex}_{file.filename}"
    file_path = OUTPUT_DIR / filename
    file.save(file_path)

    return jsonify({"success": True, "filename": filename, "path": str(file_path)})


@app.route("/api/transcribe", methods=["POST"])
def transcribe_audio():
    """Trascrive un segmento audio"""
    data = request.json
    filename = data.get("filename")
    start = data.get("start", 0)
    end = data.get("end")

    if not filename:
        return jsonify({"error": "Filename mancante"}), 400

    file_path = OUTPUT_DIR / filename
    if not file_path.exists():
        return jsonify({"error": "File non trovato"}), 404

    try:
        text = manager.transcribe(str(file_path), start, end)
        return jsonify({"text": text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)

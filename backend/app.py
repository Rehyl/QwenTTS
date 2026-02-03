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
from personality_manager import PersonalityManager
from chimera_maker import ChimeraMaker

app = Flask(__name__, static_folder="../frontend")
CORS(app)

manager = ModelManager()
OUTPUT_DIR = Path(__file__).parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

PERSONALITIES_DIR = Path(__file__).parent.parent / "saved_personalities"
PERSONALITIES_DIR.mkdir(exist_ok=True)
personality_manager = PersonalityManager(PERSONALITIES_DIR)
chimera_maker = ChimeraMaker()


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
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


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

                # Se c'è un personality_name, carica la config
                personality_name = data.get("personality_name")
                if personality_name:
                    progress_state["stage"] = (
                        f"Caricamento personalità '{personality_name}'..."
                    )
                    personality_config = personality_manager.get_details(
                        personality_name
                    )
                    if personality_config is None:
                        raise ValueError(
                            f"Personalità '{personality_name}' non trovata"
                        )

                    # Aggiungi il base_dir alla config per trovare i file audio
                    personality_config["_base_dir"] = str(
                        PERSONALITIES_DIR
                        / personality_manager._sanitize_name(personality_name)
                    )

                    # Aggiungi config ai params
                    data["personality_config"] = personality_config

                # Fase 2: Tokenizzazione (20%)
                progress_state["progress"] = 20
                progress_state["stage"] = "Tokenizzazione in corso..."
                progress_state["eta"] = int(estimated_seconds * 0.8)
                time.sleep(0.3)

                # Fase 3: Generazione (25-70% con aggiornamenti progressivi)
                progress_state["progress"] = 25
                if personality_name:
                    progress_state["stage"] = (
                        f"Generazione multi-segmento (personalità: {personality_name})..."
                    )
                else:
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


@app.route("/api/personality/create", methods=["POST"])
def create_personality():
    """Crea una nuova personalità vocale"""
    try:
        # Ottieni dati dal form multipart
        name = request.form.get("name")
        if not name:
            return jsonify({"error": "Nome personalità mancante"}), 400

        # Ottieni dati emozioni dal JSON
        emotions_json = request.form.get("emotions")
        if not emotions_json:
            return jsonify({"error": "Dati emozioni mancanti"}), 400

        emotions = json.loads(emotions_json)

        # Valida che ci sia almeno un'emozione
        if not emotions or len(emotions) == 0:
            return jsonify({"error": "Almeno un'emozione è richiesta"}), 400

        # Salva i file audio temporaneamente
        audio_files = {}
        for emotion in emotions:
            tag = emotion["tag"]
            if not tag:
                return jsonify({"error": "Tag emozione mancante"}), 400

            # Cerca il file con il nome corretto
            file_key = f"audio_{tag}"
            if file_key not in request.files:
                return (
                    jsonify({"error": f"File audio mancante per tag '{tag}'"}),
                    400,
                )

            audio_file = request.files[file_key]
            if audio_file.filename == "":
                return (
                    jsonify({"error": f"File audio vuoto per tag '{tag}'"}),
                    400,
                )

            # Salva temporaneamente
            temp_filename = f"{uuid.uuid4().hex}_{tag}.wav"
            temp_path = OUTPUT_DIR / temp_filename
            audio_file.save(str(temp_path))
            audio_files[tag] = temp_path

        # Crea la personalità
        config = personality_manager.create(name, emotions, audio_files)

        # Pulizia file temporanei
        for temp_path in audio_files.values():
            try:
                temp_path.unlink()
            except:
                pass

        return jsonify({"success": True, "personality": config})

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Errore creazione personalità: {str(e)}"}), 500


@app.route("/api/personality/list", methods=["GET"])
def list_personalities():
    """Ritorna lista di tutte le personalità salvate"""
    try:
        personalities = personality_manager.list_all()
        return jsonify({"personalities": personalities})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/personality/<name>", methods=["GET"])
def get_personality_details(name):
    """Ritorna dettagli completi di una personalità"""
    try:
        details = personality_manager.get_details(name)
        if details is None:
            return jsonify({"error": "Personalità non trovata"}), 404

        return jsonify(details)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/personality/<name>", methods=["DELETE"])
def delete_personality(name):
    """Elimina una personalità"""
    try:
        success = personality_manager.delete(name)
        if not success:
            return jsonify({"error": "Personalità non trovata"}), 404

        return jsonify({"success": True, "message": f"Personalità '{name}' eliminata"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/personality/create_smart", methods=["POST"])
def create_smart_personality():
    """
    Crea una Smart Personality usando la Chimera Reference Pipeline.
    Usa SSE streaming per comunicare il progresso in tempo reale.

    Input (multipart/form-data):
    - name: Nome personalità
    - voice_description: Descrizione voce per VoiceDesign
    - audio_neutro: File audio neutro utente
    - emotions: JSON array con lista emozioni da generare
    - segment_duration_ms: (opzionale) Durata segmenti chimera in ms (default: 5000)
    - crossfade_ms: (opzionale) Durata crossfade in ms (default: 100)

    Output: SSE stream con eventi di progresso
    """

    # Extract all request data BEFORE creating the generator
    # This avoids the "Working outside of request context" error
    try:
        form_name = request.form.get("name")
        form_voice_description = request.form.get("voice_description")
        form_emotions_json = request.form.get("emotions", "[]")
        form_segment_duration_ms = int(request.form.get("segment_duration_ms", 5000))
        form_crossfade_ms = int(request.form.get("crossfade_ms", 100))

        # Validate before proceeding
        if not form_name or not form_voice_description:
            return jsonify({"error": "Nome e descrizione voce sono richiesti"}), 400

        # Parse emotions early
        form_emotions = json.loads(form_emotions_json)
        if not form_emotions or len(form_emotions) == 0:
            return jsonify({"error": "Almeno un'emozione è richiesta"}), 400

        # Get and save the audio file immediately (while in request context)
        if "audio_neutro" not in request.files:
            return jsonify({"error": "File audio neutro mancante"}), 400

        audio_file = request.files["audio_neutro"]
        if audio_file.filename == "":
            return jsonify({"error": "Nessun file audio selezionato"}), 400

        # Save the audio file now, while we still have request context
        temp_audio_filename = f"{uuid.uuid4().hex}_source.wav"
        temp_audio_path = OUTPUT_DIR / temp_audio_filename
        audio_file.save(str(temp_audio_path))

    except Exception as e:
        return jsonify({"error": f"Errore validazione: {str(e)}"}), 400

    def generate_with_progress():
        """Generatore SSE per streaming progresso"""
        progress_state = {
            "progress": 0,
            "stage": "Inizializzazione...",
            "done": False,
            "error": None,
        }

        def progress_callback(stage: str, progress: int):
            """Callback per aggiornare lo stato del progresso"""
            progress_state["stage"] = stage
            progress_state["progress"] = progress

        def generation_thread():
            """Thread che esegue la creazione effettiva"""
            try:
                # Use pre-extracted form data (captured in closure)
                name = form_name
                voice_description = form_voice_description
                emotions = form_emotions
                segment_duration_ms = form_segment_duration_ms
                crossfade_ms = form_crossfade_ms

                progress_state["stage"] = "Caricamento audio..."
                progress_state["progress"] = 2

                try:
                    # Trascrivi l'audio
                    progress_state["stage"] = "Trascrizione audio (Whisper)..."
                    progress_state["progress"] = 5
                    transcript = manager.transcribe(str(temp_audio_path))

                    # Carica il modello VoiceDesign
                    progress_state["stage"] = "Caricamento modello VoiceDesign..."
                    progress_state["progress"] = 10
                    if manager.current_model_type != "design":
                        manager.load_model("design")

                    progress_state["stage"] = "Generazione emozioni..."
                    progress_state["progress"] = 15

                    # Crea la smart personality
                    config = personality_manager.create_smart(
                        name=name,
                        voice_description=voice_description,
                        source_audio_path=temp_audio_path,
                        source_transcript=transcript,
                        emotions=emotions,
                        model_manager=manager,
                        chimera_maker=chimera_maker,
                        segment_duration_ms=segment_duration_ms,
                        crossfade_ms=crossfade_ms,
                        progress_callback=progress_callback,
                    )

                    progress_state["stage"] = "Completato!"
                    progress_state["progress"] = 100
                    progress_state["personality_name"] = config["name"]
                    progress_state["done"] = True

                finally:
                    # Pulizia file temporaneo
                    try:
                        temp_audio_path.unlink()
                    except Exception:
                        pass

            except Exception as e:
                import traceback

                traceback.print_exc()
                progress_state["error"] = str(e)
                progress_state["done"] = True

        # Avvia thread generazione
        thread = threading.Thread(target=generation_thread)
        thread.start()

        # Stream aggiornamenti progresso
        last_progress = -1
        last_heartbeat = time.time()

        while not progress_state["done"]:
            current_time = time.time()
            # Invia aggiornamento se il progresso è cambiato O per heartbeat
            if (
                progress_state["progress"] != last_progress
                or (current_time - last_heartbeat) > 2
            ):
                update = {
                    "progress": progress_state["progress"],
                    "stage": progress_state["stage"],
                }
                yield f"data: {json.dumps(update)}\n\n"
                last_progress = progress_state["progress"]
                last_heartbeat = current_time

            time.sleep(0.5)  # Controlla ogni 500ms

        # Invia risultato finale
        if progress_state["error"]:
            yield f"data: {json.dumps({'error': progress_state['error']})}\n\n"
        else:
            final = {
                "progress": 100,
                "stage": "Completato!",
                "done": True,
                "personality_name": progress_state.get("personality_name"),
            }
            yield f"data: {json.dumps(final)}\n\n"

    return Response(
        stream_with_context(generate_with_progress()), mimetype="text/event-stream"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)

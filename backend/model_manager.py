import torch
import soundfile as sf
import numpy as np
import whisper
import librosa
import re
from qwen_tts import Qwen3TTSModel
from pathlib import Path


import gc


class ModelManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.current_model = None
        self.current_model_type = None
        self.models_dir = Path(__file__).parent.parent / "models"
        self._initialized = True
        self.whisper_model = None

    def unload_model(self):
        """Scarica il modello corrente e libera VRAM"""
        if self.current_model is not None:
            del self.current_model
            self.current_model = None
            self.current_model_type = None
            gc.collect()
            torch.cuda.empty_cache()
            torch.cuda.empty_cache()
            torch.cuda.synchronize()

    def load_whisper(self):
        """Carica il modello Whisper per la trascrizione"""
        if self.whisper_model is None:
            # Usa 'base' che è un buon compromesso. Carica su CPU se VRAM è scarsa,
            # ma useremo CUDA se disponibile e abbiamo spazio, altrimenti CPU.
            # Data la 2070 8GB, e QwenTTS che ne usa parecchia, forse meglio caricare/scaricare on-demand
            # o tenere su CPU. Proviamo su CUDA ma con lazy loading.
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self.whisper_model = whisper.load_model("base", device=device)

    def transcribe_audio(self, file_path, start=None, end=None):
        """Trascrive l'audio usando Whisper"""
        self.load_whisper()

        # Carica audio e taglia se necessario
        y, sr = librosa.load(file_path, sr=16000)

        if start is not None:
            start_sample = int(start * sr)
            end_sample = int(end * sr) if end is not None else len(y)
            y = y[start_sample:end_sample]

        # Whisper vuole float32
        y = y.astype(np.float32)

        # Trascrivi
        result = self.whisper_model.transcribe(y, fp16=torch.cuda.is_available())
        return result["text"].strip()

    def load_model(self, target_type: str) -> bool:
        """Carica un modello specifico, scaricando il precedente se necessario"""
        if self.current_model_type == target_type:
            return True  # Già caricato

        self.unload_model()

        model_paths = {
            "base": self.models_dir / "base",
            "custom": self.models_dir / "custom",
            "design": self.models_dir / "design",
            "whisper": "large-v3",  # Large-v3 for best transcription quality
        }

        model_info = model_paths.get(target_type)
        if not model_info:
            raise ValueError(f"Modello '{target_type}' non trovato")

        if target_type == "whisper":
            self.current_model = whisper.load_model(
                model_info, device="cuda" if torch.cuda.is_available() else "cpu"
            )
        else:
            if not model_info.exists():
                raise ValueError(f"Modello '{target_type}' non trovato in {model_info}")

            self.current_model = Qwen3TTSModel.from_pretrained(
                str(model_info),
                device_map="cuda:0",
                dtype=torch.bfloat16,
                attn_implementation="eager",
            )
        self.current_model_type = target_type
        return True

    def transcribe(self, audio_path: str, start: float = 0, end: float = None) -> str:
        """Trascrive audio usando Whisper con massima qualità"""
        self.load_model("whisper")

        # Load audio with librosa to handle slicing
        y, sr = librosa.load(audio_path, sr=16000)

        # Slice if needed
        if start > 0 or end is not None:
            start_sample = int(start * sr)
            end_sample = int(end * sr) if end else len(y)
            y = y[start_sample:end_sample]

        # Transcribe with optimal parameters for quality
        result = self.current_model.transcribe(
            y,
            language="it",  # Italian language for better accuracy
            task="transcribe",
            fp16=torch.cuda.is_available(),
            temperature=0,  # Deterministic output (no sampling randomness)
            beam_size=5,  # Beam search for better quality
            best_of=5,  # Consider multiple candidates
            patience=1.0,  # Patience for beam search
            condition_on_previous_text=True,  # Better context handling
            initial_prompt="",  # Can be customized if needed
            word_timestamps=False,  # Don't need word-level timestamps
        )
        return result["text"].strip()

    def generate(self, params: dict) -> tuple:
        """Genera audio in base al modello corrente"""
        if self.current_model is None:
            raise RuntimeError("Nessun modello caricato")

        if self.current_model_type == "base":
            return self._generate_clone(params)
        elif self.current_model_type == "custom":
            return self._generate_custom(params)
        elif self.current_model_type == "design":
            return self._generate_design(params)

    def _parse_tagged_text(self, text: str):
        """
        Parsa testo con tag emotivi.
        Input:  "[neutro] Ciao a tutti. [arrabbiato] Chi ha toccato i file?"
        Output: [("neutro", "Ciao a tutti. "), ("arrabbiato", "Chi ha toccato i file?")]

        Se non ci sono tag, ritorna il testo intero con tag None.
        """
        # Pattern per matching tag: [tag]
        pattern = r"\[([^\]]+)\]\s*"

        # Split il testo mantenendo i delimitatori
        parts = re.split(pattern, text)

        # Se non ci sono match, ritorna il testo intero
        if len(parts) == 1:
            return [(None, text.strip())]

        segments = []
        current_tag = None

        for i, part in enumerate(parts):
            if i == 0 and part.strip():
                # Testo prima del primo tag (senza tag)
                segments.append((None, part.strip()))
            elif i % 2 == 1:
                # Questo è un tag
                current_tag = part.strip()
            elif i % 2 == 0 and part.strip():
                # Questo è il testo dopo il tag
                segments.append((current_tag, part.strip()))

        return segments

    def _generate_multi_segment(self, segments, personality_config, language="Auto"):
        """
        Genera audio per ogni segmento usando il sample audio corrispondente
        e concatena i risultati.

        Args:
            segments: Lista di tuple (tag, text) dal parser
            personality_config: Dict config.json della personalità
            language: Lingua per la generazione

        Returns:
            Tuple (wavs, sr) con audio concatenato
        """
        audio_chunks = []
        sample_rate = None
        emotions_data = personality_config.get("emotions", {})

        for tag, text in segments:
            if not text.strip():
                continue

            # Se il tag è None o non esiste, usa il primo disponibile come fallback
            if tag is None or tag not in emotions_data:
                if tag is not None:
                    print(f"Warning: Tag '{tag}' non trovato, uso fallback")
                # Usa la prima emozione disponibile
                fallback_tag = list(emotions_data.keys())[0] if emotions_data else None
                if fallback_tag is None:
                    raise ValueError("Nessuna emozione disponibile nella personalità")
                tag = fallback_tag

            emotion_data = emotions_data[tag]
            ref_audio_path = str(
                Path(personality_config["_base_dir"]) / emotion_data["file"]
            )
            ref_text = emotion_data["ref_text"]

            # Genera segmento audio
            wavs, sr = self.current_model.generate_voice_clone(
                text=text,
                language=language,
                ref_audio=ref_audio_path,
                ref_text=ref_text,
            )

            # Memorizza il primo sample rate
            if sample_rate is None:
                sample_rate = sr
            elif sample_rate != sr:
                # Resample se necessario (non dovrebbe accadere)
                import librosa

                wavs[0] = librosa.resample(wavs[0], orig_sr=sr, target_sr=sample_rate)

            audio_chunks.append(wavs[0])

        # Concatena tutti i chunk
        if len(audio_chunks) == 0:
            raise ValueError("Nessun audio generato")

        concatenated = np.concatenate(audio_chunks, axis=0)

        return [concatenated], sample_rate

    def _generate_clone(self, params):
        """
        Genera audio con clonazione vocale.
        Supporta sia modalità manuale (ref_audio) che modalità personalità (personality_config).
        """
        # Check se stiamo usando una personalità
        personality_config = params.get("personality_config")

        if personality_config:
            # Modalità Personalità: parsing e multi-segment
            text = params["text"]
            language = params.get("language", "Auto")

            segments = self._parse_tagged_text(text)
            return self._generate_multi_segment(segments, personality_config, language)

        # Modalità Manuale: comportamento originale
        ref_audio_path = params["ref_audio"]

        # Pre-process audio: slice and normalize
        # Se params ha start/end, usali. Altrimenti, se il file è lungo, taglia i primi 15s.
        start = params.get("start_time")
        end = params.get("end_time")

        # Carica audio originale
        y, sr = sf.read(ref_audio_path)

        # Se stereo, converti in mono (media dei canali)
        if len(y.shape) > 1:
            y = np.mean(y, axis=1)

        original_duration = len(y) / sr

        # Determina i punti di taglio
        if start is not None:
            start_sample = int(float(start) * sr)
            end_sample = int(float(end) * sr) if end is not None else len(y)
            # Clip ai limiti
            start_sample = max(0, start_sample)
            end_sample = min(len(y), end_sample)
            y_segment = y[start_sample:end_sample]
        elif original_duration > 15:
            # Fallback intelligente: prendi 15s ignorando il primo secondo (spesso silenzio o rumore)
            start_sample = int(1.0 * sr)
            end_sample = int(16.0 * sr)
            if start_sample >= len(y):  # File molto corto o strano
                start_sample = 0
                end_sample = min(len(y), int(15.0 * sr))
            y_segment = y[start_sample:end_sample]
        else:
            y_segment = y

        # Normalizzazione (Peak Normalization a -1.0 dB)
        max_val = np.max(np.abs(y_segment))
        if max_val > 0:
            y_segment = y_segment / max_val * 0.9

        # Salva segmento temporaneo
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            sf.write(tmp.name, y_segment, sr)
            temp_slice_path = Path(tmp.name)

        try:
            return self.current_model.generate_voice_clone(
                text=params["text"],
                language=params.get("language", "Auto"),
                ref_audio=str(temp_slice_path),
                ref_text=params["ref_text"],
            )
        finally:
            # Pulizia file temporaneo
            if temp_slice_path and temp_slice_path.exists():
                try:
                    temp_slice_path.unlink()
                except:
                    pass

    def _generate_custom(self, params):
        return self.current_model.generate_custom_voice(
            text=params["text"],
            language=params.get("language", "Auto"),
            speaker=params["speaker"],
            instruct=params.get("instruct", ""),
        )

    def _generate_design(self, params):
        return self.current_model.generate_voice_design(
            text=params["text"],
            language=params.get("language", "Auto"),
            instruct=params["instruct"],
        )

    def get_status(self) -> dict:
        """Ritorna lo stato corrente"""
        vram_used = (
            torch.cuda.memory_allocated() / 1024**3 if torch.cuda.is_available() else 0
        )
        return {
            "model_loaded": self.current_model_type,
            "vram_used_gb": round(vram_used, 2),
        }

"""
Chimera Maker Module - Audio Hybrid Reference Generator

Questo modulo crea file audio "chimera" fondendo:
- Parte 1: Audio neutro dell'utente (per il timbro vocale)
- Parte 2: Audio emotivo generato da AI (per l'espressività)

Il risultato è un riferimento ibrido che il modello Base può usare per
apprendere sia il timbro che l'emozione tramite in-context learning.
"""

from pathlib import Path
from pydub import AudioSegment
from typing import Tuple, Optional
import soundfile as sf
import numpy as np


class ChimeraMaker:
    """Crea audio ibridi per la Chimera Reference Pipeline"""

    def __init__(self):
        self.default_segment_duration_ms = 5000  # 5 secondi per segmento
        self.default_crossfade_ms = 100  # 100ms di crossfade

    def normalize_volumes(
        self, audio1: AudioSegment, audio2: AudioSegment
    ) -> Tuple[AudioSegment, AudioSegment]:
        """
        Normalizza i volumi di due audio al livello più alto tra i due.
        Questo previene salti di volume nella giunzione.

        Args:
            audio1: Primo segmento audio
            audio2: Secondo segmento audio

        Returns:
            Tuple con i due audio normalizzati
        """
        # Calcola dBFS (decibel full scale) per trovare il volume più alto
        max_dbfs = max(audio1.dBFS, audio2.dBFS)

        # Normalizza entrambi a quel livello (con headroom di -1dB)
        target_dbfs = max_dbfs - 1.0

        audio1_normalized = audio1.apply_gain(target_dbfs - audio1.dBFS)
        audio2_normalized = audio2.apply_gain(target_dbfs - audio2.dBFS)

        return audio1_normalized, audio2_normalized

    def extract_segment(
        self, audio: AudioSegment, duration_ms: int, from_start: bool = True
    ) -> AudioSegment:
        """
        Estrae un segmento di durata specifica dall'audio.

        Args:
            audio: Audio sorgente
            duration_ms: Durata del segmento in millisecondi
            from_start: Se True estrae dall'inizio, altrimenti dalla fine

        Returns:
            Segmento estratto
        """
        if len(audio) <= duration_ms:
            return audio  # Se l'audio è già più corto, ritornalo intero

        if from_start:
            return audio[:duration_ms]
        else:
            return audio[-duration_ms:]

    def create_hybrid_reference(
        self,
        source_audio_path: Path,
        ai_audio_path: Path,
        output_path: Path,
        segment_duration_ms: Optional[int] = None,
        crossfade_ms: Optional[int] = None,
    ) -> Path:
        """
        Crea un file audio ibrido "Chimera" unendo due sorgenti.

        Args:
            source_audio_path: Path dell'audio neutro dell'utente
            ai_audio_path: Path dell'audio emotivo generato dall'AI
            output_path: Path dove salvare il file chimera
            segment_duration_ms: Durata di ogni segmento (default: 5000ms)
            crossfade_ms: Durata del crossfade (default: 100ms)

        Returns:
            Path del file chimera generato

        Raises:
            FileNotFoundError: Se i file sorgente non esistono
            ValueError: Se i parametri sono invalidi
        """
        # Valida esistenza file
        if not source_audio_path.exists():
            raise FileNotFoundError(f"Audio sorgente non trovato: {source_audio_path}")
        if not ai_audio_path.exists():
            raise FileNotFoundError(f"Audio AI non trovato: {ai_audio_path}")

        # Usa valori di default se non specificati
        if segment_duration_ms is None:
            segment_duration_ms = self.default_segment_duration_ms
        if crossfade_ms is None:
            crossfade_ms = self.default_crossfade_ms

        # Validazione parametri
        if segment_duration_ms <= 0:
            raise ValueError("segment_duration_ms deve essere > 0")
        if crossfade_ms < 0:
            raise ValueError("crossfade_ms deve essere >= 0")
        if crossfade_ms >= segment_duration_ms:
            raise ValueError("crossfade_ms deve essere < segment_duration_ms")

        # Carica gli audio
        source_audio = AudioSegment.from_file(str(source_audio_path))
        ai_audio = AudioSegment.from_file(str(ai_audio_path))

        # Estrai segmenti della durata desiderata
        # Per l'audio utente: prendi dall'inizio o dal centro se è lungo
        if len(source_audio) > segment_duration_ms:
            # Se l'audio è lungo, prendi dal centro per evitare silenzi iniziali/finali
            start_pos = (len(source_audio) - segment_duration_ms) // 2
            source_segment = source_audio[start_pos : start_pos + segment_duration_ms]
        else:
            source_segment = source_audio

        # Per l'audio AI: prendi dall'inizio (dovrebbe essere già ottimale)
        ai_segment = self.extract_segment(
            ai_audio, segment_duration_ms, from_start=True
        )

        # Normalizza i volumi
        source_segment, ai_segment = self.normalize_volumes(source_segment, ai_segment)

        # Unisci con crossfade
        if crossfade_ms > 0:
            hybrid = source_segment.append(ai_segment, crossfade=crossfade_ms)
        else:
            hybrid = source_segment + ai_segment

        # Assicura che la directory di output esista
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Esporta come WAV
        hybrid.export(
            str(output_path),
            format="wav",
            parameters=["-acodec", "pcm_s16le"],  # PCM 16-bit for compatibility
        )

        return output_path

    def create_from_numpy(
        self,
        source_array: np.ndarray,
        ai_array: np.ndarray,
        sample_rate: int,
        output_path: Path,
        segment_duration_ms: Optional[int] = None,
        crossfade_ms: Optional[int] = None,
    ) -> Path:
        """
        Crea un audio chimera da array numpy (utile per output diretto dei modelli).

        Args:
            source_array: Array numpy dell'audio neutro
            ai_array: Array numpy dell'audio AI emotivo
            sample_rate: Sample rate degli audio
            output_path: Path di output
            segment_duration_ms: Durata segmenti
            crossfade_ms: Durata crossfade

        Returns:
            Path del file generato
        """
        import tempfile

        # Salva temporaneamente come file WAV
        with tempfile.NamedTemporaryFile(
            suffix="_source.wav", delete=False
        ) as tmp_source:
            source_temp = Path(tmp_source.name)
            sf.write(str(source_temp), source_array, sample_rate)

        with tempfile.NamedTemporaryFile(suffix="_ai.wav", delete=False) as tmp_ai:
            ai_temp = Path(tmp_ai.name)
            sf.write(str(ai_temp), ai_array, sample_rate)

        try:
            # Usa il metodo principale
            result = self.create_hybrid_reference(
                source_temp,
                ai_temp,
                output_path,
                segment_duration_ms,
                crossfade_ms,
            )
        finally:
            # Pulizia file temporanei
            try:
                source_temp.unlink()
                ai_temp.unlink()
            except Exception:
                pass

        return result

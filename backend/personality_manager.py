import json
import shutil
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime


class PersonalityManager:
    """Gestisce il CRUD delle personalità vocali su file system"""

    def __init__(self, base_dir: Path):
        """
        Inizializza il manager delle personalità

        Args:
            base_dir: Directory root per salvare le personalità (es. saved_personalities/)
        """
        self.base_dir = base_dir
        self.base_dir.mkdir(exist_ok=True)

    def _sanitize_name(self, name: str) -> str:
        """Sanitizza il nome della personalità per uso come nome cartella"""
        # Sostituisce spazi con underscore e rimuove caratteri non validi
        sanitized = name.strip().replace(" ", "_")
        # Rimuove caratteri non alfanumerici (tranne _ e -)
        sanitized = "".join(c for c in sanitized if c.isalnum() or c in ("_", "-"))
        return sanitized

    def create(
        self, name: str, emotions: List[Dict[str, any]], audio_files: Dict[str, Path]
    ) -> Dict[str, any]:
        """
        Crea una nuova personalità

        Args:
            name: Nome della personalità (verrà sanitizzato)
            emotions: Lista di dict con {tag, ref_text} per ogni emozione
            audio_files: Dict {tag: Path} con i file audio temporanei

        Returns:
            Dict con i dettagli della personalità creata

        Raises:
            ValueError: Se la personalità esiste già o i dati sono invalidi
        """
        sanitized_name = self._sanitize_name(name)
        if not sanitized_name:
            raise ValueError("Nome personalità invalido")

        personality_dir = self.base_dir / sanitized_name

        if personality_dir.exists():
            raise ValueError(f"Personalità '{sanitized_name}' esiste già")

        # Crea directory
        personality_dir.mkdir(parents=True)

        # Costruisce config.json
        config = {
            "name": sanitized_name,
            "original_name": name,
            "created_at": datetime.now().isoformat(),
            "emotions": {},
        }

        try:
            # Copia i file audio e popola config
            for emotion in emotions:
                tag = emotion["tag"]
                ref_text = emotion["ref_text"]

                if tag not in audio_files:
                    raise ValueError(f"File audio mancante per tag '{tag}'")

                source_file = audio_files[tag]
                if not source_file.exists():
                    raise ValueError(f"File audio non trovato: {source_file}")

                # Determina estensione (wav by default)
                ext = source_file.suffix or ".wav"
                target_filename = f"{tag}{ext}"
                target_path = personality_dir / target_filename

                # Copia il file
                shutil.copy2(source_file, target_path)

                # Aggiungi al config
                config["emotions"][tag] = {
                    "file": target_filename,
                    "ref_text": ref_text,
                }

            # Salva config.json
            config_path = personality_dir / "config.json"
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            return config

        except Exception as e:
            # Rollback: elimina la directory se qualcosa va storto
            if personality_dir.exists():
                shutil.rmtree(personality_dir)
            raise e

    def list_all(self) -> List[Dict[str, str]]:
        """
        Lista tutte le personalità salvate

        Returns:
            Lista di dict con {name, original_name, created_at}
        """
        personalities = []

        for item in self.base_dir.iterdir():
            if item.is_dir():
                config_path = item / "config.json"
                if config_path.exists():
                    try:
                        with open(config_path, "r", encoding="utf-8") as f:
                            config = json.load(f)
                            personalities.append(
                                {
                                    "name": config.get("name", item.name),
                                    "original_name": config.get(
                                        "original_name", item.name
                                    ),
                                    "created_at": config.get("created_at", ""),
                                    "emotion_count": len(config.get("emotions", {})),
                                }
                            )
                    except Exception as e:
                        print(f"Errore lettura config per {item.name}: {e}")
                        continue

        return sorted(personalities, key=lambda x: x["name"])

    def get_details(self, name: str) -> Optional[Dict[str, any]]:
        """
        Ottiene i dettagli completi di una personalità (config.json)

        Args:
            name: Nome della personalità (sanitizzato)

        Returns:
            Dict con config completo o None se non trovata
        """
        sanitized_name = self._sanitize_name(name)
        personality_dir = self.base_dir / sanitized_name
        config_path = personality_dir / "config.json"

        if not config_path.exists():
            return None

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Errore lettura config per {sanitized_name}: {e}")
            return None

    def get_audio_path(self, name: str, tag: str) -> Optional[Path]:
        """
        Ottiene il path assoluto del file audio per un tag specifico

        Args:
            name: Nome della personalità
            tag: Tag dell'emozione

        Returns:
            Path assoluto del file audio o None se non trovato
        """
        config = self.get_details(name)
        if not config:
            return None

        emotion = config.get("emotions", {}).get(tag)
        if not emotion:
            return None

        sanitized_name = self._sanitize_name(name)
        audio_file = emotion["file"]
        audio_path = self.base_dir / sanitized_name / audio_file

        return audio_path if audio_path.exists() else None

    def delete(self, name: str) -> bool:
        """
        Elimina una personalità

        Args:
            name: Nome della personalità

        Returns:
            True se eliminata, False se non esistente
        """
        sanitized_name = self._sanitize_name(name)
        personality_dir = self.base_dir / sanitized_name

        if not personality_dir.exists():
            return False

        try:
            shutil.rmtree(personality_dir)
            return True
        except Exception as e:
            print(f"Errore eliminazione personalità {sanitized_name}: {e}")
            return False

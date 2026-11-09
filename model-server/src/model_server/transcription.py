from pathlib import Path
from typing import Any, Protocol

import av
import numpy as np
from transformers import pipeline


class Transcriber(Protocol):
    def transcribe(self, audio_path: Path) -> str: ...


class PhoWhisperTranscriber:
    """Vietnamese speech recognition using VinAI PhoWhisper and local audio decoding."""

    def __init__(self, model_name: str) -> None:
        self._pipeline = pipeline(
            "automatic-speech-recognition",
            model=model_name,
            # CPU avoids CTranslate2/CUDA runtime mismatches on WSL; Torch GPU support can
            # remain enabled for the embedding and reranking models.
            device=-1,
        )

    def transcribe(self, audio_path: Path) -> str:
        audio = _decode_audio(audio_path)
        result: Any = self._pipeline({"raw": audio, "sampling_rate": 16_000})
        return str(result["text"]).strip()


def _decode_audio(audio_path: Path) -> np.ndarray:
    resampler = av.audio.resampler.AudioResampler(format="fltp", layout="mono", rate=16_000)
    chunks: list[np.ndarray] = []
    with av.open(str(audio_path), mode="r") as container:
        if not container.streams.audio:
            raise ValueError("File không có audio stream.")
        for frame in container.decode(audio=0):
            chunks.extend(part.to_ndarray().reshape(-1) for part in resampler.resample(frame))
        chunks.extend(part.to_ndarray().reshape(-1) for part in resampler.resample(None))
    if not chunks:
        raise ValueError("Không giải mã được âm thanh trong file.")
    return np.concatenate(chunks).astype(np.float32, copy=False)

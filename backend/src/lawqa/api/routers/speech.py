from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from lawqa.api.deps import AppContainer, get_container

router = APIRouter(tags=["speech"])
MAX_AUDIO_BYTES = 20 * 1024 * 1024


class TranscriptionOut(BaseModel):
    text: str


Container = Annotated[AppContainer, Depends(get_container)]


@router.post("/transcribe")
async def transcribe(container: Container, request: Request) -> TranscriptionOut:
    if container.transcribe_audio is None:
        raise HTTPException(503, "Nhận dạng giọng nói chưa được cấu hình.")
    media_type = request.headers.get("content-type", "").split(";", maxsplit=1)[0].lower()
    if not media_type.startswith("audio/"):
        raise HTTPException(415, "Tệp tải lên phải là audio.")
    content = bytearray()
    async for part in request.stream():
        if len(content) + len(part) > MAX_AUDIO_BYTES:
            raise HTTPException(413, "Tệp audio vượt quá giới hạn 20 MB.")
        content.extend(part)
    audio = bytes(content)
    if not audio:
        raise HTTPException(422, "Tệp audio rỗng.")
    return TranscriptionOut(text=await container.transcribe_audio(audio, media_type))

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from lawqa.api.deps import AppContainer, ReadinessCheck, get_container

router = APIRouter(tags=["health"])

CHECK_TIMEOUT_SECONDS = 3.0


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(container: Annotated[AppContainer, Depends(get_container)]) -> JSONResponse:
    results = await asyncio.gather(*(_run(check) for check in container.checks.values()))
    checks = dict(zip(container.checks, results, strict=True))
    ready = all(result == "ok" for result in results)
    return JSONResponse(
        {"status": "ok" if ready else "unavailable", "checks": checks},
        status_code=200 if ready else 503,
    )


async def _run(check: ReadinessCheck) -> str:
    try:
        await asyncio.wait_for(check(), timeout=CHECK_TIMEOUT_SECONDS)
    except Exception as error:
        # Only the exception type: this endpoint is public and messages can carry internal URLs.
        return f"error: {type(error).__name__}"
    return "ok"

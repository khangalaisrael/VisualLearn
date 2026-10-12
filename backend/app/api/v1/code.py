"""Running a student's program (services/code_runner.py).

    POST /code/run            compile and run a program, return what it printed
    POST /code/make-runnable  complete or correct code so that it runs

Both are for signed-in users. Running has its own daily allowance: the
sandbox is a free outside service, so its use is kept per person and
bounded. Making code runnable is a model call and counts as a chat message.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    enforce_chat_rate_limit,
    enforce_code_run_rate_limit,
    get_code_fixer,
    get_code_runner,
    get_current_user_id,
    get_db,
)
from app.models.schemas import CodeFixRequest, CodeFixResponse, CodeRunRequest, CodeRunResponse
from app.repositories.usage_events import UsageEventRepository
from app.services.code_fixer import CodeFixer
from app.services.code_runner import CodeRunner, CodeRunnerBusy, CodeRunnerUnavailable
from app.services.usage import estimate_cost_usd, start_accumulator

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/code/run", response_model=CodeRunResponse, dependencies=[Depends(enforce_code_run_rate_limit)])
async def run_code(
    body: CodeRunRequest,
    runner: CodeRunner = Depends(get_code_runner),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> CodeRunResponse:
    if current_user_id is None:
        raise HTTPException(status_code=401, detail="Sign in to run code.")
    if not body.code.strip():
        raise HTTPException(status_code=422, detail="There is no code to run.")
    try:
        result = await runner.run(body.language, body.code, body.stdin)
    except CodeRunnerBusy as exc:
        logger.warning("code_run_busy language=%s", body.language)
        raise HTTPException(
            status_code=503, detail="The code runner is busy right now. Wait a few seconds and run it again."
        ) from exc
    except CodeRunnerUnavailable as exc:
        # The program text is never logged; only that the sandbox failed.
        logger.warning("code_run_unavailable language=%s", body.language, exc_info=True)
        raise HTTPException(
            status_code=503, detail="The code runner is not answering right now. Try again in a moment."
        ) from exc
    logger.info("code_run language=%s status=%s elapsed_ms=%d", body.language, result.status, result.duration_ms)
    return CodeRunResponse(
        status=result.status,
        stdout=result.stdout,
        stderr=result.stderr,
        compiler_output=result.compiler_output,
        duration_ms=result.duration_ms,
    )


@router.post(
    "/code/make-runnable", response_model=CodeFixResponse, dependencies=[Depends(enforce_chat_rate_limit)]
)
async def make_runnable(
    body: CodeFixRequest,
    db: AsyncSession = Depends(get_db),
    fixer: CodeFixer = Depends(get_code_fixer),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> CodeFixResponse:
    if current_user_id is None:
        raise HTTPException(status_code=401, detail="Sign in to have code completed.")
    if not body.code.strip():
        raise HTTPException(status_code=422, detail="There is no code to work on.")
    usage = start_accumulator()
    try:
        fixed = await fixer.make_runnable(body.language, body.code, body.stdin, body.last_run)
    except Exception as exc:
        logger.warning("code_fix_failed language=%s", body.language, exc_info=True)
        raise HTTPException(status_code=502, detail="That could not be completed. Please try again.") from exc
    await UsageEventRepository(db).record(
        user_id=current_user_id,
        action="code_fix",
        model=fixer.model_name,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        est_cost_usd=estimate_cost_usd(fixer.model_name, usage.input_tokens, usage.output_tokens),
    )
    await db.commit()
    return CodeFixResponse(code=fixed.code, note=fixed.note)

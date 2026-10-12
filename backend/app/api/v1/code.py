"""Running a student's program (services/code_runner.py).

    POST /code/run   compile and run Haskell or Java, return what it printed

For signed-in users, with a daily allowance: the sandbox is a free outside
service, so its use is kept per person and bounded.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import enforce_code_run_rate_limit, get_code_runner, get_current_user_id
from app.models.schemas import CodeRunRequest, CodeRunResponse
from app.services.code_runner import CodeRunner, CodeRunnerUnavailable

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

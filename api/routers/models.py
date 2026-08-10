from fastapi import APIRouter, Depends

from .. import auth
from ..providers import PROVIDER_CATALOG, RECOMMENDATIONS, test_connection
from ..schemas import TestConnectionRequest, TestConnectionResponse

router = APIRouter()


@router.get("/models")
def list_models() -> dict:
    return {"providers": PROVIDER_CATALOG, "recommendations": RECOMMENDATIONS}


@router.post("/models/test-connection", response_model=TestConnectionResponse)
async def test_connection_endpoint(
    payload: TestConnectionRequest,
    user: dict = Depends(auth.get_current_user),
) -> TestConnectionResponse:
    ok, error = await test_connection(payload.provider, payload.model, payload.api_key)
    return TestConnectionResponse(ok=ok, error=error)

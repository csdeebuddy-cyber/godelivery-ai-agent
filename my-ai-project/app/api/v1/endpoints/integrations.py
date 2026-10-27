from fastapi import APIRouter, HTTPException


router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/status")
async def integrations_status() -> dict:
    return {
        "integrations": [
            {
                "provider": "google_sheets",
                "status": "not_configured",
                "configured": False,
                "sync_endpoint": "/api/v1/integrations/google-sheets/sync",
            }
        ]
    }


@router.post(
    "/google-sheets/sync",
    status_code=501,
    responses={501: {"description": "Google Sheets integration is not configured."}},
)
async def sync_google_sheets() -> None:
    raise HTTPException(
        status_code=501,
        detail={
            "code": "integration_not_configured",
            "message": "Google Sheets is not connected; no data was synchronized.",
        },
    )

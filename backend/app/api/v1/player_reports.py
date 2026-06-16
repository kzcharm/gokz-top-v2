from fastapi import APIRouter, HTTPException, status

from app import crud
from app.api.deps import CurrentUser, SessionDep
from app.models import PlayerReportCreate, PlayerReportPublic

router = APIRouter(prefix="/player-reports", tags=["player-reports"])


@router.post(
    "",
    response_model=PlayerReportPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_player_report(
    session: SessionDep,
    current_user: CurrentUser,
    report_in: PlayerReportCreate,
) -> PlayerReportPublic:
    try:
        report = await crud.create_player_report(
            session=session,
            reporter_steamid64=current_user.steamid64,
            report_in=report_in,
        )
    except crud.PlayerReportTargetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except crud.PlayerReportRecordNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        crud.PlayerReportRecordTargetMismatchError,
        crud.PlayerReportError,
    ) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return crud.to_player_report_public(report=report)

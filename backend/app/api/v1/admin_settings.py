from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app import crud
from app.api.deps import SessionDep, get_current_active_superuser
from app.models import QQBindingSecretPublic, QQBindingSecretStatusPublic, User
from app.services.qq_binding import (
    encrypt_qq_binding_secret,
    generate_qq_binding_secret,
    reveal_qq_binding_secret,
)

router = APIRouter(prefix="/admin/settings", tags=["admin-settings"])
CurrentSuperuser = Annotated[User, Depends(get_current_active_superuser)]


def _secret_response(*, secret: QQBindingSecretPublic) -> Response:
    return Response(
        content=secret.model_dump_json(),
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/qq-binding-secret", response_model=QQBindingSecretStatusPublic)
async def read_admin_qq_binding_secret_status(
    *,
    session: SessionDep,
    _current_user: CurrentSuperuser,
) -> QQBindingSecretStatusPublic:
    secret = await crud.get_qq_binding_secret(session=session)
    if secret is None:
        return QQBindingSecretStatusPublic(configured=False)
    return QQBindingSecretStatusPublic(
        configured=True,
        created_at=secret.created_at,
        updated_at=secret.updated_at,
    )


@router.post("/qq-binding-secret/generate", response_model=QQBindingSecretPublic)
async def generate_admin_qq_binding_secret(
    *,
    session: SessionDep,
    _current_user: CurrentSuperuser,
) -> Response:
    raw_secret = generate_qq_binding_secret()
    try:
        secret = await crud.create_qq_binding_secret(
            session=session,
            encrypted_secret=encrypt_qq_binding_secret(raw_secret),
        )
    except crud.QQBindingSecretAlreadyConfiguredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _secret_response(
        secret=reveal_qq_binding_secret(encrypted_secret=secret.encrypted_secret)
    )


@router.get("/qq-binding-secret/reveal", response_model=QQBindingSecretPublic)
async def reveal_admin_qq_binding_secret(
    *,
    session: SessionDep,
    _current_user: CurrentSuperuser,
) -> Response:
    secret = await crud.get_qq_binding_secret(session=session)
    if secret is None:
        raise HTTPException(status_code=404, detail="QQ binding secret is not configured")
    return _secret_response(
        secret=reveal_qq_binding_secret(encrypted_secret=secret.encrypted_secret)
    )


@router.post("/qq-binding-secret/rotate", response_model=QQBindingSecretPublic)
async def rotate_admin_qq_binding_secret(
    *,
    session: SessionDep,
    _current_user: CurrentSuperuser,
) -> Response:
    secret = await crud.get_qq_binding_secret(session=session)
    if secret is None:
        raise HTTPException(status_code=404, detail="QQ binding secret is not configured")
    raw_secret = generate_qq_binding_secret()
    secret = await crud.rotate_qq_binding_secret(
        session=session,
        secret=secret,
        encrypted_secret=encrypt_qq_binding_secret(raw_secret),
    )
    return _secret_response(
        secret=reveal_qq_binding_secret(encrypted_secret=secret.encrypted_secret)
    )


@router.delete("/qq-binding-secret", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_admin_qq_binding_secret(
    *,
    session: SessionDep,
    _current_user: CurrentSuperuser,
) -> Response:
    secret = await crud.get_qq_binding_secret(session=session)
    if secret is None:
        raise HTTPException(status_code=404, detail="QQ binding secret is not configured")
    await crud.delete_qq_binding_secret(session=session, secret=secret)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

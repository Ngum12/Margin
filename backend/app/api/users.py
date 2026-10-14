from fastapi import APIRouter

from app.api.deps import AdminUser, DbSession
from app.schemas.accounts import PasswordResetIn, UserCreateIn, UserOut, UserUpdateIn
from app.services import users as user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
def list_users(db: DbSession, admin: AdminUser) -> list[UserOut]:
    return [UserOut.model_validate(u) for u in user_service.list_users(db, admin)]


@router.post("", status_code=201)
def create_user(data: UserCreateIn, db: DbSession, admin: AdminUser) -> UserOut:
    return UserOut.model_validate(user_service.create_user(db, admin, data))


@router.patch("/{user_id}")
def update_user(user_id: int, data: UserUpdateIn, db: DbSession, admin: AdminUser) -> UserOut:
    return UserOut.model_validate(user_service.update_user(db, admin, user_id, data))


@router.post("/{user_id}/password", status_code=204)
def reset_password(user_id: int, data: PasswordResetIn, db: DbSession, admin: AdminUser) -> None:
    user_service.reset_password(db, admin, user_id, data.password)

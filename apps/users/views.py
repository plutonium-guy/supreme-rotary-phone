"""HTTP routes for the users app (Django's ``views.py`` / ``urls.py``).

The module-level ``router`` is auto-discovered and mounted at
``/api/users`` by the app registry.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status

from apps.users import services
from apps.users.schemas import UserCreate, UserOut, UserUpdate

router = APIRouter()


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED, operation_id="users_create")
async def create_user(payload: UserCreate) -> UserOut:
    user = await services.create_user(payload)
    return UserOut.model_validate(user)


@router.get("", response_model=list[UserOut], operation_id="users_list")
async def list_users(limit: int = 100, offset: int = 0) -> list[UserOut]:
    users = await services.list_users(limit=limit, offset=offset)
    return [UserOut.model_validate(u) for u in users]


@router.get("/{user_id}", response_model=UserOut, operation_id="users_retrieve")
async def retrieve_user(user_id: int) -> UserOut:
    user = await services.get_user(user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return UserOut.model_validate(user)


@router.patch("/{user_id}", response_model=UserOut, operation_id="users_update")
async def update_user(user_id: int, payload: UserUpdate) -> UserOut:
    user = await services.get_user(user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    user = await services.update_user(user, payload)
    return UserOut.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, operation_id="users_delete")
async def delete_user(user_id: int) -> Response:
    user = await services.get_user(user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    await services.delete_user(user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

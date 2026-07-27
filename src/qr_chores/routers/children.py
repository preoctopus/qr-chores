"""Parent HTML: manage child accounts."""

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.auth.deps import require_role
from qr_chores.db import get_db
from qr_chores.models.user import User, UserRole
from qr_chores.services.users import (
    UserServiceError,
    create_user,
    get_child_for_parent,
    list_children_for_parent,
    update_user_profile,
)
from qr_chores.templating import templates

router = APIRouter(tags=["children"])


@router.get("/children", response_class=HTMLResponse)
async def children_list(
    request: Request,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    kids = await list_children_for_parent(db, user.id, include_inactive=True)
    return templates.TemplateResponse(
        request,
        "children_list.html",
        {"user": user, "title": "Children", "children": kids},
    )


@router.get("/children/new", response_class=HTMLResponse)
async def children_new_form(
    request: Request,
    user: User = Depends(require_role(UserRole.parent)),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "child_form.html",
        {
            "user": user,
            "title": "Add child",
            "child": None,
            "error": None,
            "form": {
                "email": "",
                "first_name": "",
                "last_name": "",
                "password": "",
            },
        },
    )


@router.post("/children", response_model=None)
async def children_create(
    request: Request,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
):
    data = await request.form()
    form = {
        "email": str(data.get("email") or ""),
        "first_name": str(data.get("first_name") or ""),
        "last_name": str(data.get("last_name") or ""),
        "password": str(data.get("password") or ""),
    }
    try:
        await create_user(
            db,
            email=form["email"],
            password=form["password"],
            first_name=form["first_name"],
            last_name=form["last_name"],
            role=UserRole.child,
            parent_id=user.id,
        )
        await db.commit()
    except UserServiceError as exc:
        await db.rollback()
        return templates.TemplateResponse(
            request,
            "child_form.html",
            {
                "user": user,
                "title": "Add child",
                "child": None,
                "error": exc.message,
                "form": form,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse("/children", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/children/{child_id}/edit", response_class=HTMLResponse)
async def children_edit_form(
    request: Request,
    child_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
):
    child = await get_child_for_parent(db, user.id, child_id)
    if child is None:
        return RedirectResponse("/children", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request,
        "child_form.html",
        {
            "user": user,
            "title": f"Edit {child.display_name}",
            "child": child,
            "error": None,
            "form": {
                "email": child.email,
                "first_name": child.first_name,
                "last_name": child.last_name,
                "password": "",
            },
        },
    )


@router.post("/children/{child_id}/edit", response_model=None)
async def children_edit(
    request: Request,
    child_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
):
    child = await get_child_for_parent(db, user.id, child_id)
    if child is None:
        return RedirectResponse("/children", status_code=status.HTTP_303_SEE_OTHER)
    data = await request.form()
    form = {
        "email": str(data.get("email") or ""),
        "first_name": str(data.get("first_name") or ""),
        "last_name": str(data.get("last_name") or ""),
        "password": str(data.get("password") or ""),
    }
    try:
        await update_user_profile(
            db,
            child,
            email=form["email"],
            first_name=form["first_name"],
            last_name=form["last_name"],
            password=form["password"] or None,
        )
        await db.commit()
    except UserServiceError as exc:
        await db.rollback()
        return templates.TemplateResponse(
            request,
            "child_form.html",
            {
                "user": user,
                "title": f"Edit {child.display_name}",
                "child": child,
                "error": exc.message,
                "form": form,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse("/children", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/children/{child_id}/deactivate", response_model=None)
async def children_deactivate(
    child_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
):
    child = await get_child_for_parent(db, user.id, child_id)
    if child is not None:
        child.is_active = False
        await db.commit()
    return RedirectResponse("/children", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/children/{child_id}/activate", response_model=None)
async def children_activate(
    child_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
):
    child = await get_child_for_parent(db, user.id, child_id)
    if child is not None:
        child.is_active = True
        await db.commit()
    return RedirectResponse("/children", status_code=status.HTTP_303_SEE_OTHER)

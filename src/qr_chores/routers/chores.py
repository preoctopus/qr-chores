"""Parent chore management and QR views."""

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.auth.deps import require_role
from qr_chores.config import Settings, get_settings
from qr_chores.db import get_db
from qr_chores.models.chore import Chore, PhotoPolicy
from qr_chores.models.user import User, UserRole
from qr_chores.services.chores import (
    DAY_LABELS,
    count_completions,
    delete_chore,
    list_all_chores,
    parse_due_time,
    parse_schedule_days,
    schedule_labels,
)
from qr_chores.services.qr import chore_url, generate_qr_png, new_qr_token
from qr_chores.services.timeutil import format_due_time
from qr_chores.templating import templates

router = APIRouter(tags=["chores"])


def _form_context(
    *,
    chore: Chore | None = None,
    error: str | None = None,
    form: dict | None = None,
) -> dict:
    form = form or {}
    if chore and not form:
        form = {
            "title": chore.title,
            "description": chore.description or "",
            "due_time": chore.due_time.strftime("%H:%M"),
            "base_points": str(chore.base_points),
            "photo_policy": chore.photo_policy.value,
            "schedule_days": list(chore.schedule_days),
        }
    return {
        "chore": chore,
        "error": error,
        "form": form,
        "day_labels": DAY_LABELS,
        "photo_policies": list(PhotoPolicy),
        "schedule_labels": schedule_labels,
        "format_due_time": format_due_time,
    }


@router.get("/chores", response_class=HTMLResponse)
async def chores_list(
    request: Request,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    chores = await list_all_chores(db)
    return templates.TemplateResponse(
        request,
        "chores_list.html",
        {
            "user": user,
            "title": "Chores",
            "chores": chores,
            "format_due_time": format_due_time,
            "schedule_labels": schedule_labels,
        },
    )


@router.get("/chores/new", response_class=HTMLResponse)
async def chores_new_form(
    request: Request,
    user: User = Depends(require_role(UserRole.parent)),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "chore_form.html",
        {
            "user": user,
            "title": "New chore",
            **_form_context(
                form={
                    "title": "",
                    "description": "",
                    "due_time": "20:00",
                    "base_points": "10",
                    "photo_policy": PhotoPolicy.none.value,
                    "schedule_days": list("0123456"),
                }
            ),
        },
    )


@router.post("/chores", response_model=None)
async def chores_create(
    request: Request,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
):
    data = await request.form()
    title = str(data.get("title") or "")
    description = str(data.get("description") or "")
    due_time = str(data.get("due_time") or "")
    photo_policy = str(data.get("photo_policy") or "none")
    schedule_day = [str(v) for v in data.getlist("schedule_day")]
    try:
        base_points = int(str(data.get("base_points") or "10"))
    except ValueError:
        base_points = 10

    form = {
        "title": title,
        "description": description,
        "due_time": due_time,
        "base_points": str(base_points),
        "photo_policy": photo_policy,
        "schedule_days": schedule_day,
    }
    title = title.strip()
    if not title:
        return templates.TemplateResponse(
            request,
            "chore_form.html",
            {
                "user": user,
                "title": "New chore",
                **_form_context(error="Title is required.", form=form),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        due = parse_due_time(due_time)
        policy = PhotoPolicy(photo_policy)
    except (ValueError, KeyError):
        return templates.TemplateResponse(
            request,
            "chore_form.html",
            {
                "user": user,
                "title": "New chore",
                **_form_context(error="Invalid due time or photo policy.", form=form),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    chore = Chore(
        title=title,
        description=description.strip() or None,
        qr_token=new_qr_token(),
        due_time=due,
        schedule_days=parse_schedule_days(schedule_day),
        photo_policy=policy,
        base_points=max(0, base_points),
        is_active=True,
    )
    db.add(chore)
    await db.commit()
    await db.refresh(chore)
    return RedirectResponse(f"/chores/{chore.id}/qr", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/chores/{chore_id}/edit", response_class=HTMLResponse)
async def chores_edit_form(
    request: Request,
    chore_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
):
    chore = await db.get(Chore, chore_id)
    if chore is None:
        return RedirectResponse("/chores", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request,
        "chore_form.html",
        {
            "user": user,
            "title": f"Edit {chore.title}",
            **_form_context(chore=chore),
        },
    )


@router.post("/chores/{chore_id}/edit", response_model=None)
async def chores_edit(
    request: Request,
    chore_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
):
    chore = await db.get(Chore, chore_id)
    if chore is None:
        return RedirectResponse("/chores", status_code=status.HTTP_303_SEE_OTHER)

    data = await request.form()
    title = str(data.get("title") or "")
    description = str(data.get("description") or "")
    due_time = str(data.get("due_time") or "")
    photo_policy = str(data.get("photo_policy") or "none")
    schedule_day = [str(v) for v in data.getlist("schedule_day")]
    try:
        base_points = int(str(data.get("base_points") or "10"))
    except ValueError:
        base_points = 10

    form = {
        "title": title,
        "description": description,
        "due_time": due_time,
        "base_points": str(base_points),
        "photo_policy": photo_policy,
        "schedule_days": schedule_day,
    }
    title = title.strip()
    if not title:
        return templates.TemplateResponse(
            request,
            "chore_form.html",
            {
                "user": user,
                "title": "Edit chore",
                **_form_context(chore=chore, error="Title is required.", form=form),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        due = parse_due_time(due_time)
        policy = PhotoPolicy(photo_policy)
    except (ValueError, KeyError):
        return templates.TemplateResponse(
            request,
            "chore_form.html",
            {
                "user": user,
                "title": f"Edit {chore.title}",
                **_form_context(chore=chore, error="Invalid due time or photo policy.", form=form),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    chore.title = title
    chore.description = description.strip() or None
    chore.due_time = due
    chore.schedule_days = parse_schedule_days(schedule_day)
    chore.photo_policy = policy
    chore.base_points = max(0, base_points)
    await db.commit()
    return RedirectResponse("/chores", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/chores/{chore_id}/deactivate", response_model=None)
async def chores_deactivate(
    chore_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
):
    chore = await db.get(Chore, chore_id)
    if chore is not None:
        chore.is_active = False
        await db.commit()
    return RedirectResponse("/chores", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/chores/{chore_id}/activate", response_model=None)
async def chores_activate(
    chore_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
):
    chore = await db.get(Chore, chore_id)
    if chore is not None:
        chore.is_active = True
        await db.commit()
    return RedirectResponse("/chores", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/chores/{chore_id}/delete", response_class=HTMLResponse)
async def chores_delete_confirm(
    request: Request,
    chore_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
):
    chore = await db.get(Chore, chore_id)
    if chore is None:
        return RedirectResponse("/chores", status_code=status.HTTP_303_SEE_OTHER)
    completion_count = await count_completions(db, chore.id)
    return templates.TemplateResponse(
        request,
        "chore_delete.html",
        {
            "user": user,
            "title": f"Delete {chore.title}",
            "chore": chore,
            "completion_count": completion_count,
            "format_due_time": format_due_time,
        },
    )


@router.post("/chores/{chore_id}/delete", response_model=None)
async def chores_delete(
    chore_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
):
    chore = await db.get(Chore, chore_id)
    if chore is not None:
        await delete_chore(db, chore)
    return RedirectResponse("/chores", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/chores/{chore_id}/qr", response_class=HTMLResponse)
async def chore_qr_page(
    request: Request,
    chore_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    chore = await db.get(Chore, chore_id)
    if chore is None:
        return RedirectResponse("/chores", status_code=status.HTTP_303_SEE_OTHER)
    url = chore_url(settings, chore.qr_token)
    return templates.TemplateResponse(
        request,
        "chore_qr.html",
        {
            "user": user,
            "title": f"QR · {chore.title}",
            "chore": chore,
            "qr_url": url,
            "format_due_time": format_due_time,
        },
    )


@router.get("/chores/{chore_id}/qr.png")
async def chore_qr_png(
    chore_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    chore = await db.get(Chore, chore_id)
    if chore is None:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    png = generate_qr_png(chore_url(settings, chore.qr_token))
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Content-Disposition": f'inline; filename="chore-{chore.id}-qr.png"',
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get("/print/qrs", response_class=HTMLResponse)
async def print_qrs(
    request: Request,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    result = await db.execute(
        select(Chore).where(Chore.is_active.is_(True)).order_by(Chore.title)
    )
    chores = list(result.scalars().all())
    items = [
        {
            "chore": c,
            "url": chore_url(settings, c.qr_token),
            "png_path": f"/chores/{c.id}/qr.png",
        }
        for c in chores
    ]
    return templates.TemplateResponse(
        request,
        "print_qrs.html",
        {
            "user": user,
            "title": "Print QR codes",
            "items": items,
            "format_due_time": format_due_time,
        },
    )

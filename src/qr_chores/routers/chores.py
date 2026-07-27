"""Parent chore management and QR views."""

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
from qr_chores.services.qr import (
    chore_url,
    generate_qr_png,
    get_base_url_from_request,
    new_qr_token,
)
from qr_chores.services.timeutil import format_due_time
from qr_chores.services.users import get_child_for_parent, list_children_for_parent
from qr_chores.templating import templates

router = APIRouter(tags=["chores"])


def _form_context(
    *,
    chore: Chore | None = None,
    error: str | None = None,
    form: dict | None = None,
    children: list[User] | None = None,
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
            "assignee_user_id": str(chore.assignee_user_id or ""),
        }
    return {
        "chore": chore,
        "error": error,
        "form": form,
        "children": children or [],
        "day_labels": DAY_LABELS,
        "photo_policies": list(PhotoPolicy),
        "schedule_labels": schedule_labels,
        "format_due_time": format_due_time,
    }


async def _parent_chore(db: AsyncSession, parent: User, chore_id: int) -> Chore | None:
    result = await db.execute(
        select(Chore).options(selectinload(Chore.assignee)).where(Chore.id == chore_id)
    )
    chore = result.scalar_one_or_none()
    if chore is None or chore.assignee_user_id is None:
        return None
    child = await get_child_for_parent(db, parent.id, chore.assignee_user_id)
    if child is None:
        return None
    return chore


@router.get("/chores", response_class=HTMLResponse)
async def chores_list(
    request: Request,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    chores = await list_all_chores(db, parent_id=user.id)
    # Load assignees for list labels
    result = await db.execute(
        select(Chore)
        .options(selectinload(Chore.assignee))
        .where(Chore.id.in_([c.id for c in chores] or [-1]))
        .order_by(Chore.is_active.desc(), Chore.due_time, Chore.title)
    )
    chores = list(result.scalars().all())
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
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    kids = await list_children_for_parent(db, user.id, include_inactive=False)
    return templates.TemplateResponse(
        request,
        "chore_form.html",
        {
            "user": user,
            "title": "New chore",
            **_form_context(
                children=kids,
                form={
                    "title": "",
                    "description": "",
                    "due_time": "20:00",
                    "base_points": "10",
                    "photo_policy": PhotoPolicy.none.value,
                    "schedule_days": list("0123456"),
                    "assignee_user_id": str(kids[0].id) if kids else "",
                },
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
    kids = await list_children_for_parent(db, user.id, include_inactive=False)
    title = str(data.get("title") or "")
    description = str(data.get("description") or "")
    due_time = str(data.get("due_time") or "")
    photo_policy = str(data.get("photo_policy") or "none")
    schedule_day = [str(v) for v in data.getlist("schedule_day")]
    assignee_raw = str(data.get("assignee_user_id") or "")
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
        "assignee_user_id": assignee_raw,
    }
    title = title.strip()
    if not title:
        return templates.TemplateResponse(
            request,
            "chore_form.html",
            {
                "user": user,
                "title": "New chore",
                **_form_context(error="Title is required.", form=form, children=kids),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        due = parse_due_time(due_time)
        policy = PhotoPolicy(photo_policy)
        assignee_id = int(assignee_raw)
    except (ValueError, KeyError):
        return templates.TemplateResponse(
            request,
            "chore_form.html",
            {
                "user": user,
                "title": "New chore",
                **_form_context(
                    error="Invalid due time, photo policy, or assignee.",
                    form=form,
                    children=kids,
                ),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    child = await get_child_for_parent(db, user.id, assignee_id)
    if child is None or not child.is_active:
        return templates.TemplateResponse(
            request,
            "chore_form.html",
            {
                "user": user,
                "title": "New chore",
                **_form_context(
                    error="Pick one of your active children.",
                    form=form,
                    children=kids,
                ),
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
        assignee_user_id=child.id,
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
    chore = await _parent_chore(db, user, chore_id)
    if chore is None:
        return RedirectResponse("/chores", status_code=status.HTTP_303_SEE_OTHER)
    kids = await list_children_for_parent(db, user.id, include_inactive=False)
    return templates.TemplateResponse(
        request,
        "chore_form.html",
        {
            "user": user,
            "title": f"Edit {chore.title}",
            **_form_context(chore=chore, children=kids),
        },
    )


@router.post("/chores/{chore_id}/edit", response_model=None)
async def chores_edit(
    request: Request,
    chore_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
):
    chore = await _parent_chore(db, user, chore_id)
    if chore is None:
        return RedirectResponse("/chores", status_code=status.HTTP_303_SEE_OTHER)
    kids = await list_children_for_parent(db, user.id, include_inactive=False)

    data = await request.form()
    title = str(data.get("title") or "")
    description = str(data.get("description") or "")
    due_time = str(data.get("due_time") or "")
    photo_policy = str(data.get("photo_policy") or "none")
    schedule_day = [str(v) for v in data.getlist("schedule_day")]
    assignee_raw = str(data.get("assignee_user_id") or "")
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
        "assignee_user_id": assignee_raw,
    }
    title = title.strip()
    if not title:
        return templates.TemplateResponse(
            request,
            "chore_form.html",
            {
                "user": user,
                "title": "Edit chore",
                **_form_context(chore=chore, error="Title is required.", form=form, children=kids),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        due = parse_due_time(due_time)
        policy = PhotoPolicy(photo_policy)
        assignee_id = int(assignee_raw)
    except (ValueError, KeyError):
        return templates.TemplateResponse(
            request,
            "chore_form.html",
            {
                "user": user,
                "title": f"Edit {chore.title}",
                **_form_context(
                    chore=chore,
                    error="Invalid due time, photo policy, or assignee.",
                    form=form,
                    children=kids,
                ),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    child = await get_child_for_parent(db, user.id, assignee_id)
    if child is None or not child.is_active:
        return templates.TemplateResponse(
            request,
            "chore_form.html",
            {
                "user": user,
                "title": f"Edit {chore.title}",
                **_form_context(
                    chore=chore,
                    error="Pick one of your active children.",
                    form=form,
                    children=kids,
                ),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    chore.title = title
    chore.description = description.strip() or None
    chore.due_time = due
    chore.schedule_days = parse_schedule_days(schedule_day)
    chore.photo_policy = policy
    chore.base_points = max(0, base_points)
    chore.assignee_user_id = child.id
    await db.commit()
    return RedirectResponse("/chores", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/chores/{chore_id}/deactivate", response_model=None)
async def chores_deactivate(
    chore_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
):
    chore = await _parent_chore(db, user, chore_id)
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
    chore = await _parent_chore(db, user, chore_id)
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
    chore = await _parent_chore(db, user, chore_id)
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
    settings: Settings = Depends(get_settings),
):
    chore = await _parent_chore(db, user, chore_id)
    if chore is not None:
        await delete_chore(db, chore, settings=settings)
    return RedirectResponse("/chores", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/chores/{chore_id}/qr", response_class=HTMLResponse)
async def chore_qr_page(
    request: Request,
    chore_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    chore = await _parent_chore(db, user, chore_id)
    if chore is None:
        return RedirectResponse("/chores", status_code=status.HTTP_303_SEE_OTHER)
    url = chore_url(settings, chore.qr_token, request=request)
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
    request: Request,
    chore_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    chore = await _parent_chore(db, user, chore_id)
    if chore is None:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    png = generate_qr_png(chore_url(settings, chore.qr_token, request=request))
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
    chores = await list_all_chores(db, include_inactive=False, parent_id=user.id)
    items = [
        {
            "chore": c,
            "url": chore_url(settings, c.qr_token, request=request),
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
            "base_url": get_base_url_from_request(settings, request),
        },
    )

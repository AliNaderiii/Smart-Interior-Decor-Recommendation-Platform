"""Designer B2B2C: projects, share links (signed token), public share view.

Stage 03 hardening (probe `R-01`, `T-19`):
  * ``GET /share/{token}`` is rate limited per IP. It is the only
    unauthenticated endpoint that returns tenant data *and* runs a
    recommendation, so it was simultaneously a scraping surface, a token
    brute-force surface and an unmetered compute surface.
  * share creation is audited, and the emailed link is HTML-escaped.

Stage 1 (T-1.1):
  * ``POST /projects`` enforces the designer project quota from the versioned
    plans dataset (client spec: "subscription required to create new
    projects") — see ``app/services/designer_quota.py``.
"""
from __future__ import annotations

import html
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_designer
from app.core.config import settings
from app.core.rate_limit import enforce_rate_limit
from app.db.session import get_db
from app.models import audit_log as actions
from app.models.base import utcnow
from app.models.project import Project, ShareLink
from app.models.quiz import StyleQuiz
from app.models.user import User
from app.schemas.common import ok
from app.schemas.sanitize import SafeText
from app.services import audit
from app.services.designer_quota import create_designer_project
from app.services.emailer import send_email
from app.services.recommender import recommend

router = APIRouter(tags=["projects"])


class ProjectIn(BaseModel):
    # V2 (A04): extra="forbid" — this model is splatted into Project(**dump),
    # so unknown keys must be rejected, not silently dropped.
    model_config = ConfigDict(extra="forbid")

    name: SafeText(max_length=200, min_length=1)
    client_name: SafeText(max_length=200) = ""
    client_email: SafeText(max_length=255) = ""
    notes: SafeText(max_length=2000) = ""


class ShareIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quiz_id: str = Field(min_length=1, max_length=32)
    send_to_email: EmailStr | None = None
    expires_days: int = Field(default=30, ge=1, le=365)


def _project_out(p: Project, quiz_count: int = 0) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "client_name": p.client_name,
        "client_email": p.client_email,
        "notes": p.notes,
        "created_at": p.created_at.isoformat(),
        "quiz_count": quiz_count,
    }


@router.get("/projects")
def list_projects(user: User = Depends(require_designer), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Project).where(Project.designer_id == user.id).order_by(Project.created_at.desc())
    ).all()
    return ok([_project_out(p, len(p.quizzes)) for p in rows])


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectIn, user: User = Depends(require_designer), db: Session = Depends(get_db)):
    # Stage 1 (T-1.1): client spec — "subscription required to create new
    # projects". The quota comes from the versioned plans dataset; the
    # designer path is race-safe (row lock + conditional insert — see
    # app/services/designer_quota.py). Non-designers (admins) have no quota.
    project = create_designer_project(db, user, body.model_dump())
    if project is None:
        project = Project(designer_id=user.id, **body.model_dump())
        db.add(project)
        db.commit()
    return ok(_project_out(project))


@router.get("/projects/{project_id}")
def get_project(project_id: str, user: User = Depends(require_designer), db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None or project.designer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    quizzes = [
        {"id": q.id, "client_name": q.client_name, "styles": q.styles,
         "created_at": q.created_at.isoformat()}
        for q in project.quizzes
    ]
    return ok({**_project_out(project, len(quizzes)), "quizzes": quizzes})


@router.delete("/projects/{project_id}")
def delete_project(
    project_id: str,
    request: Request,
    user: User = Depends(require_designer),
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if project is None or project.designer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    db.delete(project)
    db.commit()
    audit.record(
        db, actions.ACTION_PROJECT_DELETE, user_id=user.id,
        detail=f"project={project_id}", request=request,
    )
    return ok({"message": "deleted"})


@router.post("/projects/{project_id}/share", status_code=status.HTTP_201_CREATED)
def share_project(
    project_id: str,
    body: ShareIn,
    request: Request,
    user: User = Depends(require_designer),
    db: Session = Depends(get_db),
):
    """Generate a signed public link (and optionally email it to the client)."""
    project = db.get(Project, project_id)
    if project is None or project.designer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    quiz = db.get(StyleQuiz, body.quiz_id)
    if quiz is None or quiz.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz not found")

    link = ShareLink(
        token=secrets.token_urlsafe(32),
        quiz_id=quiz.id,
        created_by=user.id,
        expires_at=utcnow() + timedelta(days=body.expires_days),
    )
    db.add(link)
    db.commit()

    share_url = f"/share/{link.token}"
    if body.send_to_email:
        # `full_name` is SafeText-stripped on the way in, but this string is
        # interpolated into an HTML email body — escape at the point of use so
        # the guarantee does not depend on a validator three modules away.
        sender = html.escape(user.full_name or "Your designer")
        send_email(
            str(body.send_to_email),
            f"{sender} shared decor recommendations with you",
            f'<p>View your personalized living room plan: '
            f'<a href="{html.escape(share_url)}">Open</a></p>',
        )
    audit.record(
        db, actions.ACTION_SHARE_CREATE, user_id=user.id,
        detail=f"project={project.id} quiz={quiz.id} expires_days={body.expires_days}"
               f" emailed={bool(body.send_to_email)}",
        request=request,
    )
    return ok({"token": link.token, "share_url": share_url, "expires_at": link.expires_at.isoformat()})


@router.get("/share/{token}")
def public_share_view(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Public, read-only recommendations for a shared quiz. No auth."""
    # R-01: unauthenticated, returns another tenant's data, and each miss costs
    # a database round trip while each hit costs a full recommendation. The
    # 256-bit token makes guessing infeasible; the limit makes *trying*
    # expensive and caps scraping of links that leaked through a mail client.
    enforce_rate_limit(
        f"share:{audit.client_ip(request)}",
        limit=settings.SHARE_RATE_LIMIT_PER_MINUTE,
    )
    if len(token) > 128:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share link not found")
    link = db.scalar(select(ShareLink).where(ShareLink.token == token))
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share link not found")
    if link.expires_at is not None:
        exp = link.expires_at
        if exp.tzinfo is None:
            from datetime import timezone

            exp = exp.replace(tzinfo=timezone.utc)
        if exp < utcnow():
            raise HTTPException(status.HTTP_410_GONE, "Share link expired")
    quiz = db.get(StyleQuiz, link.quiz_id)
    if quiz is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz deleted")
    payload = {
        "styles": quiz.styles,
        "color_palette": quiz.color_palette,
        "budget_min_toman": quiz.budget_min_toman,
        "budget_max_toman": quiz.budget_max_toman,
        "materials": quiz.materials,
        "patterns": quiz.patterns,
        "quiz_embedding": list(quiz.quiz_embedding) if quiz.quiz_embedding is not None else None,
    }
    result = recommend(db, payload)
    return ok({
        "client_name": quiz.client_name,
        "quiz": {"styles": quiz.styles, "color_palette": quiz.color_palette,
                 "room_width_cm": quiz.room_width_cm, "room_length_cm": quiz.room_length_cm},
        **result,
    })

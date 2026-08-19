"""Designer B2B2C: projects, share links (signed token), public share view."""
from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_designer
from app.db.session import get_db
from app.models.base import utcnow
from app.models.project import Project, ShareLink
from app.models.quiz import StyleQuiz
from app.models.user import User
from app.schemas.common import ok
from app.services.emailer import send_email
from app.services.recommender import recommend

router = APIRouter(tags=["projects"])


class ProjectIn(BaseModel):
    name: str
    client_name: str = ""
    client_email: str = ""
    notes: str = ""


class ShareIn(BaseModel):
    quiz_id: str
    send_to_email: EmailStr | None = None
    expires_days: int = 30


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
def delete_project(project_id: str, user: User = Depends(require_designer), db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None or project.designer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    db.delete(project)
    db.commit()
    return ok({"message": "deleted"})


@router.post("/projects/{project_id}/share", status_code=status.HTTP_201_CREATED)
def share_project(
    project_id: str,
    body: ShareIn,
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
        send_email(
            str(body.send_to_email),
            f"{user.full_name or 'Your designer'} shared decor recommendations with you",
            f'<p>View your personalized living room plan: <a href="{share_url}">Open</a></p>',
        )
    return ok({"token": link.token, "share_url": share_url, "expires_at": link.expires_at.isoformat()})


@router.get("/share/{token}")
def public_share_view(token: str, db: Session = Depends(get_db)):
    """Public, read-only recommendations for a shared quiz. No auth."""
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

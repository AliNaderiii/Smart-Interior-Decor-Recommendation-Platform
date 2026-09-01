"""Quiz CRUD + POST /recommend."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.embedding_service import get_embedding, quiz_to_text
from app.api.deps import get_current_user
from app.core.datasets import recommendation_limit
from app.core.rate_limit import enforce_rate_limit
from app.db.session import get_db
from app.models.project import Project
from app.models.quiz import StyleQuiz
from app.models.user import User
from app.schemas.common import ok
from app.schemas.quiz import QuizIn
from app.services.recommender import recommend

router = APIRouter(tags=["quiz"])


def _quiz_out(q: StyleQuiz) -> dict:
    return {
        "id": q.id,
        "user_id": q.user_id,
        "project_id": q.project_id,
        "client_name": q.client_name,
        "styles": q.styles,
        "color_palette": q.color_palette,
        "room_width_cm": q.room_width_cm,
        "room_length_cm": q.room_length_cm,
        "budget_min_toman": q.budget_min_toman,
        "budget_max_toman": q.budget_max_toman,
        "materials": q.materials,
        "patterns": q.patterns,
    }


def _quiz_dict(q: StyleQuiz) -> dict:
    return {
        "styles": q.styles,
        "color_palette": q.color_palette,
        "budget_min_toman": q.budget_min_toman,
        "budget_max_toman": q.budget_max_toman,
        "materials": q.materials,
        "patterns": q.patterns,
        "quiz_embedding": list(q.quiz_embedding) if q.quiz_embedding is not None else None,
    }


@router.post("/quiz", status_code=status.HTTP_201_CREATED)
def create_quiz(body: QuizIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.project_id:
        project = db.get(Project, body.project_id)
        if project is None or project.designer_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    quiz = StyleQuiz(
        user_id=user.id,
        project_id=body.project_id,
        client_name=body.client_name,
        styles=body.styles,
        color_palette=body.color_palette,
        room_width_cm=body.room_width_cm,
        room_length_cm=body.room_length_cm,
        budget_min_toman=body.budget_min_toman,
        budget_max_toman=body.budget_max_toman,
        materials=body.materials,
        patterns=body.patterns,
    )
    quiz.quiz_embedding = get_embedding(
        quiz_to_text(body.styles, body.color_palette, body.materials, body.patterns)
    )
    db.add(quiz)
    db.commit()
    return ok(_quiz_out(quiz))


@router.get("/quiz")
def list_quizzes(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(StyleQuiz).where(StyleQuiz.user_id == user.id).order_by(StyleQuiz.created_at.desc())
    ).all()
    return ok([_quiz_out(q) for q in rows])


@router.get("/quiz/{quiz_id}")
def get_quiz(quiz_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    quiz = db.get(StyleQuiz, quiz_id)
    if quiz is None or quiz.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz not found")
    return ok(_quiz_out(quiz))


@router.post("/recommend")
def recommend_endpoint(
    body: QuizIn | None = None,
    quiz_id: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get ranked recommendations either from a saved quiz or an inline payload.

    Rate-limited to 20 req/min per user — each cold call costs an embedding +
    vector search (AI cost control; cached hits are cheap but still counted).
    """
    enforce_rate_limit(f"recommend:{user.id}")
    if quiz_id:
        quiz = db.get(StyleQuiz, quiz_id)
        if quiz is None or quiz.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz not found")
        payload = _quiz_dict(quiz)
    elif body is not None:
        payload = body.model_dump(exclude={"project_id", "client_name"})
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "quiz_id or body required")

    result = recommend(db, payload, user_id=str(user.id))

    # Paywall: free users see full data for the top product per category,
    # remaining items are stripped to teaser fields (server-side enforcement).
    sub = user.subscription
    is_pro = bool(sub and sub.is_active)
    if not is_pro:
        visible_limit = recommendation_limit("homeowner_free")
        for cat, items in result["categories"].items():
            teasers = []
            for i, item in enumerate(items):
                if i < visible_limit:
                    teasers.append(item)
                else:
                    teasers.append({
                        "id": item["id"],
                        "title": item["title"],
                        "category": item["category"],
                        "image_url": item["image_url"],
                        "locked": True,
                    })
            result["categories"][cat] = teasers
    result["is_pro"] = is_pro
    return ok(result)

"""Product CRUD (admin) with S3 upload + AI extraction + link validation."""
from __future__ import annotations

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai.embedding_service import get_embedding, product_to_text
from ai.feature_extractor import FeatureExtractor
from app.api.deps import require_admin
from app.core.storage import get_storage
from app.db.session import get_db
from app.models.product import Product
from app.models.user import User
from app.schemas.common import ok
from app.schemas.product import ProductIn, ProductUpdate
from app.services.link_checker import check_product_link

router = APIRouter(prefix="/products", tags=["products"])


def _reembed(product: Product) -> None:
    product.style_embedding = get_embedding(
        product_to_text(
            product.title, product.styles, product.colors,
            product.materials, product.description, product.patterns,
        )
    )


@router.get("")
def list_products(
    category: str | None = None,
    is_verified: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    stmt = select(Product)
    if category:
        stmt = stmt.where(Product.category == category)
    if is_verified is not None:
        stmt = stmt.where(Product.is_verified.is_(is_verified))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(
        stmt.order_by(Product.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    from app.schemas.product import ProductOut

    return ok({
        "items": [ProductOut.model_validate(p).model_dump() for p in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.post("", status_code=status.HTTP_201_CREATED)
def create_product(
    body: ProductIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    product = Product(**body.model_dump(), is_verified=False)
    _reembed(product)
    db.add(product)
    db.commit()
    if product.seller_link:
        background.add_task(check_product_link, product.id)
    from app.schemas.product import ProductOut

    return ok(ProductOut.model_validate(product).model_dump())


@router.post("/upload", status_code=status.HTTP_201_CREATED)
def upload_product_image(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Upload image to storage, run AI extraction, create an unverified draft."""
    data = file.file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Max 10MB")
    url = get_storage().upload_file(data, file.filename or "image.jpg", file.content_type)

    extraction = FeatureExtractor().extract(url if url.startswith("http") else file.filename or url)
    product = Product(
        title=extraction.get("description_for_embedding", "New product")[:250] or "New product",
        category="sofa",
        price_toman=1,
        image_url=url,
        colors=extraction["colors"],
        styles=extraction["style"],
        materials=extraction["material"],
        patterns=extraction["patterns"],
        description=extraction["description_for_embedding"],
        extraction_confidence=extraction["confidence"],
        extraction_raw=extraction,
        is_verified=False,
    )
    _reembed(product)
    db.add(product)
    db.commit()
    from app.schemas.product import ProductOut

    return ok({
        "product": ProductOut.model_validate(product).model_dump(),
        "extraction": extraction,
    })


@router.patch("/{product_id}")
def update_product(
    product_id: str,
    body: ProductUpdate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(product, key, value)
    if {"title", "styles", "colors", "materials", "description", "patterns"} & changes.keys():
        _reembed(product)
    db.commit()
    if "seller_link" in changes and product.seller_link:
        background.add_task(check_product_link, product.id)
    from app.schemas.product import ProductOut

    return ok(ProductOut.model_validate(product).model_dump())


@router.delete("/{product_id}")
def delete_product(product_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    db.delete(product)
    db.commit()
    return ok({"message": "deleted"})


@router.post("/{product_id}/verify")
def verify_product(product_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Human-in-the-loop: mark AI-extracted features as verified."""
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    product.is_verified = True
    db.commit()
    return ok({"id": product.id, "is_verified": True})

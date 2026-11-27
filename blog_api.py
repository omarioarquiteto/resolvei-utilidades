from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlparse

import bleach
from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/blog", tags=["blog"])

BLOG_ADMIN_UID = os.getenv("BLOG_ADMIN_UID", "").strip()
BLOG_ADMIN_EMAIL = os.getenv("BLOG_ADMIN_EMAIL", "").strip().lower()
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "").strip()
FIREBASE_STORAGE_BUCKET = os.getenv(
    "FIREBASE_STORAGE_BUCKET",
    f"{FIREBASE_PROJECT_ID}.firebasestorage.app" if FIREBASE_PROJECT_ID else "",
).strip()

MAX_IMAGE_BYTES = 8 * 1024 * 1024
IMAGE_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}
ALLOWED_TAGS = {
    "p", "br", "strong", "b", "em", "i", "u", "s",
    "h2", "h3", "h4", "ul", "ol", "li",
    "blockquote", "a", "img", "figure", "figcaption", "hr",
}
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
    "figure": ["class"],
}
ALLOWED_PROTOCOLS = {"http", "https", "mailto"}


class BlogPostInput(BaseModel):
    title: str = Field(min_length=3, max_length=140)
    slug: str = Field(min_length=3, max_length=120)
    category: str = Field(default="Outros produtos", max_length=60)
    excerpt: str = Field(default="", max_length=320)
    cover_image: str = Field(default="", alias="coverImage", max_length=2048)
    product_link: str = Field(default="", alias="productLink", max_length=2048)
    body_html: str = Field(default="", alias="bodyHtml", max_length=200000)
    tags: list[str] = Field(default_factory=list)
    seo_title: str = Field(default="", alias="seoTitle", max_length=160)
    seo_description: str = Field(default="", alias="seoDescription", max_length=240)
    status: str = Field(default="draft")

    class Config:
        allow_population_by_field_name = True


def _firebase_modules():
    try:
        import firebase_admin
        from firebase_admin import auth as firebase_auth
        from firebase_admin import firestore as firebase_firestore
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Firebase Admin não está disponível no servidor.") from exc
    if not firebase_admin._apps:
        raise HTTPException(status_code=503, detail="Firebase Admin não está configurado no Render.")
    return firebase_admin, firebase_auth, firebase_firestore


def _verify_user(authorization: str | None) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Faça login no Resolvei para continuar.")
    _, firebase_auth, _ = _firebase_modules()
    try:
        return firebase_auth.verify_id_token(authorization[7:].strip())
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Sessão Firebase inválida ou expirada.") from exc


def _is_admin(user: dict[str, Any]) -> bool:
    # Configure one identity only. When a UID is present it takes priority,
    # so an accidentally populated email variable cannot grant a second account.
    if BLOG_ADMIN_UID:
        return user.get("uid") == BLOG_ADMIN_UID
    email = str(user.get("email") or "").strip().lower()
    return bool(
        BLOG_ADMIN_EMAIL
        and email == BLOG_ADMIN_EMAIL
        and user.get("email_verified") is True
    )


def _require_admin(authorization: str | None) -> dict[str, Any]:
    if not BLOG_ADMIN_UID and not BLOG_ADMIN_EMAIL:
        raise HTTPException(
            status_code=503,
            detail="O editor ainda não foi habilitado. Configure BLOG_ADMIN_EMAIL ou BLOG_ADMIN_UID nas variáveis de ambiente do Render.",
        )
    user = _verify_user(authorization)
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Acesso restrito à conta administradora do Blog Resolvei.")
    return user


def _db():
    _, _, firebase_firestore = _firebase_modules()
    return firebase_firestore.client()


def _timestamp_iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _serialize_post(snapshot) -> dict[str, Any]:
    data = snapshot.to_dict() or {}
    for field in ("createdAt", "updatedAt", "publishedAt"):
        data[field] = _timestamp_iso(data.get(field))
    data["slug"] = snapshot.id
    return data


def _normalize_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return slug.strip("-")[:120]


def _clean_html(value: str) -> str:
    clean = bleach.clean(
        value or "",
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
        strip_comments=True,
    )
    return clean


def _validate_payload(req: BlogPostInput) -> dict[str, Any]:
    slug = _normalize_slug(req.slug)
    if len(slug) < 3:
        raise HTTPException(status_code=400, detail="O endereço do post precisa ter pelo menos 3 caracteres.")
    if req.status not in {"draft", "published"}:
        raise HTTPException(status_code=400, detail="Status de publicação inválido.")
    cover = req.cover_image.strip()
    if cover:
        parsed = urlparse(cover)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HTTPException(status_code=400, detail="A imagem de capa deve usar um endereço HTTP ou HTTPS.")
    product_link = req.product_link.strip()
    if product_link:
        parsed = urlparse(product_link)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HTTPException(status_code=400, detail="O link do produto deve usar um endereço HTTP ou HTTPS.")
    body = _clean_html(req.body_html)
    if not re.sub(r"<[^>]+>", "", body).strip():
        raise HTTPException(status_code=400, detail="Escreva o conteúdo do review antes de salvar.")
    tags = []
    for tag in req.tags[:20]:
        item = str(tag).strip()[:40]
        if item and item not in tags:
            tags.append(item)
    return {
        "title": req.title.strip(),
        "slug": slug,
        "category": req.category.strip() or "Outros produtos",
        "excerpt": req.excerpt.strip(),
        "coverImage": cover,
        "productLink": product_link,
        "bodyHtml": body,
        "tags": tags,
        "seoTitle": req.seo_title.strip(),
        "seoDescription": req.seo_description.strip(),
        "status": req.status,
    }


@router.get("/admin-status")
def blog_admin_status(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    configured = bool(BLOG_ADMIN_UID or BLOG_ADMIN_EMAIL)
    if not authorization:
        return {"configured": configured, "isAdmin": False}
    try:
        user = _verify_user(authorization)
    except HTTPException:
        return {"configured": configured, "isAdmin": False}
    return {"configured": configured, "isAdmin": _is_admin(user)}


@router.get("/posts")
def blog_public_posts() -> dict[str, Any]:
    if not BLOG_ADMIN_UID and not BLOG_ADMIN_EMAIL:
        # Public article reading remains enabled only after the blog's admin
        # account has been configured, preventing an unowned editorial space.
        return {"posts": []}
    try:
        docs = _db().collection("blogPosts").where("status", "==", "published").stream()
        posts = [_serialize_post(doc) for doc in docs]
        posts.sort(key=lambda post: post.get("publishedAt") or post.get("createdAt") or "", reverse=True)
        return {"posts": posts[:60]}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Não foi possível acessar as publicações do blog no Firestore.") from exc


@router.get("/posts/{slug}")
def blog_public_post(slug: str) -> dict[str, Any]:
    if not BLOG_ADMIN_UID and not BLOG_ADMIN_EMAIL:
        raise HTTPException(status_code=404, detail="Review não encontrado.")
    try:
        snapshot = _db().collection("blogPosts").document(slug).get()
        if not snapshot.exists:
            raise HTTPException(status_code=404, detail="Review não encontrado.")
        post = _serialize_post(snapshot)
        if post.get("status") != "published":
            raise HTTPException(status_code=404, detail="Review não encontrado.")
        return {"post": post}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Não foi possível carregar este review.") from exc


@router.get("/admin/posts")
def blog_admin_posts(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _require_admin(authorization)
    try:
        docs = _db().collection("blogPosts").stream()
        posts = [_serialize_post(doc) for doc in docs]
        posts.sort(key=lambda post: post.get("updatedAt") or post.get("createdAt") or "", reverse=True)
        return {"posts": posts}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Não foi possível carregar os posts no Firestore.") from exc


@router.post("/posts")
def blog_create_post(req: BlogPostInput, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _require_admin(authorization)
    data = _validate_payload(req)
    _, _, firebase_firestore = _firebase_modules()
    ref = firebase_firestore.client().collection("blogPosts").document(data["slug"])
    if ref.get().exists:
        raise HTTPException(status_code=409, detail="Já existe um post com esse endereço. Escolha outro slug.")
    now = firebase_firestore.SERVER_TIMESTAMP
    data.update({
        "createdAt": now,
        "updatedAt": now,
        "publishedAt": now if data["status"] == "published" else None,
    })
    ref.set(data)
    saved = ref.get()
    return {"ok": True, "post": _serialize_post(saved)}


@router.put("/posts/{slug}")
def blog_update_post(slug: str, req: BlogPostInput, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _require_admin(authorization)
    data = _validate_payload(req)
    _, _, firebase_firestore = _firebase_modules()
    collection = firebase_firestore.client().collection("blogPosts")
    old_ref = collection.document(slug)
    old_snapshot = old_ref.get()
    if not old_snapshot.exists:
        raise HTTPException(status_code=404, detail="Post não encontrado.")
    old_data = old_snapshot.to_dict() or {}
    new_ref = collection.document(data["slug"])
    if data["slug"] != slug and new_ref.get().exists:
        raise HTTPException(status_code=409, detail="Já existe outro post com esse endereço.")
    now = firebase_firestore.SERVER_TIMESTAMP
    was_published = old_data.get("status") == "published"
    data["createdAt"] = old_data.get("createdAt") or now
    data["updatedAt"] = now
    if data["status"] == "published":
        data["publishedAt"] = old_data.get("publishedAt") if was_published else now
    else:
        data["publishedAt"] = None
    new_ref.set(data)
    if data["slug"] != slug:
        old_ref.delete()
    return {"ok": True, "post": _serialize_post(new_ref.get())}


@router.delete("/posts/{slug}")
def blog_delete_post(slug: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _require_admin(authorization)
    ref = _db().collection("blogPosts").document(slug)
    snapshot = ref.get()
    if not snapshot.exists:
        raise HTTPException(status_code=404, detail="Post não encontrado.")
    ref.delete()
    return {"ok": True, "deleted": True}


@router.post("/upload")
async def blog_upload_image(
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_admin(authorization)
    content_type = (file.content_type or "").lower()
    extension = IMAGE_TYPES.get(content_type)
    if not extension:
        raise HTTPException(status_code=415, detail="Formato de imagem não suportado. Use JPG, PNG, WEBP ou GIF.")
    contents = await file.read(MAX_IMAGE_BYTES + 1)
    if len(contents) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="A imagem deve ter no máximo 8 MB.")
    if not contents:
        raise HTTPException(status_code=400, detail="O arquivo de imagem está vazio.")
    if not FIREBASE_STORAGE_BUCKET:
        raise HTTPException(status_code=503, detail="Configure FIREBASE_STORAGE_BUCKET nas variáveis do Render.")
    try:
        import firebase_admin
        from firebase_admin import storage as firebase_storage
        if not firebase_admin._apps:
            raise RuntimeError("Firebase Admin não está inicializado.")
        bucket = firebase_storage.bucket(FIREBASE_STORAGE_BUCKET)
        object_name = f"blog/{uuid.uuid4().hex}.{extension}"
        token = uuid.uuid4().hex
        blob = bucket.blob(object_name)
        blob.cache_control = "public, max-age=31536000, immutable"
        blob.metadata = {"firebaseStorageDownloadTokens": token}
        blob.upload_from_string(contents, content_type=content_type, if_generation_match=0)
        encoded_name = quote(object_name, safe="")
        url = f"https://firebasestorage.googleapis.com/v0/b/{bucket.name}/o/{encoded_name}?alt=media&token={token}"
        return {"ok": True, "url": url, "path": object_name}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Falha ao enviar a imagem. Verifique o bucket e as permissões de Storage da conta de serviço do Firebase.") from exc

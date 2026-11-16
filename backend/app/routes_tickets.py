import re
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import metrics
from .config import get_settings
from .db import get_db
from .logging_conf import security_event
from .models import Attachment, Comment, ExportJob, Ticket, User
from .schemas import AttachmentOut, CommentIn, CommentOut, ExportOut, TicketDetail, TicketIn, TicketOut, TicketPatch
from .security import current_user, require_staff
from .services import enqueue, get_queue, get_storage

router = APIRouter(prefix="/api", tags=["tickets"])

ALLOWED_TYPES = {"image/png", "image/jpeg", "application/pdf", "text/plain"}


def _is_staff(user: User) -> bool:
    return user.role in ("agent", "admin")


def _get_ticket(db: Session, ticket_id: int, user: User) -> Ticket:
    t = db.get(Ticket, ticket_id)
    # un utilisateur simple ne voit que ses tickets ; 404 plutôt que 403 pour ne rien révéler
    if t is None or (not _is_staff(user) and t.author_id != user.id):
        if t is not None:
            security_event("access_denied", user_id=user.id, ticket_id=ticket_id)
        raise HTTPException(404, "Ticket introuvable")
    return t


@router.get("/tickets", response_model=list[TicketOut])
def list_tickets(status: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = select(Ticket).order_by(Ticket.id.desc()).limit(200)
    if not _is_staff(user):
        q = q.where(Ticket.author_id == user.id)
    if status:
        q = q.where(Ticket.status == status)
    return db.scalars(q).all()


@router.post("/tickets", response_model=TicketOut, status_code=201)
def create_ticket(data: TicketIn, db: Session = Depends(get_db), user: User = Depends(current_user),
                  queue=Depends(get_queue)):
    t = Ticket(title=data.title, description=data.description, priority=data.priority, author_id=user.id)
    db.add(t)
    db.commit()
    metrics.TICKETS_CREATED.inc()
    # tâche de fond : notification par e-mail, traitée par le worker
    enqueue(queue, "tasks.notify_ticket_created", t.id)
    return t


@router.get("/tickets/{ticket_id}", response_model=TicketDetail)
def get_ticket(ticket_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _get_ticket(db, ticket_id, user)


@router.patch("/tickets/{ticket_id}", response_model=TicketOut)
def patch_ticket(ticket_id: int, data: TicketPatch, db: Session = Depends(get_db),
                 user: User = Depends(require_staff), queue=Depends(get_queue)):
    t = _get_ticket(db, ticket_id, user)
    if data.status:
        t.status = data.status
    if data.priority:
        t.priority = data.priority
    assigned = False
    if data.assignee_id is not None and data.assignee_id != t.assignee_id:
        assignee = db.get(User, data.assignee_id)
        if assignee is None or not _is_staff(assignee):
            raise HTTPException(422, "L'assigné doit être un agent")
        t.assignee_id = assignee.id
        assigned = True
    db.commit()
    if assigned:
        enqueue(queue, "tasks.notify_ticket_assigned", t.id)
    return t


@router.post("/tickets/{ticket_id}/comments", response_model=CommentOut, status_code=201)
def add_comment(ticket_id: int, data: CommentIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = _get_ticket(db, ticket_id, user)
    c = Comment(ticket_id=t.id, author_id=user.id, body=data.body)
    db.add(c)
    db.commit()
    return c


@router.post("/tickets/{ticket_id}/attachments", response_model=AttachmentOut, status_code=201)
async def upload_attachment(ticket_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                            user: User = Depends(current_user), storage=Depends(get_storage)):
    s = get_settings()
    t = _get_ticket(db, ticket_id, user)
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, f"Type non autorisé ({file.content_type})")
    data = await file.read(s.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > s.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"Fichier trop gros (max {s.max_upload_mb} Mo)")
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", file.filename or "fichier")[:120]
    key = f"tickets/{t.id}/{uuid.uuid4().hex}_{safe}"
    storage.put(s.s3_bucket_attachments, key, data, file.content_type)
    att = Attachment(ticket_id=t.id, filename=safe, content_type=file.content_type, size=len(data),
                     object_key=key, uploaded_by=user.id)
    db.add(att)
    db.commit()
    metrics.UPLOADS.inc()
    return att


@router.get("/attachments/{att_id}")
def download_attachment(att_id: int, db: Session = Depends(get_db), user: User = Depends(current_user),
                        storage=Depends(get_storage)):
    att = db.get(Attachment, att_id)
    if att is None:
        raise HTTPException(404, "Pièce jointe introuvable")
    _get_ticket(db, att.ticket_id, user)  # même règle d'accès que pour le ticket
    data, ctype = storage.get(get_settings().s3_bucket_attachments, att.object_key)
    return Response(data, media_type=ctype,
                    headers={"Content-Disposition": f'attachment; filename="{att.filename}"'})


@router.post("/exports", response_model=ExportOut, status_code=202)
def request_export(db: Session = Depends(get_db), user: User = Depends(require_staff), queue=Depends(get_queue)):
    job = ExportJob(user_id=user.id)
    db.add(job)
    db.commit()
    enqueue(queue, "tasks.generate_export", job.id)
    return job


@router.get("/exports/{job_id}", response_model=ExportOut)
def get_export(job_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    job = db.get(ExportJob, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(404, "Export introuvable")
    return job


@router.get("/exports/{job_id}/download")
def download_export(job_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff),
                    storage=Depends(get_storage)):
    job = db.get(ExportJob, job_id)
    if job is None or job.user_id != user.id or job.status != "done":
        raise HTTPException(404, "Export indisponible")
    data, ctype = storage.get(get_settings().s3_bucket_exports, job.object_key)
    return Response(data, media_type=ctype,
                    headers={"Content-Disposition": f'attachment; filename="tickets_{job.id}.csv"'})

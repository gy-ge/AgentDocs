"""Task template CRUD endpoints under ``/api/task-templates``."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_api_key
from app.api.serializers import serialize_task_template
from app.db import get_db
from app.schemas.templates import TaskTemplateCreate, TaskTemplateUpdate
from app.services.template_service import TemplateService

router = APIRouter(prefix="/api/task-templates", tags=["task-templates"], dependencies=[Depends(require_api_key)])
service = TemplateService()


@router.get("")
def list_task_templates(db: Session = Depends(get_db)):
    templates = service.list_templates(db)
    return {
        "ok": True,
        "data": [serialize_task_template(template).model_dump(mode="json") for template in templates],
    }


@router.post("")
def create_task_template(payload: TaskTemplateCreate, db: Session = Depends(get_db)):
    template = service.create_template(
        db,
        name=payload.name,
        action=payload.action,
        instruction=payload.instruction,
    )
    return {"ok": True, "data": serialize_task_template(template).model_dump(mode="json")}


@router.put("/{template_id}")
def update_task_template(
    template_id: int, payload: TaskTemplateUpdate, db: Session = Depends(get_db)
):
    template = service.update_template(
        db,
        template_id,
        name=payload.name,
        action=payload.action,
        instruction=payload.instruction,
    )
    return {"ok": True, "data": serialize_task_template(template).model_dump(mode="json")}


@router.delete("/{template_id}")
def delete_task_template(template_id: int, db: Session = Depends(get_db)):
    service.delete_template(db, template_id)
    return {"ok": True, "data": {"id": template_id}}
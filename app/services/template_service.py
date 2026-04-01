from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import TaskTemplate
from app.time_utils import utcnow


class TemplateService:
    def list_templates(self, db: Session) -> list[TaskTemplate]:
        return (
            db.query(TaskTemplate)
            .order_by(TaskTemplate.updated_at.desc(), TaskTemplate.id.desc())
            .all()
        )

    def get_template(self, db: Session, template_id: int) -> TaskTemplate:
        template = db.get(TaskTemplate, template_id)
        if template is None:
            raise ApiError(404, "not_found", "task template not found")
        return template

    def create_template(
        self,
        db: Session,
        *,
        name: str,
        action: str,
        instruction: str,
    ) -> TaskTemplate:
        now = utcnow()
        template = TaskTemplate(
            name=name,
            action=action,
            instruction=instruction,
            created_at=now,
            updated_at=now,
        )
        db.add(template)
        db.commit()
        db.refresh(template)
        return template

    def update_template(
        self,
        db: Session,
        template_id: int,
        *,
        name: str,
        action: str,
        instruction: str,
    ) -> TaskTemplate:
        template = self.get_template(db, template_id)
        template.name = name
        template.action = action
        template.instruction = instruction
        template.updated_at = utcnow()
        db.commit()
        db.refresh(template)
        return template

    def delete_template(self, db: Session, template_id: int) -> None:
        template = self.get_template(db, template_id)
        db.delete(template)
        db.commit()
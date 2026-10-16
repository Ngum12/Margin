"""Local-only name recognition for spare sheets. Suggestions never assign a page."""

import io
from difflib import SequenceMatcher
from typing import Any

from PIL import Image
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.factory import ollama_client
from app.ai.ollama import resolve_model
from app.ai.prompts import load_prompt
from app.ai.types import ModelOutputInvalidError
from app.config import Settings
from app.db.models import Exam, IntakePage, Student
from app.services import audit


class NameRead(BaseModel):
    name: str = Field(max_length=200)


def identify_spare(
    factory: sessionmaker[Session], settings: Settings, payload: dict[str, Any]
) -> None:
    if settings.ai_backend == "mock":
        return  # No invented identity in demonstrations.
    with factory() as db:
        item = db.get(IntakePage, int(payload["intake_page_id"]))
        if (
            not item
            or item.page_id
            or item.discarded
            or item.identification_model
            or item.reason != "spare"
        ):
            return
        exam = db.get(Exam, item.exam_id)
        if exam is None:
            return
        with Image.open(settings.data_dir / item.image_path) as source:
            image = source.convert("RGB").rotate(-item.rotation, expand=True)
            header = image.crop((0, 0, image.width, round(image.height * 0.14)))
            header.thumbnail((1600, 400))
            buffer = io.BytesIO()
            header.save(buffer, "PNG")
        client = ollama_client(settings)
        model = resolve_model(client, settings.reader_model)
        prompt = load_prompt("spare_name")
        response = client.chat_json(
            model.name,
            prompt.render(),
            NameRead.model_json_schema(),
            images=[buffer.getvalue()],
        )
        try:
            name = NameRead.model_validate_json(response).name.strip().casefold()
        except ValidationError:
            raise ModelOutputInvalidError("invalid_name_output") from None
        students = list(db.scalars(select(Student).where(Student.class_id == exam.class_id)))
        ranked = sorted(
            (
                (SequenceMatcher(None, name, (s.display_name or "").casefold()).ratio(), s.id)
                for s in students
                if s.display_name and name
            ),
            reverse=True,
        )
        if (
            ranked
            and ranked[0][0] >= 0.7
            and (len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= 0.1)
        ):
            item.suggested_student_id = ranked[0][1]
        item.identification_model = f"{model.name}@{model.version}"[:100]
        audit.record(
            db,
            actor=None,
            entity_type="intake_page",
            entity_id=item.id,
            action="suggest_identity",
            new_value={
                "model": item.identification_model,
                "prompt_version": prompt.version,
                "suggested_student_id": item.suggested_student_id,
            },
        )
        db.commit()

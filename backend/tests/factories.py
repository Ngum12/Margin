"""Test data builders and API helpers."""

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.db.models import Role, School, SchoolClass, Student, User

PASSWORD = "correct-horse-battery"
# Hashing is deliberately slow; hash the shared test password once.
_PASSWORD_HASH = hash_password(PASSWORD)


@dataclass
class Factory:
    db: Session

    def school(self, curriculum: str = "cm_gce_ol") -> School:
        school = School(name="Test High School", country="Cameroon", curriculum=curriculum)
        self.db.add(school)
        self.db.commit()
        return school

    def user(
        self, school: School, username: str, role: Role = Role.TEACHER, *, active: bool = True
    ) -> User:
        user = User(
            school_id=school.id,
            username=username,
            display_name=username.title(),
            password_hash=_PASSWORD_HASH,
            role=role,
            is_active=active,
        )
        self.db.add(user)
        self.db.commit()
        return user

    def school_class(self, school: School, teacher: User, name: str = "Form 5A") -> SchoolClass:
        school_class = SchoolClass(
            school_id=school.id, name=name, academic_year="2026/2027", teacher_id=teacher.id
        )
        self.db.add(school_class)
        self.db.commit()
        return school_class

    def student(self, school_class: SchoolClass, code: str, name: str | None = None) -> Student:
        student = Student(
            school_id=school_class.school_id,
            class_id=school_class.id,
            code=code,
            display_name=name,
        )
        self.db.add(student)
        self.db.commit()
        return student


class ApiUser:
    """A signed-in browser: its own TestClient (cookie jar) plus the CSRF token."""

    def __init__(self, app: FastAPI, username: str, password: str = PASSWORD) -> None:
        self.client = TestClient(app)
        response = self.client.post(
            "/api/auth/login", json={"username": username, "password": password}
        )
        assert response.status_code == 200, response.text
        self.csrf: str = response.json()["csrf_token"]

    def get(self, url: str) -> Any:
        return self.client.get(url)

    def _send(self, method: str, url: str, json: Any = None, **kwargs: Any) -> Any:
        headers = {"X-CSRF-Token": self.csrf, **kwargs.pop("headers", {})}
        return self.client.request(method, url, json=json, headers=headers, **kwargs)

    def post(self, url: str, json: Any = None, **kwargs: Any) -> Any:
        return self._send("POST", url, json, **kwargs)

    def put(self, url: str, json: Any = None, **kwargs: Any) -> Any:
        return self._send("PUT", url, json, **kwargs)

    def patch(self, url: str, json: Any = None, **kwargs: Any) -> Any:
        return self._send("PATCH", url, json, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> Any:
        return self._send("DELETE", url, **kwargs)


def complete_scheme() -> dict[str, Any]:
    """A valid two-question mark scheme in API (whole-mark) form."""
    return {
        "questions": [
            {
                "label": "1(a)",
                "prompt_text": "State two properties of metals.",
                "max_marks": 2,
                "points": [
                    {
                        "description": "Conducts electricity",
                        "marks": 1,
                        "alternatives": ["conductor"],
                    },
                    {"description": "Malleable", "marks": 1},
                ],
            },
            {
                "label": "1(b)",
                "prompt_text": "Name the gas produced when zinc reacts with dilute acid.",
                "max_marks": 1,
                "points": [{"description": "Hydrogen (H_2)", "marks": 1}],
            },
        ]
    }

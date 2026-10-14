from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.errors import Issue
from app.services.mark_scheme_import import MAX_CSV_BYTES, decode_csv, parse_mark_scheme_csv
from tests.conftest import World
from tests.factories import ApiUser

HEADER = (
    "question_label,question_prompt,question_max_marks,point_description,point_marks,"
    "point_alternatives\n"
)
GOOD_CSV = (
    HEADER
    + "1(a),State two properties of metals,2,Conducts electricity,1,conductor|good conductor\n"
    + "1(a),State two properties of metals,2,Malleable,1,\n"
    + '1(b),"Name the gas, with formula",1,Hydrogen (H_2),1,\n'
)


def _codes(issues: list[Issue]) -> list[str]:
    return [i.code for i in issues]


def test_parses_questions_points_and_alternatives() -> None:
    result = parse_mark_scheme_csv(GOOD_CSV)

    assert result.issues == []
    assert result.scheme is not None
    q1, q2 = result.scheme.questions
    assert (q1.label, q1.max_marks, len(q1.points)) == ("1(a)", 2, 2)
    assert q1.points[0].alternatives == ["conductor", "good conductor"]
    assert q1.points[1].alternatives == []
    assert q2.prompt_text == "Name the gas, with formula"


def test_utf8_bom_and_header_case_are_tolerated() -> None:
    text = decode_csv(("﻿" + GOOD_CSV.replace("question_label", "Question_Label")).encode())

    assert isinstance(text, str)
    assert parse_mark_scheme_csv(text).scheme is not None


def test_alternatives_column_is_optional() -> None:
    csv_text = (
        "question_label,question_prompt,question_max_marks,point_description,point_marks\n"
        "1,Define demand,2,Quantity buyers are willing and able to buy,2\n"
    )

    assert parse_mark_scheme_csv(csv_text).scheme is not None


def test_french_text_survives() -> None:
    csv_text = HEADER + "1,Définissez l'offre,1,Quantité offerte à un prix donné,1,\n"

    result = parse_mark_scheme_csv(csv_text)

    assert result.scheme is not None
    assert result.scheme.questions[0].prompt_text == "Définissez l'offre"


def test_missing_columns_are_reported() -> None:
    result = parse_mark_scheme_csv("question_label,point_marks\n1,1\n")

    assert result.scheme is None
    assert _codes(result.issues) == ["import.missing_columns"]
    assert result.issues[0].params["columns"] == [
        "question_prompt",
        "question_max_marks",
        "point_description",
    ]


def test_non_numeric_marks_are_reported_per_row() -> None:
    csv_text = HEADER + "1,P,two,D,1,\n1,P,2,D,1.5,\n"

    result = parse_mark_scheme_csv(csv_text)

    assert result.scheme is None
    assert [(i.code, i.path) for i in result.issues] == [
        ("import.max_marks_not_number", ["row", 2]),
        ("import.point_marks_not_number", ["row", 3]),
    ]


def test_inconsistent_question_columns_are_reported() -> None:
    csv_text = HEADER + "1,Prompt,2,A,1,\n1,Prompt,3,B,1,\n"

    result = parse_mark_scheme_csv(csv_text)

    assert _codes(result.issues) == ["import.question_inconsistent"]
    assert result.issues[0].params == {"label": "1", "first_row": 2}


def test_question_rows_must_be_together() -> None:
    csv_text = HEADER + "1,P,1,A,1,\n2,P,1,B,1,\n1,P,1,C,1,\n"

    assert _codes(parse_mark_scheme_csv(csv_text).issues) == ["import.question_not_contiguous"]


def test_extra_cells_are_reported() -> None:
    csv_text = HEADER + "1,P,1,A,1,,surprise\n"

    assert _codes(parse_mark_scheme_csv(csv_text).issues) == ["import.row_extra_cells"]


def test_missing_label_is_reported() -> None:
    assert _codes(parse_mark_scheme_csv(HEADER + ",P,1,A,1,\n").issues) == ["import.label_required"]


def test_blank_rows_are_skipped_and_empty_file_reported() -> None:
    assert _codes(parse_mark_scheme_csv(HEADER + ",,,,,\n").issues) == ["import.empty"]


def test_oversized_and_non_utf8_input_is_refused() -> None:
    too_big = decode_csv(b"x" * (MAX_CSV_BYTES + 1))
    not_utf8 = decode_csv("é".encode("latin-1"))

    assert isinstance(too_big, Issue)
    assert too_big.code == "import.too_large"
    assert isinstance(not_utf8, Issue)
    assert not_utf8.code == "import.not_utf8"


def test_preview_endpoint_parses_and_validates(app: FastAPI, world: World) -> None:
    user = ApiUser(app, "alice")

    response = user.post(
        "/api/mark-scheme/import-preview",
        content=GOOD_CSV.encode(),
        headers={"Content-Type": "text/csv"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["issues"] == []
    assert len(body["scheme"]["questions"]) == 2
    assert body["validation"]["is_ready"] is True


def test_preview_reports_rule_problems_without_saving(app: FastAPI, world: World) -> None:
    user = ApiUser(app, "alice")
    csv_text = HEADER + "1,P,5,A,1,\n"

    body = user.post(
        "/api/mark-scheme/import-preview",
        content=csv_text.encode(),
        headers={"Content-Type": "text/csv"},
    ).json()

    assert body["validation"]["readiness"][0]["code"] == "question.points_below_max"


def test_preview_rejects_other_content_types(app: FastAPI, world: World) -> None:
    user = ApiUser(app, "alice")

    response = user.post("/api/mark-scheme/import-preview", json={"csv": GOOD_CSV})

    assert response.status_code == 422
    assert response.json()["code"] == "import.wrong_type"


def test_preview_rejects_oversized_body(app: FastAPI, world: World) -> None:
    user = ApiUser(app, "alice")

    response = user.post(
        "/api/mark-scheme/import-preview",
        content=b"a" * (MAX_CSV_BYTES + 10),
        headers={"Content-Type": "text/csv"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "import.too_large"


def test_preview_requires_sign_in(client: TestClient) -> None:
    response = client.post(
        "/api/mark-scheme/import-preview", content=b"x", headers={"Content-Type": "text/csv"}
    )

    assert response.status_code == 401

import io
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

from app.db.models import Page, PageState, Script, Student
from app.exports.marked_pdf import write_marked_pdf
from app.services.results import ResultPage, ScriptResult


def test_duplex_class_reprints_never_share_a_sheet_between_students(tmp_path: Path) -> None:
    Image.new("RGB", (300, 500), "white").save(tmp_path / "scan.jpg")
    results = []
    for ident, code in enumerate(["AAAAAA", "BBBBBB"], start=1):
        student = Student(id=ident, school_id=1, class_id=1, code=code)
        script = Script(id=ident, exam_id=1, student_id=ident, student=student)
        page = Page(
            id=ident,
            script_id=ident,
            upload_id=1,
            source_page_index=ident,
            image_path="scan.jpg",
            thumb_path="scan.jpg",
            width=300,
            height=500,
            state=PageState.ASSIGNED,
            position=1,
            is_cover=False,
            rotation_stack=0,
            rotation_auto=0,
        )
        results.append(ScriptResult(script, [], pages=[ResultPage(page, "")]))
    output = io.BytesIO()
    assert write_marked_pdf(output, results, "Exam", tmp_path, "en", duplex=True) == 4
    with pdfium.PdfDocument(output.getvalue()) as document:
        assert len(document) == 4
        texts = []
        for index in range(4):
            page = document[index]
            text = page.get_textpage()
            try:
                texts.append(text.get_text_range())
            finally:
                text.close()
                page.close()
        assert "AAAAAA" in texts[0]
        assert texts[1] == ""
        assert "BBBBBB" in texts[2]
        assert texts[3] == ""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.subjects.registry import SubjectConfig, SubjectRegistry, get_registry


def test_shipped_configs_cover_first_version_subjects() -> None:
    subjects = get_registry().for_curriculum("cm_gce_ol")

    assert [s.code for s in subjects] == ["chemistry", "economics", "mathematics"]
    for subject in subjects:
        assert subject.names.en
        assert subject.names.fr
        assert subject.reader.notation_hints


def test_unknown_curriculum_has_no_subjects() -> None:
    assert get_registry().for_curriculum("ke_kcse") == []


def test_adding_a_subject_is_just_a_file(tmp_path: Path) -> None:
    (tmp_path / "biology.toml").write_text(
        'code = "biology"\ncurriculum = "cm_gce_ol"\n[names]\nen = "Biology"\nfr = "Biologie"\n',
        encoding="utf-8",
    )

    registry = SubjectRegistry.from_directory(tmp_path)

    subject = registry.get("cm_gce_ol", "biology")
    assert subject is not None
    assert subject.names.fr == "Biologie"


def test_invalid_config_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "bad.toml").write_text('code = "Bad Code!"\ncurriculum = "x"\n', encoding="utf-8")

    with pytest.raises(ValidationError):
        SubjectRegistry.from_directory(tmp_path)


def test_duplicate_subjects_are_rejected() -> None:
    subject = SubjectConfig.model_validate(
        {"code": "chemistry", "curriculum": "cm_gce_ol", "names": {"en": "C", "fr": "C"}}
    )

    with pytest.raises(ValueError, match="Duplicate"):
        SubjectRegistry([subject, subject])

from enum import StrEnum

from sqlalchemy import Enum


def str_enum[E: StrEnum](enum_cls: type[E], name: str) -> Enum:
    """Portable enum column: stored as VARCHAR with a CHECK constraint, not a native type."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        length=32,
        values_callable=lambda members: [m.value for m in members],
    )

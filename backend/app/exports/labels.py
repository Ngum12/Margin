"""Headings printed in exported files, in the requesting teacher's language."""

LABELS: dict[str, dict[str, str]] = {
    "en": {
        "student_code": "Student code",
        "student_name": "Name",
        "total": "Total",
        "max": "Maximum",
        "percentage": "Percentage",
        "confirmed_at": "Confirmed at",
        "page": "Page",
        "results": "Results",
        "comments": "Comments",
        "marks_here": "Marks for this page",
        "not_marked": "No question marked on this page",
        "ai_model": "AI model",
        "test_model": "Test model: not real AI marking",
    },
    "fr": {
        "student_code": "Code élève",
        "student_name": "Nom",
        "total": "Total",
        "max": "Maximum",
        "percentage": "Pourcentage",
        "confirmed_at": "Confirmée le",
        "page": "Page",
        "results": "Résultats",
        "comments": "Commentaires",
        "marks_here": "Notes de cette page",
        "not_marked": "Aucune question notée sur cette page",
        "ai_model": "Modèle d'IA",
        "test_model": "Modèle de test : pas une vraie correction par IA",
    },
}


def labels(language: str) -> dict[str, str]:
    return LABELS.get(language, LABELS["en"])

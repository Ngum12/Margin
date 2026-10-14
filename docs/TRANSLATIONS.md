# Translations

English (`frontend/src/i18n/locales/en.json`) is the source. French (`fr.json`) must have exactly the same keys (enforced by a frontend test), and every backend error and issue code must have text in both (enforced by `backend/tests/test_translations.py`).

## Status
| Language | Status | Reviewed by |
|---|---|---|
| English | Complete | n/a |
| French | **Draft**: every string present, written by the engineer, not yet reviewed by a French-speaking teacher. | not yet |

## Before release
- A francophone teacher (ideally from a Cameroonian bilingual school) reviews every French string in context, especially exam vocabulary ("barème", "élément du barème", "fiche de couverture").
- Record the reviewer and date in the table above.

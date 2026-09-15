# AI Agent Instructions for Document Archiving System

## Purpose
This file helps AI coding agents quickly understand the repository, its architecture, and the key commands needed to run and test the project.

## Project type
- Django web application.
- Python 3 virtual environment expected in `.venv`.
- Default database is SQLite, with optional PostgreSQL support via `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT` environment variables.

## Key commands
- `python -m venv .venv`
- Windows activate: `.venv\Scripts\activate`
- `pip install -r requirements.txt`
- `cp .env.example .env`
- `python manage.py migrate`
- `python manage.py seed_archive`
- `python manage.py runserver`
- `python manage.py test`

## What matters most
- `config/settings.py` contains environment-driven configuration and the SQLite fallback.
- `accounts/models.py` defines the custom `User` model with `role` and `is_archive_admin`.
- `accounts/mixins.py` enforces RBAC: `AdminRequiredMixin` for write/admin actions, `StaffUserRequiredMixin` for read-only signed-in users.
- `documents/models.py` contains the archive domain model, including:
  - `Document` with sequential per-type/year numbering via `save()` and `select_for_update()` row locking.
  - `DocumentQuerySet.visible_to(user)` for staff/admin visibility rules.
  - soft-delete semantics with `Document.soft_delete()` / `restore()`.
  - audit trail and notifications.
- `documents/views.py` handles search, file creation/editing, downloads, attachments, soft delete, restore, and admin-only CSV export.

## Important conventions
- Role enforcement is done in views and mixins, not by hiding UI elements.
- Confidential records are excluded from staff users via `Document.objects.visible_to(user)`.
- The control number format is a business-critical feature: `TYPE No. NNN, s. YEAR` with special handling for indorsements.
- Media files are served from `/media/` in `DEBUG` only; production should use `document_download` with an authenticated download flow.

## Tests
- `documents/tests.py` covers control-number generation, access control, search filters, and soft-delete behavior.
- Use the tests as a reliable source when changing document numbering, RBAC, or visibility logic.

## Helpful docs
- Primary repository documentation: `README.md`

## Recommended agent behavior
- Preserve the existing role-based authorization model.
- Avoid changing business logic without explicit test updates.
- Keep UI and template changes narrow unless the issue is clearly related to a form/view requirement.
- Prefer using existing Django patterns already present in the repo.

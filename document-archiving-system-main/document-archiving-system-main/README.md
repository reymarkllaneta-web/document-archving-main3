  # Records Archive — Django document archiving system

  Files, numbers, searches and serves four record types: **Memorandum**, **Indorsement**,
  **Office Order** and **Executive Order**. Access is split two ways: administrators file and
  manage, staff users search and read.

  ---

  ## What it does

  **Control numbers.** Every record carries `TYPE No. NNN, s. YEAR` — for example
  `MEMORANDUM No. 012, s. 2026`. Numbering runs independently per type per series year.
  Leave the number blank on the form and the next one in that series is assigned on save,
  inside a row lock so two clerks saving at the same moment can't take the same number.
  Indorsements get their level in front: `2nd INDORSEMENT No. 004, s. 2026`.

  **Search.** One panel filters on keyword (subject, summary, tags, office, signatory,
  addressee), type, number, series year, status, originating office, and issue-date range.
  Results paginate; administrators can export the current result set to CSV.

  **Records keep their links.** An indorsement points at the document it forwards; a
  superseding order points at what it replaced. The detail page shows both directions of
  that chain.

  **Nothing is really deleted.** Removing a record moves it to the bin and drops it out of
  search, but the control number stays reserved so the series keeps its order. An
  administrator can restore it.

  **Audit trail.** Sign-ins, searches, document views, downloads, edits and account changes
  are all logged with user, timestamp and IP. The log is read-only — even in Django admin.

  ---

  ## Role-based access control

  Two roles, stored on the user record (`accounts.User.role`), enforced by
  `accounts/mixins.py`. Superusers are always treated as administrators.

  | | Administrator | Staff user |
  |---|---|---|
  | Search and open records | yes | yes |
  | Download scans and enclosures | yes | yes |
  | File a new document | yes | no |
  | Edit a document | yes | no |
  | Remove / restore a document | yes | no |
  | See confidential records | yes | no |
  | Add enclosures | yes | no |
  | Export the index to CSV | yes | no |
  | Create and edit accounts | yes | no |
  | Reset another user's password | yes | no |
  | Read the audit trail | yes | no |

  Enforcement is on the view, not the template. Hiding a button never grants a permission —
  `AdminRequiredMixin` returns 403 on any direct URL hit, and the download and export views
  check the role before they open a file. Denied attempts land in the audit trail.

  Two guardrails on account editing: an administrator cannot remove their own administrator
  role, and cannot deactivate their own account. That prevents locking every administrator
  out of user management.

  ---

  ## Setup

  ```bash
  python -m venv .venv
  source .venv/bin/activate          # Windows: .venv\Scripts\activate
  pip install -r requirements.txt

  cp .env.example .env               # then set DJANGO_SECRET_KEY

  python manage.py makemigrations accounts documents
  python manage.py migrate
  python manage.py seed_archive      # demo accounts + sample records (optional)
  python manage.py runserver
  ```

  Open http://127.0.0.1:8000/. The seed command creates:

  - `admin` / `archive-admin-2026` — Administrator
  - `clerk` / `archive-user-2026` — Staff user

  **Change both passwords before this touches real records.** Skip `seed_archive` entirely
  and use `python manage.py createsuperuser` if you'd rather start clean.

  Run the tests with `python manage.py test`. They cover series numbering, the role
  boundaries, confidential-record visibility, search filters, and soft delete.

  ---

  ## Layout

  ```
  config/          settings, urls
  accounts/        User model (role, office), login, account management, RBAC mixins
  documents/       Document, Attachment, AccessLog; search form; views; seed command; tests
  templates/       base shell, search, detail, forms, audit trail
  static/css/      app.css
  media/           uploaded scans and enclosures (git-ignored)
  ```

  ---

  ## Before going live

  - Set `DJANGO_DEBUG=False`, a real `DJANGO_SECRET_KEY`, and `DJANGO_ALLOWED_HOSTS`.
  - Move to PostgreSQL — the commented block in `config/settings.py` shows the swap. SQLite
    is fine for a single office; it isn't fine for concurrent writers.
  - **Serve media through the app, not the web server.** In `DEBUG` mode Django serves
    `/media/` directly, which means anyone with a URL can fetch a scan without signing in.
    In production, drop that route and let `document_download` serve files (nginx
    `X-Accel-Redirect` or Apache `X-Sendfile` keeps it fast). The view already checks the
    role and logs the download.
  - Put it behind HTTPS. The settings file switches on secure cookies and HSTS when
    `DEBUG=False`.
  - Back up both the database and `media/`. Neither one is useful without the other.
  - Add a virus scan on upload if the archive accepts files from outside the office.

  ## Easy extensions

  - **More document types:** add to `DocumentType` in `documents/models.py` and migrate.
    Numbering, search and the dashboard pick them up with no other changes.
  - **Full-text search:** on PostgreSQL, replace `DocumentQuerySet.search` with
    `SearchVector` / `SearchRank` for ranked results and stemming.
  - **OCR:** run uploaded scans through Tesseract and write the text into `description` so
    the contents become searchable, not just the metadata.
  - **Retention schedules:** add a `disposal_date` and a management command that flags
    records due for disposal.

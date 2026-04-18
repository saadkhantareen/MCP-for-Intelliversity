# Bulk Upload Implementation

## Overview
The bulk upload feature allows platform administrators to create `User` accounts, `BaseProfile`s, and role-specific profiles (`StudentProfile` or `FacultyProfile`) via CSV or Excel (XLSX) file uploads. This significantly accelerates the onboarding process.

## Architecture

### 1. Data Definitions (`bulk_constants.py`)
Centralizes all column names and requirements:
- **Core Columns**: `role` (student/faculty), `email`, `password`, `first_name`, `last_name`. If `password` is left empty, a secure fallback is generated (though this may be hidden unless emailed).
- **Profile Columns**: Maps raw columns to `BaseProfile`, `StudentProfile`, and `FacultyProfile` fields (e.g., `enrollment_number`, `qualification`, `cgpa`).

### 2. File Parsing (`bulk_parser.py`)
Handles parsing of both `.csv` and `.xlsx` files:
- Detects the file format.
- Uses the `csv` module for CSV files and `openpyxl` for Excel files.
- Converts the data into an array of dictionaries representing each row.

### 3. Row Processing (`bulk_processor.py`)
Handles DB insertion per row with explicit multi-tenancy support using `db_alias`:
- Normalizes spaces and handles `NoneType` issues natively to prevent unhandled `.strip()` crashes for empty Excel cells.
- Sets passwords via `set_password()`.
- Explicitly queries `using(db_alias)` for all objects, circumventing a known Django bug where ManyToMany relationships (like `User.groups`) default back to the "default" database and violation constraints are triggered.
  *Fix implemented*: `user.groups.through.objects.using(db_alias).get_or_create(user_id=user.id, group_id=group.id)`
- In case of failure during `BaseProfile` or role profile creation, gracefully deletes the un-linked `User` from the current tenant database to avoid orphaned users, ignoring global logging constraints (`django_admin_log` tenant table unavailability).

### 4. API Endpoints (`views_bulk.py`)
- **GET `/api/v1/profiles/bulk-upload/template/`**: Provides a dynamically generated boilerplate CSV template incorporating all columns designated in `bulk_constants.py`.
- **POST `/api/v1/profiles/bulk-upload/`**: Standard multipart-form upload endpoint. Intercepts the uploaded file, reads it via parser, iterates over it with the processor, and returns an array of success/error statuses per row.

## Testing & Usage
1. Use standard formatting and the exact headers given by `/api/v1/profiles/bulk-upload/template/`.
2. Any row with incorrect roles or duplicate emails will fail independently without halting the remaining valid rows.
3. Once completed, successful users are inherently bound to the database associated with the active tenant domain (e.g., `intelliversity_comsats`) and tagged with their access `Group` (`student` or `faculty`), enabling immediate portal authentication.

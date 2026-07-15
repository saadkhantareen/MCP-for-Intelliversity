# Accounts and Profiles Data Models

Django splits logic between Authentication contexts (`apps.accounts.models`) and role-specific user details (`apps.profiles.models`).

## The `User` Model (`apps.accounts.models.User`)
This defines the core session entity:
- A custom user model inheriting `AbstractBaseUser` and `PermissionsMixin`.
- Defines `email` as the primary identifier implicitly replacing traditional `username`.
- Standard user activity flags: `is_active`, `is_staff`.
- Inherits core abstractions like `BaseModel` (likely appending tracking metadata such as created/modified timestamps).

## The `Profiles` Model Stack (`apps.profiles.models`)

All profiles wrap around the central user entity, decoupling access levels and logic from identity validation:

1. **`BaseProfile`** (`models.OneToOneField` to `User`):
   - Holds general, universal demographic parameters.
   - Handles relationships natively (Father's name, Address, Gender).
   - Bio details: Phone Numbers, Contact Information, Picture bindings.
   - Contains a one-to-many relationship with `Document` entities.

2. **`StudentProfile`** (`models.OneToOneField` to `BaseProfile`):
   - Tracks university data for active students.
   - Examples: `enrollment_number`, `department`, `program`, `semester`, `batch_year`, `cgpa`.

3. **`FacultyProfile`** (`models.OneToOneField` to `BaseProfile`):
   - Focuses broadly on operational capabilities.
   - Fields: `designation`, `qualification`, `specialization`, `experience_years`, `office_number` mapping.

4. **`AdminProfile`** (`models.OneToOneField` to `BaseProfile`):
   - Simplified staff metrics context: includes `designation`, `office_number`, and `office_location`.

5. **`Document`** (`models.ForeignKey` to `BaseProfile`):
   - Captures records mapping a given document file to user credentials (`document_type` mapped to Enums like `MATRIC_RESULT`, `PHD_DEGREE`, `CNIC` or `PASSPORT`). Support for `is_verified` flags per document metadata entry.
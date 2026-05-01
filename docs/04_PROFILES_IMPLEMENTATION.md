# Profiles Application Implementation Details

This document comprehensively outlines the core internal structure, logic, and flow of the `apps/profiles` module in the Intelliversity Backend. It contains the exact behaviors defined in `models.py`, `serializers.py`, `views.py`, and `migrations/0001_initial.py`.

## 1. Data Schema (`apps/profiles/models.py`)

The application embraces a distributed "role-profile" architecture wrapped around a centralized `BaseProfile`. 

### `BaseProfile`
Acts as the central node mapping a single user to their demographic and generic characteristics.
- **Relations**: Uniquely binds securely to the `User` model (`settings.AUTH_USER_MODEL`) with a `OneToOneField(on_delete=models.CASCADE)`.
- **Fields Summary**: 
   - Media: `profile_picture` (ImageField).
   - Identity: `father_name`, `date_of_birth`, `gender` (Choice of male/female/other), `nationality`, `cnic` (15 char string), `religion`.
   - Contact Info: `phone_number`, `emergency_contact`, `address`, `city`, `country`.
   - Free text: `bio`.

### Role-Specific Profiles (`StudentProfile`, `FacultyProfile`, `AdminProfile`)
Each role-specific model extends the profile vertically by adding a `OneToOneField` to `BaseProfile`.
- **`StudentProfile`**: Maps `enrollment_number`, `department`, `program`, `semester`, `batch_year`, and `cgpa` (DecimalField, max_digits=4).
- **`FacultyProfile`**: Contains career info like `designation`, `qualification`, `specialization`, `experience_years`, `office_number`, and `office_location`.
- **`AdminProfile`**: Retains basic administrative configurations like `designation`, `office_number`, and `office_location`.

### `Document`
A polymorphic file attachment model mapping uploaded user documents.
- **Relations**: Linked via `ForeignKey` to `BaseProfile`.
- **Fields**: 
  - `document_type`: Uses TextChoices (`MATRIC_RESULT`, `BACHELOR_DEGREE`, `PASSPORT`, `CNIC`, etc.).
  - `title`, `file` (FileField), `description`, and an `is_verified` boolean to manage validity.

---

## 2. API Serialization & Validation (`apps/profiles/serializers.py`)

The serializers manage deeply nested JSON payload updates and restrict certain field accesses depending on role permissions.

### Custom Validators
- **`validate_cnic(value)`**: Ensures the CNIC only contains numbers/dashes and explicitly checks for exactly 13 digits (excluding dashes).
- **`validate_phone_number(value)`**: Ensures > 10 digits and only contains `+`, `-`, or numeric values.
- **`validate_date_of_birth(value)`**: Restricts birth dates to the past.

### Serializer Breakdown
1. **`DocumentSerializer` & `AdminDocumentSerializer`**:
   - `DocumentSerializer` makes `is_verified` read-only for standard users.
   - `AdminDocumentSerializer` allows modifications (e.g., verifying a student's document mapping) while protecting `id`, `created_at`, `updated_at`.
2. **`BaseProfileSerializer`**:
   - Flattens the User data by extracting read-only `email`, `first_name`, `last_name` from the `User` model using `source="user.[field]"`.
   - Includes `get_roles` via a `SerializerMethodField` referencing `user.groups`.
3. **Dual-Serializer Role Pattern**:
   - The app dynamically uses different serializers depending on who is invoking the update.
   - Example: **`StudentProfileSerializer`** sets academic metrics (`department`, `program`, `cgpa`) to **`read_only_fields`** to prevent students from editing their own CGPA. 
   - Conversely, **`AdminStudentProfileSerializer`** removes these restrictions, enabling full write access to all academic attributes.
   - Similar pairing is enforced for `FacultyProfile` and `AdminFacultyProfile`.
   - Overrides the `update()` loop locally: extracts nested `base_profile` data via `validated_data.pop("base_profile", {})` to patch both models concurrently.

---

## 3. Operations & Access Controllers (`apps/profiles/views.py`)

The views embrace implicit data mapping. Instead of making the user pass their ID, views heavily rely on JWT tokens and tenant scopes.

### Core Helpers
- **`ROLE_PROFILE_MAP`**: Maps portal strings (`"student"`, `"faculty"`, `"admin"`) to their respective `(Model, UserSerializer, AdminSerializer)`.
- **`get_or_create_base_profile` / `get_or_create_role_profile`**: Because profiles might not exist immediately on user signup, they are defensively "lazily instantiated" via Django's `get_or_create` on-the-fly handling when APIs are hit.

### Endpoints
1. **`MyProfileView` (`/api/v1/profiles/me/`)**:
   - Resolves the requested profile architecture directly from `request.portal_name` (e.g., handles Faculty if on the `faculty` subdomain).
   - Validates that the targeted role exists inside `request.user.groups`.
   - `GET` fetches the active user's profile.
   - `PUT` seamlessly updates the user's role-profile and base-profile simultaneously via `partial=True`.
2. **`UserProfileView` (`/api/v1/profiles/users/`)**:
   - Admin-exclusive. Blocked by `_is_admin()` checking if `request.portal_name == "admin"`.
   - Can list all user roles across the tenant, dynamically resolving and packaging them utilizing the paired `AdminSerializer` via `ROLE_PROFILE_MAP`.
   - Allows administrators to run unrestrained `PUT` operations to modify user properties (like verified CGPAs).
3. **`DocumentView` & `AdminDocumentView`**:
   - Provides granular upload, retrieval, and deletion of personal document archives. Admin views mirror this but specify individual users via URL parsing. 

---

## 4. Database Setup & Initialization (`apps/profiles/migrations/0001_initial.py`)

Highlights from the generated SQL representation mapping:
- Primary keys universally utilize `UUIDField(default=uuid.uuid4, editable=False, primary_key=True)`.
- `created_at` (`auto_now_add=True`) and `updated_at` (`auto_now=True`) fields are embedded directly across all profile and document schemas globally, courtesy of inheriting `apps.base_models.BaseModel`.
- All `OneToOneFields` (`user` to `BaseProfile`, `base_profile` to `StudentProfile`, etc.) cascade cleanly upon parent deletion.
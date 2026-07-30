## Models, Cloudinary and Dynamic Portal Branding

This document describes the core Django models introduced for multi-tenancy, portal branding, and how Cloudinary is used for dynamic assets.

### Core models (apps.tenants)

- `University`
  - Fields: `id (UUID)`, `name`, `subdomain`, `db_name`, `db_host`, `db_port`, `is_active`, timestamps
  - Purpose: stores tenant database connection details and meta used to route requests.

- `Portal`
  - Fields: `id (UUID)`, `name` (choices: `student`, `faculty`, `admin`, `parent`), `is_active`, timestamps
  - Purpose: standardizes portal types across universities.

- `UniversityPortal` (through / junction model)
  - Fields: `id (UUID)`, `university (FK)`, `portal (FK)`, `is_active`, timestamps
  - Purpose: links a `University` to any number of `Portal` types. Used as the primary join for branding and domains.

- `PortalBranding`
  - Fields: `id (UUID)`, `university_portal (OneToOne to UniversityPortal)`, `logo_url`, `logo_public_id`, `logo_dark_url`, `logo_dark_public_id`, `favicon_url`, `favicon_public_id`, `theme_config (JSON)`, timestamps
  - Cloudinary: `*_public_id` fields store Cloudinary public IDs; `*_url` fields are the CDN URLs that may be served directly to frontends.
  - Purpose: stores per-university-per-portal visual branding and theme configuration. The frontend fetches this to apply theming dynamically.

- `PageAsset`
  - Fields: `id (UUID)`, `university_portal (FK)`, `page_type` (e.g., `login`, `register`, `forgot_password`, `dashboard`, `landing`), `background_image_url`, `background_image_public_id`, `metadata (JSON)`, timestamps
  - Purpose: per-page visual assets (background image + metadata) for each portal.

- `UniversityDomain`
  - Fields: `id (UUID)`, `university_portal (FK)`, `domain` (string), `is_primary`, `is_custom`, `ssl_status`, `verified_at`, timestamps
  - Purpose: maps a `UniversityPortal` to one or more usable domains (e.g. `student.fast.localhost`). The router and middleware use this table to determine tenant and portal from incoming Host header.


### How Cloudinary is used

- Upload flow: the admin UI or a background job uploads images (logos, favicons, page backgrounds) to Cloudinary and saves both the returned CDN URL and the `public_id` into `PortalBranding` / `PageAsset`.
- Serving: frontend uses the stored `*_url` fields. When transformations are needed, the `public_id` can be used together with the Cloudinary SDK to generate resized/optimized URLs.
- Security: cloudinary keys are stored in env variables (`CLOUDINARY_*` in `.env`) and used server-side for uploads and signed requests.


### Dynamic Portal Theming & Request Routing

- Incoming requests are routed by inspecting the Host header.
  - The tenant middleware (`apps.tenants.middleware` / `router`) looks up the `UniversityDomain` matching the host, retrieves the attached `UniversityPortal`, and sets the current tenant and portal in the request context.
- The frontend requests portal branding from the backend (or receives branding during SSR). Backend exposes branding as JSON (the `PortalBranding` fields) for the matched tenant + portal.
- The frontend then applies the `theme_config` and logos dynamically. Background images (from `PageAsset`) are loaded per page.


### Management commands & lifecycle

- `migrate_tenants`: applies migrations on each tenant database configured in `University.db_name` etc.
- `seed_roles`: creates default roles & permissions inside each tenant DB.


### Notes for developers

- When adding new visual fields, prefer storing both `*_public_id` and an explicit `*_url` so stored records remain valid even if CDN prefixes or signed URL approaches change.
- For local development the `UniversityDomain` entries are often mapped to `.localhost` hosts in `/etc/hosts` (e.g. `student.fast.localhost`) to avoid external DNS.

---
File last updated: April 27, 2026

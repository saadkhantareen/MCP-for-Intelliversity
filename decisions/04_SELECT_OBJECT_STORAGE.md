# Use Cloudinary for Asset Storage and Media Delivery

## The Problem

The University Management System needs a secure, cost-effective way to store, upload, manage, and deliver public and private assets without adding unnecessary infrastructure complexity during development.

## Options Considered

- **Cloudinary** — Managed asset storage, direct signed uploads, image transformations, optimization, and media delivery, with a free plan suitable for initial development within its usage limits.
- Amazon S3 — General-purpose object storage with presigned uploads, granular access controls, and usage-based pricing.
- Cloudflare R2 — S3-compatible object storage with presigned uploads and usage-based pricing.
- Self-hosted object storage — Greater infrastructure control but additional costs and responsibility for deployment, security, maintenance, and scaling.

## Rationale

- **Low initial cost:** Cloudinary's free plan allows development and testing without an initial paid subscription, provided storage, transformation, bandwidth, and other usage remain within the plan's limits.
- **Faster development:** Cloudinary provides storage, image transformations, optimization, and delivery without requiring us to build and maintain these capabilities ourselves.
- **Efficient uploads:** The Django REST Framework backend generates upload signatures, allowing the frontend to upload files directly to Cloudinary instead of routing large files through the application server.
- **Security control:** The backend authenticates users, validates upload requests, enforces tenant permissions, and manages access to private assets. Public and private assets use appropriate delivery policies.
- **Reduced infrastructure complexity:** A managed media service allows development efforts to focus on the UMS's core functionality, including tenant isolation, academic workflows, and AI integration.
- **Future portability:** A provider-neutral asset service and internal asset records will isolate Cloudinary-specific logic from business modules, making a future migration to Amazon S3 or Cloudflare R2 easier.

## Notes

- Cloudinary is the initial asset storage and media delivery provider. Its free plan is appropriate for initial development, but production suitability must be reassessed as usage grows.
- Free-plan limits and features can change. Review the [Cloudinary pricing page](https://cloudinary.com/pricing) before deployment and monitor usage to avoid unexpected restrictions or upgrade requirements.
- Assets will be associated with internal asset records rather than relying exclusively on provider-specific URLs. Records should track provider identifiers, tenant ownership where applicable, visibility, and upload status.
- The backend remains responsible for tenant isolation and authorization. Organizing files into tenant-specific folders alone does not provide security isolation.
- Upload signatures authorize uploads; they do not automatically authorize private downloads. Private assets require appropriate access controls and authorized delivery.
- Migration to another provider will require copying and verifying files, updating asset metadata, adapting access policies, and replacing provider-specific transformations where necessary.
- Cloudinary, Amazon S3, and Cloudflare R2 are not functionally identical. Future portability reduces migration effort but does not eliminate provider-specific changes.

### References

- [Cloudinary Pricing](https://cloudinary.com/pricing)
- [Cloudinary Upload API Reference](https://cloudinary.com/documentation/image_upload_api_reference)
- [Cloudinary Control Access to Media](https://cloudinary.com/documentation/control_access_to_media)
- [Amazon S3 Presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html)
- [Cloudflare R2 Presigned URLs](https://developers.cloudflare.com/r2/api/s3/presigned-urls/)

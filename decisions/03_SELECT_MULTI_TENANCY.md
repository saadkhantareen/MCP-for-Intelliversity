# Adopt Database-per-Tenant (Silo) Model for Multi-Tenant Data Tier

### The Problem
Select a data-tier tenant isolation architecture that guarantees strict institutional data privacy, compliance, and fault containment for high-value university tenants without prohibitive infrastructure complexity.

### Options Considered
- **Database-per-Tenant on Shared Instances (Soft Silo with Hard Silo Graduation Path)**
- Pool (Shared Database & Schema with `tenant_id` + Row-Level Security) — rejected because a single query bug, ORM misconfiguration, or missing filter risks catastrophic cross-tenant data leaks across FERPA/GDPR-regulated student and financial records.
- Schema-per-Tenant (One Database, Schema per Tenant) — rejected because shared database resources (WAL, locks, buffer cache, catalog bloat) retain noisy-neighbor and blast-radius risks while complicating single-tenant point-in-time recovery.
- Instance- / Account-per-Tenant (Hard/Full-Stack Silo by Default) — rejected as the baseline due to excessive idle infrastructure costs and linear fleet management overhead, but retained as a graduation tier for exceptional compliance or workload needs.
- Bridge / Hybrid (Pooled for Small, Silo for Large) — rejected because all target tenants are high-value institutions requiring strict isolation; supporting dual data paths early introduces unjustified architectural overhead.

### Rationale
- **Structural Data Isolation & Minimal Blast Radius:** Dedicated logical databases and tenant-scoped credentials structurally eliminate cross-tenant data leakage from application query bugs, ORM flaws, or SQL injections.
- **Institutional Compliance & Auditability:** Satisfies university procurement and regulatory requirements (FERPA, GDPR, data residency) with simple, provable per-tenant data purging, independent exports, and isolated backup/restore workflows.
- **End-to-End AI Safety:** Prevents cross-institutional contamination across AI workloads (RAG retrieval, vector embeddings, prompt histories, semantic caches) by scoping vector storage (`pgvector`) and retrieval strictly to authenticated tenant database contexts.
- **Seamless Scalability & Dev Parity:** Matches local development setup (multiple tenant databases on a single instance) while enabling heavy or sovereign tenants to graduate to dedicated instances or AWS Regions via a tenant catalog router without application code rewrites.

### Notes
- **Operational Mitigations:**
  - *Connection Pooling:* PgBouncer and RDS Proxy handle connection multiplication across tenant databases to prevent resource exhaustion.
  - *Migration Orchestrator:* CI/CD pipelines automate multi-tenant schema migrations with canary ordering, state tracking, and retry/rollback capabilities.
  - *Tenant Catalog & Router:* A control-plane service maps tenant IDs to database endpoints and credentials retrieved from AWS Secrets Manager.
  - *Noisy-Neighbor Controls:* Per-tenant statement timeouts, query governors, dedicated read replicas, and performance monitoring mitigate resource contention on shared instances.
- **AI Tier Isolation Rules:**
  - Vector embeddings and indexes are stored per tenant in the tenant database using `pgvector`.
  - RAG retriever contexts are bound strictly to verified JWT/auth tokens, never user input prompts.
  - Caches and conversational logs are isolated per tenant; no cross-tenant model training or fine-tuning occurs on customer data.
  - Object storage enforces tenant-scoped S3 prefixes, dedicated buckets, or tenant KMS encryption keys.
- **References:**
  - AWS Well-Architected SaaS Lens: Tenant Isolation (Silo, Pool, Bridge)
  - AWS Whitepaper: SaaS Tenant Isolation Strategies
  - AWS SaaS Factory: Multi-Tenant Data Partitioning and Onboarding Automation

### Extras
> #### Silo model at the data layer OR database-per-tenant on a shared instance.

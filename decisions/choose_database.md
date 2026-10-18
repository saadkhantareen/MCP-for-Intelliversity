# Use PostgreSQL with Django REST Framework for Primary Database

### The Problem
Select a primary database that enforces strict ACID compliance for multi-tenant academic and financial records while natively supporting vector embeddings for AI workflows without adding operational overhead.

### Options Considered
- **PostgreSQL (with `django.contrib.postgres` and `pgvector`)**
- MongoDB (NoSQL) — lacks strict relational integrity and robust multi-collection ACID transactions needed for complex relational queries (e.g., degree audits and transcripts across semesters).
- MySQL — lacks mature native vector search capabilities (`pgvector`) for RAG workflows and offers weaker out-of-the-box Django ORM support for advanced data types.
- Dedicated Vector DB (Pinecone / Milvus) + RDBMS — introduces operational bloat and risks dual-write inconsistency or orphaned vector records.

### Rationale
- **Unified Relational & Vector Engine (`pgvector`):** Stores structured university management data alongside 1,536-dimensional semantic embeddings for the AskAI RAG agent within the same tables and transactions, preventing sync errors and eliminating separate vector database infrastructure.
- **Deep Django Synergy & Hybrid Data Types:** First-class integration via `django.contrib.postgres` enables native usage of `JSONB` with GIN indexing, `ArrayField`, and `SearchVector` (Trigram search) for flexible department rubrics and course metadata while preserving relational integrity.
- **Robust Multi-Tenant Isolation:** Seamlessly supports siloed database-per-tenant and schema-based isolation patterns to structurally guarantee cross-tenant security and zero data leakage.
- **Strict ACID Guarantees:** Ensures absolute transactional reliability required for university fee processing, grade publishing, and prerequisite validation.

### Notes
- **Connection Overhead Mitigation:** To mitigate PostgreSQL's process-per-connection memory footprint under peak student loads, PgBouncer is deployed as a lightweight connection pooler in front of the database.
- **Multi-Tenant Migration Strategy:** Multi-database migration complexity across tenant instances is mitigated by automating schema migrations through the CI/CD deployment pipeline.
- **Production Precedents:**
  - Supabase — relies on PostgreSQL schema isolation and Row-Level Security (RLS) to power thousands of multi-tenant workloads.
  - Notion — uses PostgreSQL to manage large-scale hierarchical tenant data and JSONB document structures.
- **References:**
  - *Multi-Tenant SaaS Database Architecture: Pooled, Silo, and Bridge Patterns* (2026)
  - *pgvector Guide: Vector Search and RAG in PostgreSQL* (2026)
  - *PostgreSQL for Django Developers: Beyond Raw SQL* (2026)

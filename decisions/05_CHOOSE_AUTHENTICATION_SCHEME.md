# JWT-Based Authentication

**Status:** Accepted

## Context

Intelliversity is an AI-powered, multi-tenant University Management System built with React, Django REST Framework, and PostgreSQL. The backend exposes APIs for students, faculty members, and administrators across university-specific tenants.

The system requires an authentication mechanism that integrates with a frontend–backend architecture, supports protected API endpoints, and can accommodate future client applications.

## Decision

We selected Django REST Framework Simple JWT for API authentication. Authenticated clients send access tokens through the HTTP `Authorization` header using the Bearer authentication scheme.

Django REST Framework remains responsible for enforcing application permissions, while tenant-resolution logic and data-access controls enforce university-level isolation.

## Rationale

1. **API compatibility:** Bearer tokens provide a standard mechanism for presenting authentication credentials to protected HTTP endpoints.

2. **Reduced token-lookup overhead:** Signed access tokens can be validated without requiring a database lookup for a token record on every request.

3. **Token lifecycle management:** Simple JWT supports configurable access-token and refresh-token lifetimes, allowing us to balance session continuity and security.

4. **Framework integration:** The solution integrates with Django's authentication model and DRF permission classes without requiring a separate authentication framework.

5. **Extensibility:** The approach can accommodate additional API clients without requiring each client to use Django's browser-session mechanism.

## Alternatives considered

- **Django SessionAuthentication:** Rejected in favor of bearer-token authentication for the chosen frontend–backend API design. Session authentication remains a viable alternative, particularly for browser-focused applications requiring centralized session control.

- **DRF TokenAuthentication:** Rejected because its standard implementation does not provide the same built-in access/refresh-token lifecycle and typically requires a database lookup for the token record.

- **OAuth 2.0 / OpenID Connect:** Not selected because the current application does not require a dedicated authorization server, delegated third-party access, or federated identity infrastructure.

- **Opaque access tokens:** Not selected because the application can benefit from self-contained access-token validation without a token-record lookup on every request.

## Consequences

The decision reduces authentication-related token-lookup overhead and provides a clear access-token lifecycle.

However, access tokens may remain valid until expiration unless an additional revocation mechanism is implemented. The system must also protect token storage and transport, validate account status where required, and enforce tenant isolation independently of authentication.

## Security requirements

- Enforce HTTPS in production.
- Use appropriately short-lived access tokens.
- Protect refresh tokens and define a secure refresh and logout strategy.
- Configure token rotation and revocation according to the application's security requirements.
- Avoid sensitive information in JWT claims.
- Enforce role-based permissions, object-level access controls, and tenant isolation.
- Protect browser token storage against XSS-related risks.
- Apply CSRF protection when authentication credentials are transported through cookies.
- Keep signing keys secure and plan for key rotation.

## Conclusion

Simple JWT was selected as a proportionate authentication solution for Intelliversity's API-oriented architecture. The decision prioritizes framework integration, a defined token lifecycle, and reduced token-lookup overhead while retaining Django's authorization mechanisms and application-level tenant isolation.
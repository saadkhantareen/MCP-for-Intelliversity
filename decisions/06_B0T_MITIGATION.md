# Google reCAPTCHA v3 for Bot Detection

**Status:** Accepted

## Context

Intelliversity is an AI-powered, multi-tenant University Management System built with React, Django REST Framework, and PostgreSQL.

The application exposes web interfaces and APIs for students, faculty members, and administrators. Public-facing operations, including login, registration, and password recovery, may be targeted by automated abuse.

AI-powered endpoints may also be vulnerable to automated requests that consume application resources and increase computational costs.

Authentication, authorization, and input validation are necessary but do not independently identify all potentially automated or abusive interactions.

The system therefore requires an additional mechanism to assess bot-related risk while minimizing unnecessary friction for legitimate users.

## Decision

We selected Google reCAPTCHA v3 as an additional bot-detection and risk-assessment mechanism.

The frontend obtains a reCAPTCHA token when a protected action is initiated and submits it to the Django backend.

The backend verifies the token with Google's verification service and evaluates the returned result, including the score and expected action, before deciding how to handle the request.

Application-specific policies determine whether a request is allowed, rejected, rate-limited, or subjected to additional verification.

reCAPTCHA supplements existing security controls and does not replace authentication, authorization, tenant isolation, or request throttling.

## Rationale

1. **Low user friction:** reCAPTCHA v3 assesses interactions without routinely requiring users to solve a CAPTCHA challenge.

2. **Risk-based assessment:** The score allows the application to make decisions based on the estimated risk associated with an interaction.

3. **Action-specific policies:** Different operations, such as login and registration, can be assessed separately.

4. **Backend enforcement:** Server-side token verification allows the application to validate the assessment before processing a protected operation.

5. **Protection against automated abuse:** The additional risk signal can help identify suspicious activity targeting authentication, registration, and other sensitive endpoints.

6. **Proportionate implementation:** The service adds a bot-detection layer without requiring the application to develop and maintain its own behavioral risk-analysis system.

## Alternatives considered

- **reCAPTCHA v2:** Provides checkbox-based and invisible challenge mechanisms. It was not selected because v3 offers score-based assessment without routinely interrupting legitimate users. Version 2 remains a viable alternative if explicit challenges become necessary.

- **Rate limiting:** Restricts request frequency and helps control resource consumption. It was not considered a complete replacement because request frequency alone does not determine whether an interaction is legitimate. Rate limiting remains a complementary security control.

- **Honeypot fields:** Provide a lightweight mechanism for detecting some simplistic automated form submissions. They were not selected as the primary solution because sophisticated bots can bypass them.

- **Email verification and multi-factor authentication:** Strengthen account verification and authentication, respectively. They address related but different security concerns and may be used alongside reCAPTCHA.

- **Cloudflare Turnstile:** Offers managed and non-interactive CAPTCHA alternatives. It remains a viable option if future requirements favor its challenge model, privacy characteristics, or operational features.

- **hCaptcha:** Provides an alternative third-party CAPTCHA service. It was not selected because the current implementation uses Google's risk-assessment model and does not currently require a different provider.

- **Web application firewall and bot management:** Can filter suspicious traffic before it reaches the application. These controls remain potential additions for production deployment rather than direct substitutes for application-level risk assessment.

- **No CAPTCHA:** Relies on controls such as authentication, rate limiting, account verification, and monitoring. This may be appropriate for low-risk or restricted environments, but it may provide insufficient protection for publicly exposed operations targeted by automated abuse.

## Consequences

The decision provides an additional signal for assessing potentially automated requests while minimizing routine user interaction.

However, reCAPTCHA v3 does not guarantee that a request is human or legitimate. False positives and false negatives remain possible, and score thresholds require appropriate calibration.

The integration introduces a dependency on Google's verification service and requires consideration of service availability, request latency, and applicable privacy requirements.

The application must define appropriate behavior when verification fails or the external service is unavailable.

The implementation also requires secure management of the secret key and backend verification of token validity, action, and relevant deployment details.

## Security requirements

- Verify reCAPTCHA tokens on the backend before processing protected actions.
- Keep the secret key outside frontend code and public repositories.
- Verify the expected action and relevant hostname information.
- Respect token expiration and single-use verification restrictions.
- Use action-specific thresholds based on the operation's risk and observed traffic.
- Define explicit failure-handling policies for verification errors and service outages.
- Apply rate limiting independently of reCAPTCHA.
- Retain JWT authentication, role-based authorization, object-level permissions, and tenant-isolation controls.
- Avoid revealing sensitive account information through error responses.
- Monitor verification failures, score distributions, false positives, and suspicious traffic.
- Assess accessibility, privacy, and third-party service requirements.

## Conclusion

Google reCAPTCHA v3 was selected as a proportionate bot-detection mechanism for Intelliversity because it provides score-based risk assessment with minimal routine user friction.

The decision complements the application's existing authentication and authorization architecture while introducing additional protection against automated abuse.

Its effectiveness depends on correct backend verification, appropriate risk thresholds, explicit failure-handling policies, and complementary security controls such as rate limiting.
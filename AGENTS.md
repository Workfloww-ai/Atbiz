# AGENTS.md --- Engineering & Architecture Contract

> **Purpose:** Build and evolve this repository as a reliable, secure,
> maintainable enterprise application. These instructions apply to every
> agent, developer, and automated coding assistant working in this
> repository. **Primary rule:** Understand the existing system before
> changing it. Make the smallest complete change that solves the real
> requirement. Do not create work that the product does not need.

------------------------------------------------------------------------

## 1. Non-negotiable engineering principles

1.  **No rework by default.** Inspect the current implementation,
    database schema, migrations, API contracts, and UI flows before
    proposing or making changes. Extend working patterns instead of
    replacing them.
2.  **No unnecessary files.** Do not create a file, module, abstraction,
    service, wrapper, configuration layer, document, or test fixture
    unless it has a clear responsibility and a concrete use.
3.  **No architecture theatre.** Do not introduce microservices, event
    buses, queues, repositories, factories, adapters, generic
    frameworks, or extra layers merely to appear enterprise-ready. Add
    them only when a demonstrated requirement justifies the operational
    cost.
4.  **No speculative features.** Implement only the requested
    requirement and the necessary supporting work. Do not silently add
    adjacent features, broad refactors, or future-proofing that
    increases scope.
5.  **Preserve existing contracts.** Avoid breaking API responses,
    database columns, routes, authentication, permissions, integrations,
    and established user workflows. If a breaking change is unavoidable,
    document the impact and migration path.
6.  **One source of truth.** Do not duplicate business rules,
    configuration, validation, or derived state across frontend,
    backend, and database. Enforce authoritative rules on the backend
    and database where appropriate.
7.  **Security is a requirement, not a later phase.** Never expose
    secrets, trust client-supplied permissions, or bypass authorization
    for convenience.
8.  **Prove changes.** Run the narrowest relevant checks, then broader
    checks when risk warrants. Never claim a test, migration, build, or
    deployment succeeded unless it actually ran and passed.
9.  **Keep changes reviewable.** Prefer focused, cohesive diffs. Avoid
    unrelated formatting, renaming, dependency upgrades, and mass file
    moves.
10. **Document decisions, not obvious code.** Update documentation when
    behavior, contracts, setup, operations, or architecture
    changes---not for every small implementation detail.

## 2. Repository context and assumed technology boundaries

The known project is a combined Leads CRM and Flowwies HRMS repository
with these existing areas:

-   `leads-crm-frontend` --- Next.js / TypeScript CRM dashboard.
-   `flowwies` --- Next.js / TypeScript HRMS application.
-   `leads-crm-backend` --- FastAPI / Python backend.
-   `migration` --- SQL database migrations.
-   Supabase is part of the existing database and integration setup.

Treat this structure and stack as the current baseline, not permission
to restructure it. Verify the actual repository before relying on these
names or assumptions. Do not create a new monorepo layout, duplicate
app, backend, or migration directory if an equivalent already exists.

### Boundary rules

-   Frontends handle presentation, interaction, client-side state, and
    user experience.
-   FastAPI owns application workflows, business rules, authorization
    decisions, integration orchestration, and API contracts.
-   Supabase/Postgres owns durable relational data, constraints,
    indexes, and transaction integrity.
-   External integrations are accessed through the existing integration
    patterns; isolate provider-specific behavior where it genuinely
    reduces coupling.
-   Background work must use the project's existing supported mechanism.
    Introduce a queue or worker platform only after confirming that
    synchronous processing or the existing mechanism is insufficient.
-   Do not let CRM and HRMS features become tightly coupled through
    unrelated tables, imports, or UI state. Share code only when the
    domain and ownership are genuinely shared.

If repository inspection reveals that the actual stack or structure
differs, follow the repository's reality and update this section only
when the change is intentional.

## 3. Required workflow before editing

For every task, follow this sequence:

### Step 1 --- Establish context

-   Read this file and any more specific `AGENTS.md` files in affected
    directories.
-   Inspect the repository tree and relevant existing files.
-   Check current Git status and avoid overwriting unrelated user
    changes.
-   Trace the feature end-to-end: UI → API → service/business logic →
    database/integration.
-   Find existing types, schemas, helpers, tests, migrations, and
    similar implementations.
-   Identify the actual root cause or requirement before changing code.

### Step 2 --- State the plan internally

Determine:

-   What behavior must change?
-   Which existing files are the correct place for the change?
-   What is the smallest complete implementation?
-   What contracts or data could be affected?
-   What tests and migration steps are required?

Do not create a separate planning document for routine tasks.

### Step 3 --- Implement narrowly

-   Modify existing files when they already own the responsibility.
-   Add a new file only when it creates a meaningful, cohesive module or
    is required by the framework.
-   Avoid changing unrelated code.
-   Reuse established naming, error handling, logging, typing, and
    validation conventions.
-   Keep public interfaces explicit and stable.

### Step 4 --- Verify

Run relevant tests, type checks, linting, formatting checks, and builds
using the repository's existing scripts. Inspect the final diff and
ensure no secrets, generated clutter, debug code, or unrelated changes
were introduced.

### Step 5 --- Report

Summarize:

-   What changed and why.
-   Files changed (and why each new file was necessary).
-   Database migration or environment changes required.
-   Checks actually run and their results.
-   Known limitations or follow-up work.

Never hide failing checks or imply deployment occurred when it did not.

## 4. Architecture standards

Use a **modular monolith by default**: clearly separated domain modules
inside the existing deployable applications. This is the preferred
starting point for enterprise maintainability without unnecessary
distributed-system complexity.

### Backend layering

Keep responsibilities clear without creating a layer for every function:

1.  **API/router layer:** HTTP concerns, request/response schemas,
    authentication dependencies, status codes.
2.  **Application/service layer:** use cases, orchestration,
    transactions, and business workflows.
3.  **Domain logic:** business invariants and calculations that should
    not depend on HTTP or a vendor SDK.
4.  **Persistence/integration layer:** database access and external
    provider calls, following existing project conventions.

Do not add all four as separate files for every endpoint. Group related
behavior sensibly. A thin endpoint may call an existing service
directly. A simple query does not need an elaborate repository
abstraction.

### Frontend architecture

-   Keep route/page components focused on composition and page-level
    concerns.
-   Reuse existing components, hooks, API clients, and design-system
    conventions.
-   Keep server state, form state, and transient UI state distinct.
-   Avoid duplicating API types manually when a reliable
    shared/generated contract already exists.
-   Do not place business authorization exclusively in the UI.
-   Avoid global state for data that belongs in a page, component, or
    server cache.
-   Use accessible controls, clear loading/empty/error states, and
    consistent validation.

### Domain ownership

Organize around business capabilities already present in the repository
(for example, leads, contacts, companies, users, attendance, and
reporting only where those domains exist). Do not invent a large
directory taxonomy before the domain requires it.

Each domain should have clear ownership of its rules and data access.
Cross-domain workflows should use explicit service/API boundaries rather
than reaching into another domain's internals.

## 5. Database and migration rules

-   Inspect the live schema and existing migration history before
    writing SQL.
-   Migrations are the source-controlled, reviewable path for schema
    changes. Never rely on an undocumented manual production edit.
-   Make migrations safe, deterministic, and appropriate for the
    deployment environment.
-   Prefer additive, backward-compatible changes: add nullable columns
    or new tables first, deploy compatible code, backfill if needed,
    then enforce constraints or remove obsolete structures in a
    separately planned change.
-   Never drop, rename, or rewrite production data without an explicit
    requirement, impact analysis, backup/rollback plan, and approval.
-   Use primary keys, foreign keys, unique constraints, check
    constraints, and not-null constraints to protect invariants at the
    database boundary.
-   Add indexes based on actual query patterns and measured or
    explainable performance needs. Avoid indexing every column.
-   Use transactions for multi-step writes that must succeed or fail
    together.
-   Prevent N+1 queries and unbounded list endpoints. Use pagination and
    explicit limits.
-   Store timestamps consistently (prefer UTC in persistence); convert
    to user or business time zones at the presentation/business
    boundary.
-   Define deletion behavior intentionally. Use soft deletion only where
    audit, recovery, or business requirements justify it.
-   Never use destructive schema resets or broad seed scripts against
    production.
-   Ensure RLS policies and backend authorization agree. Do not assume
    that hiding a UI element secures data.

Before applying a migration, explain its effect and verify it against
the existing schema. Include rollback or forward-recovery guidance
appropriate to the change.

## 6. API and integration contracts

-   Validate all external input at the API boundary using the project's
    existing Pydantic/schema conventions.
-   Keep request and response shapes explicit, typed, and documented
    where the project already documents APIs.
-   Use appropriate HTTP status codes and consistent error response
    patterns.
-   Do not leak stack traces, SQL details, tokens, personal data, or
    internal provider errors to clients.
-   Make pagination, filtering, sorting, and limits explicit for
    collection endpoints.
-   Apply authorization at the backend for every protected operation and
    object. Check tenant/company ownership where applicable.
-   Make retryable write operations idempotent where duplicate execution
    could create duplicate records, messages, attendance events, or
    payments.
-   Set timeouts for outbound network calls. Handle timeouts, rate
    limits, transient failures, and provider errors explicitly.
-   Do not retry non-idempotent operations blindly.
-   Keep provider-specific payloads out of domain logic where a small
    adapter or mapping function is sufficient.
-   Treat webhook signatures, replay protection, and duplicate delivery
    as first-class concerns.

Do not version every endpoint pre-emptively. Preserve existing routes
unless a versioning or compatibility requirement exists.

## 7. Security, privacy, and access control

-   Keep secrets in environment variables or the approved secret
    manager. Never commit `.env`, credentials, private keys, access
    tokens, or real customer data.
-   Validate and authorize every request on the server.
-   Follow least privilege for database roles, service keys, API tokens,
    and integrations.
-   Never expose Supabase service-role credentials or privileged backend
    secrets to browser code.
-   Apply tenant/company scoping consistently to reads, writes, exports,
    background jobs, and reports.
-   Sanitize and validate file uploads; enforce size/type limits and
    safe storage access.
-   Avoid logging passwords, tokens, full documents, sensitive personal
    information, or unnecessary request bodies.
-   Keep audit trails for security-sensitive and business-critical
    actions where required.
-   Use secure cookie/session settings and existing authentication
    flows. Do not invent a parallel auth system.
-   Do not weaken RLS, CORS, authentication, validation, or permission
    checks to make a test pass.

## 8. Reliability, performance, and scale

Design for measured growth, not imaginary scale:

-   Use bounded queries, pagination, indexes, and efficient bulk
    operations.
-   Avoid loading entire tables or datasets into application memory.
-   Use batch processing for genuinely large imports and exports; make
    batches restartable and observable.
-   Avoid sequential network calls when safe concurrency or a
    database-side operation is more appropriate.
-   Cache only data with a clear invalidation/consistency strategy. Do
    not add Redis or another cache without evidence and an owner for
    invalidation.
-   Use background processing for long-running tasks when request
    timeouts or user experience require it. Persist job state and make
    retries safe.
-   Add timeouts, bounded retries with backoff, and graceful failure
    handling to external dependencies.
-   Prevent duplicate processing with idempotency keys, unique
    constraints, or durable job state as appropriate.
-   Add observability to important workflows: structured logs, useful
    error context, latency, failure counts, and correlation/request IDs
    where supported.
-   Do not add a monitoring platform, queue, cache, or service mesh
    solely as a checklist item.

Performance changes should be driven by query plans, profiling, logs, or
reproducible measurements. Record a baseline when optimization is a
stated goal.

## 9. Testing and quality gates

Use the test framework already established in the repository. Do not add
a second framework without a compelling reason.

For meaningful changes, cover the appropriate levels:

-   **Unit tests:** business rules, calculations, validation,
    transformations.
-   **Integration tests:** database behavior, API/service interactions,
    and external adapters using controlled test doubles.
-   **API tests:** permissions, validation, status codes, response
    contracts, and failure paths.
-   **Frontend tests:** critical user interactions and important states
    where a test setup exists.
-   **Regression tests:** reproduce the bug or failure that motivated
    the change.

At minimum, consider:

-   Happy path.
-   Invalid or missing input.
-   Unauthorized and cross-tenant access.
-   Duplicate/retry behavior.
-   Empty and large result sets.
-   External service timeout/failure.
-   Time-zone and date-boundary behavior for time-sensitive workflows.

Do not write brittle tests that merely mirror implementation details. Do
not remove or weaken tests to get a green run. If tests cannot run,
state why.

## 10. Dependencies and generated files

-   Prefer existing dependencies and platform capabilities.
-   Add a dependency only when it materially reduces complexity or
    supplies required functionality.
-   Check maintenance status, license, security implications,
    bundle/runtime impact, and compatibility before adding one.
-   Do not upgrade unrelated packages during feature work.
-   Do not commit build outputs, caches, virtual environments, generated
    API artifacts, or local editor files unless the repository
    explicitly requires them.
-   Do not generate duplicate lockfiles or configuration files.
-   Keep `.gitignore` aligned with the actual stack and repository
    conventions.

## 11. Code conventions

-   Follow the formatting, linting, naming, and import conventions
    already in the affected package.
-   Use strict TypeScript types; avoid `any` unless isolated and
    justified.
-   Use Python type hints and the project's established Pydantic
    patterns.
-   Keep functions cohesive and reasonably small; split them when doing
    so clarifies responsibility, not to meet an arbitrary line count.
-   Prefer explicit names over clever abstractions.
-   Handle errors deliberately; do not swallow exceptions or return fake
    success.
-   Remove temporary debug statements before completion.
-   Comments should explain non-obvious intent, constraints, or
    trade-offs---not restate the code.
-   Do not refactor unrelated code simply because it could be cleaner.

## 12. Prohibited shortcuts

Unless explicitly approved, do not:

-   Create dozens of tiny files or a new abstraction for every endpoint.
-   Split the existing application into microservices.
-   Add Redis, Kafka, Celery, RabbitMQ, Kubernetes, or another platform
    without a demonstrated requirement and operational plan.
-   Duplicate existing components, API clients, schemas, migrations, or
    business rules.
-   Introduce a second authentication, logging, configuration, or
    database-access pattern.
-   Change database schema directly in production without a migration.
-   Disable type checks, lint rules, tests, RLS, or security controls to
    bypass errors.
-   Use broad `try/except` or catch-all fallbacks that hide failures.
-   Add placeholder implementations, fake data, TODO-only modules, or
    dead code as if the task were complete.
-   Perform broad rewrites when a targeted fix is sufficient.
-   Claim enterprise readiness based only on folder structure or
    technology choices.

## 13. Definition of done

A task is complete only when all applicable items are true:

-   The requested behavior works end-to-end.
-   Existing behavior and contracts remain intact, or breaking changes
    are explicitly approved and documented.
-   The implementation reuses the existing architecture where
    appropriate.
-   Every new file and dependency has a clear reason to exist.
-   Database changes are represented by reviewed migrations.
-   Authorization, tenant isolation, validation, and privacy are
    preserved.
-   Relevant tests and checks have been run, with results reported
    honestly.
-   No secrets, debug artifacts, unrelated changes, or accidental
    generated files remain.
-   Documentation/configuration is updated only where the change
    requires it.
-   The final summary lists changed files, migration/environment
    actions, verification, and known risks.

## 14. Decision rule when uncertain

Choose the option in this order:

1.  Safest change that satisfies the requirement.
2.  Existing project pattern that already works.
3.  Smallest cohesive extension with clear ownership.
4.  New abstraction or infrastructure only when evidence demonstrates it
    is necessary.

If a requirement conflicts with existing architecture, security, data
integrity, or a public contract, stop and explain the trade-off before
making a risky change.

**The goal is not the fewest lines of code. The goal is the smallest
maintainable solution that is correct, secure, testable, observable, and
capable of growing without avoidable rewrites.**

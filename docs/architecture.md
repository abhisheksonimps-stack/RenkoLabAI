# Architecture Overview

RenkoLab AI is designed as a clean enterprise application foundation using:

- Clean Architecture
- Domain-Driven Design
- Hexagonal Architecture
- CQRS-ready command/query separation
- Dependency injection and repository abstraction
- Event-driven integration points

## Backend Layers

- `app/api` — HTTP API layer and request/response schemas
- `app/application` — domain application services and use cases
- `app/domain` — domain models and business invariants
- `app/infrastructure` — persistence, messaging, and external adapters
- `app/plugins` — extension surface for new analytics or exchange adapters
- `app/events` — event definitions and dispatching
- `app/workers` — background scheduling and processing

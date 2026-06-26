# RenkoLab AI

RenkoLab AI is an enterprise-grade quantitative trading platform foundation built with modern Python and TypeScript technologies.

> This repository contains only the production-grade software foundation. No trading strategy implementations are included.

## Architecture

- FastAPI backend
- React + TypeScript frontend
- PostgreSQL database
- Redis cache/event bus
- SQLAlchemy 2.x + Alembic
- Pydantic v2
- Clean Architecture / DDD / Hexagonal
- CQRS-ready service layer
- Plugin-based extension surface
- Event-driven integration points

## Repository Layout

- `backend/` — Python application code
- `frontend/` — React user interface
- `deployment/` — deployment manifests and infrastructure guidance
- `docs/` — architecture and onboarding documentation
- `research/` — research notes and project experimentation
- `datasets/` — curated dataset storage and ingestion metadata
- `scripts/` — tooling entrypoints for setup, validation, and automation
- `tests/` — integration and unit test scaffolding

## Getting Started

1. Copy `.env.example` to `.env`
2. Build containers:
   ```bash
   docker compose up --build
   ```
3. Backend: `http://localhost:8000`
4. Frontend: `http://localhost:3000`

## Development

- Backend service: `backend/app/main.py`
- Frontend app entrypoint: `frontend/src/main.tsx`

## Notes

This project is designed as a foundation for institutional software; it is not a trading bot and does not include production trading logic.

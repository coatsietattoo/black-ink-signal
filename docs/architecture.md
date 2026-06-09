# Architecture Overview

## Components
- FastAPI local backend
- SQLite database
- Shared Python core package
- Reddit public connector
- Electron desktop app

## Flow
1. Connector fetches recent public Reddit items
2. Items are normalized into a common lead shape
3. Scoring engine assigns a lead score
4. Leads are stored in SQLite
5. Desktop app reads from backend API and renders live feed
6. Operator manually updates review/contact status

## Initial constraints
- single-operator desktop mode
- local SQLite only
- no automated outbound messaging
- Reddit-only ingestion for MVP v1

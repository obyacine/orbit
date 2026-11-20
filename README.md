# Orbit — AI project-management agent

> Hackathon project · *AI for Work and Business*
>
> *Give us your project brief. We handle the paperwork, watch the project and draft the reports. You make the decisions.*

Orbit is a self-hosted project-management platform with a built-in AI agent. Teams track their work as usual
(work items, sprints, modules, documents). The agent compares that work with what was validated at kick-off
(the **baseline**), detects drifts as soon as they appear, and drafts the whole reporting chain:
**Team Lead → Project Manager → Steering Committee**.

- **No method imposed.** The PM picks how the project is prioritized (MoSCoW, Kano, RICE, WSJF, ICE, value/effort,
  native priority or custom labels) and run (Scrum, Kanban, Waterfall, hybrid). Rules and reports adapt.
- **Numbers are computed, never generated.** Percentages, velocity and delays come from tested Python code.
  The LLM only turns computed JSON into prose.
- **Humans stay in charge.** Every report is a draft until a person approves it.
- **Works without AI.** If the LLM is unavailable, reports fall back to deterministic templates.

---

## Table of contents

1. [How it works](#1-how-it-works)
2. [The platform](#2-the-platform)
3. [The AI agent](#3-the-ai-agent)
4. [How the agent works with the platform](#4-how-the-agent-works-with-the-platform)
5. [Project methods](#5-project-methods)
6. [Getting started](#6-getting-started)
7. [Agent API](#7-agent-api)
8. [Tests](#8-tests)
9. [Repository layout](#9-repository-layout)
10. [Status and roadmap](#10-status-and-roadmap)
11. [License](#11-license)

---

## 1. How it works

| | Module 1 — The contract | Module 2 — Enforcing the contract |
|---|---|---|
| **Input** | A raw project brief | The live state of the project |
| **What the agent does** | Turns the brief into formal documents: business case, charter, prioritization table, risk register, stakeholder map, communication plan | Measures progress, applies anomaly rules against the baseline, drafts reports |
| **Human step** | The PM edits and validates → the **baseline** is frozen and versioned | The Team Lead / PM reviews, edits and approves each report |
| **Output** | Work items, modules, milestones and labels created in the platform | Progress report, situation report, anomaly register 🔴 🟡 🔵 |

> *Module 1 creates the contract. Module 2 enforces it.*

---

## 2. The platform

The platform is where the team works day to day. It is a monorepo of independent services behind a single
reverse proxy.

```
                     ┌──────────────────── Browser ────────────────────┐
                     │  web (main app)    space (public)    admin      │
                     └────────┬───────────────────────────────────────┘
                              │ HTTPS / WebSocket
                      ┌───────▼────────┐
                      │ proxy (Caddy)  │  :80 / :443
                      └─┬─────┬─────┬──┘
         /api/*, /auth/*│     │     │ /live/*
               ┌────────▼─┐   │   ┌─▼──────────┐
               │   api    │   │   │    live    │  real-time collaboration
               │ (Django) │   │   │ (Node/Yjs) │
               └┬───┬───┬─┘   │   └────────────┘
     ┌──────────┘   │   └──────────────┐
┌────▼──────┐ ┌─────▼────┐ ┌───────────▼┐ ┌──────────┐
│PostgreSQL │ │  Valkey  │ │  RabbitMQ  │ │  MinIO   │
│  (data)   │ │ (cache)  │ │  (queue)   │ │ (files)  │
└───────────┘ └──────────┘ └─────┬──────┘ └──────────┘
                           ┌─────▼──────────────┐
                           │ worker + scheduler │  Celery
                           └────────────────────┘
```

### Services

| Service | Stack | Role |
|---|---|---|
| `apps/web` | React 19, React Router, MobX, Tailwind | Main application (`:3000`) |
| `apps/space` | React | Public, read-only boards (`/spaces`) |
| `apps/admin` | React | Instance administration (`/god-mode`): SMTP, sign-in methods, AI keys |
| `apps/api` | Python, Django, Django REST Framework | REST API, authentication, business logic (`:8000`) |
| `apps/live` | Node, Express, Hocuspocus, Yjs | Real-time collaborative editing of documents (`:3100`) |
| `apps/proxy` | Caddy | Routes `/api`, `/auth`, `/live`, `/spaces`, `/god-mode`; automatic HTTPS |
| worker / scheduler | Celery + RabbitMQ | Background and periodic jobs |
| `packages/*` | TypeScript | Shared code: types, constants, API services, rich-text editor, i18n, UI blocks |

### Data model

Everything is scoped **Workspace → Project → Work item**.

- A **work item** has a state, priority, assignees, labels, dates, an estimate, a parent (sub-items) and relations
  (*blocks*, *blocked by*, *duplicate of*…). Readable IDs such as `BANK-12` come from a per-project sequence.
- **Cycles** are time boxes (sprints or milestones). **Modules** group work items into epics or phases.
- **Pages** are collaborative documents. **Views** are saved filters. **Intake** collects incoming requests.
- All records use UUID keys, record who created / updated them, and are soft-deleted before a nightly purge.

### Request lifecycle

Example: a card is dragged from *Todo* to *In Progress* on the board.

1. The MobX store updates immediately (optimistic UI).
2. The web app sends `PATCH /api/workspaces/{slug}/projects/{id}/issues/{issue}/` with the session cookie.
3. The proxy forwards it to Django. The session is checked, then the role (`Admin` 20, `Member` 15, `Guest` 5).
4. The change is saved in PostgreSQL and the API answers at once.
5. An activity job is queued in RabbitMQ. A Celery worker writes the activity history, the notifications and the
   **webhooks**. Webhooks are what the AI agent listens to (see §4).

### Background jobs

- **Event-driven:** activity history, notifications, webhooks, e-mails (invitations, magic codes), exports.
- **Scheduled:** e-mail digests every 5 minutes; nightly purge of deleted items, auto-archive, cleanup of expired
  exports and unfinished uploads.

### Real-time collaboration

Documents are Yjs CRDTs edited with a Tiptap editor. Browsers connect to `live` over WebSocket; the server
authenticates the session against the API, merges changes from every client, and saves the document (binary,
HTML and JSON) back to the API every 10 seconds. A Redis extension lets several `live` instances scale out.

### Files

Uploads use **pre-signed URLs**: the API issues an upload URL, the browser sends the file straight to MinIO
(S3-compatible), then confirms. The API never streams file content.

---

## 3. The AI agent

The agent lives in [`ai-service/`](./ai-service): a separate **FastAPI** service (Python 3.12) using **Google
Gemini** for writing.

```
         platform API (/api/v1)
                 │
         ┌───────▼────────┐
         │ plane_client   │  thin HTTP client (X-Api-Key)
         └───────┬────────┘
         ┌───────▼────────┐
         │   snapshot     │  normalized, tracker-agnostic view of a project
         └───────┬────────┘
         ┌───────▼────────┐
         │   methods      │  PM's method → every item gets a common tier
         └───────┬────────┘
         ┌───────▼────────┐
         │   metrics      │  % done, velocity / throughput, WIP, milestones, coverage   ← pure Python
         └───────┬────────┘
         ┌───────▼────────┐
         │    rules       │  deterministic anomalies 🔴 🟡 🔵, each tied to what it violates
         └───────┬────────┘
         ┌───────▼────────┐
         │   reports      │  structure + numbers from code, narrative from the LLM (or a template)
         └───────┬────────┘
         ┌───────▼────────┐
         │  db (SQLite)   │  reports, approvals, project methods — outside the platform's schema
         └────────────────┘
```

### Design principles

| Principle | Where it is enforced |
|---|---|
| The LLM never computes a number | `module2/metrics.py` and `module2/rules.py` contain no LLM call. `llm.py` only receives already-computed JSON, with the instruction *"invent no figure, name or fact"* and temperature 0.3 |
| Every anomaly is traceable | Each anomaly carries a `baseline_ref` (e.g. `MoSCoW / Must-Have`, `Phase / Specifications`) |
| AI is optional | If `GEMINI_API_KEY` is missing or a call fails, `llm.write()` returns `None` and reports use templates. `/health` reports `"llm": "templates"` |
| Human validation | Reports are saved as `draft`; `POST /reports/{id}/approve` records who approved and the edited text |
| Chained reporting | The situation report (PM → Steering Committee) is built on the latest **approved** progress report |
| Tracker-agnostic | Downstream code only sees the snapshot; supporting another tracker means rewriting `plane_client.py` |
| No change to the platform's database | Orbit's data is stored in its own SQLite file, so no platform migration is needed |

### What the agent produces

**Progress report — Team Lead → PM**
Overall progress, progress per epic, velocity or throughput, work in progress, blocked items with the *reason*
(taken from the item's last comment), deadlines at risk, and a written summary.

**Situation report — PM → Steering Committee**
Project weather 🟢 🟡 🔴, plan vs actual per sprint / phase / milestone, coverage per priority level,
anomalies of the period, executive summary, recommendations and decisions expected.

**Anomaly register**

| Severity | Rule |
|---|---|
| 🔴 Critical | Critical item unassigned less than 7 days before its deadline |
| 🔴 Critical | Critical item late or blocked |
| 🔴 Critical | Phase past its end date and not finished (missed gate) — Waterfall / hybrid |
| 🟡 Warning | Important item late |
| 🟡 Warning | Velocity (Scrum) or throughput (Kanban) down by more than 20 % |
| 🟡 Warning | WIP limit exceeded — Kanban / hybrid |
| 🟡 Warning | Sprint / phase / milestone at risk: % done lower than % of time elapsed |
| 🟡 Warning | Sprint past its end date and not finished — Scrum / hybrid |
| 🔵 Info | Optional item postponed |
| 🔵 Info | Active items with no priority in the chosen method |

Example output (Waterfall project prioritized with Kano):

```
🔴 Basique « RH-2 » en retard de 4 j          (réf. Kano / Basique)
🔴 Phase « Spécifications » terminé(e) depuis 5 j à 50 % seulement
🟡 Phase « Développement » à risque : 0 % réalisé pour 17 % du temps écoulé
```

> Reports are written in French, the language of the target users.

---

## 4. How the agent works with the platform

```
 ┌──────────────────────── Orbit platform ────────────────────────┐
 │                                                                 │
 │  web app ──(session)──► api ──(X-Orbit-Token)──┐                │
 │   "AI Agent" tab         ▲ proxy endpoint       │                │
 │                          │                      ▼                │
 │   work items, cycles,    │ /api/v1 (X-Api-Key)  ai-service ──► Gemini
 │   modules, comments  ◄───┴──────────────────────┤ (FastAPI)      │
 │                                                 │                │
 │   webhooks (worker) ───────────────────────────►│                │
 │                                                 ▼                │
 │                                          SQLite: reports,        │
 │                                          approvals, methods      │
 └─────────────────────────────────────────────────────────────────┘
```

1. **Reading the project.** The agent calls the platform's public REST API (`/api/v1/`) with a workspace API key:
   work items, states, labels, cycles, modules, relations and comments. It never reads the database directly.
2. **Triggers.** An analysis or a report runs on demand from the UI, on a schedule, or when a platform webhook
   signals a change.
3. **Security.** The browser never talks to the agent. It calls a platform endpoint that checks the user's
   session, which then calls the agent with a shared secret (`X-Orbit-Token`).
4. **Writing back.** In Module 1, the validated baseline is pushed through the same API: labels, modules
   (epics / phases), cycles (sprints / milestones) and work items. Approved reports can be published as pages.
5. **Ownership.** The platform stays the single source of truth for the work; the agent owns the baseline, the
   reports and the anomaly register.

| Agent concept | Platform object |
|---|---|
| Epic | Module |
| Phase (Waterfall) | Module with start and end dates |
| Sprint / milestone | Cycle |
| Priority | Label (`Must`, `Basique`, `WSJF:13`…) or native priority field |
| Blocked item | `blocked_by` relation or `Bloqué` label; last comment = reason |
| Done / in progress | State group `completed` / `started` |

---

## 5. Project methods

Each project has a method chosen by the PM (`PUT /projects/{id}/method`). Code: [`ai-service/app/methods.py`](./ai-service/app/methods.py).

**Prioritization**

| Method | What the team puts on work items |
|---|---|
| MoSCoW | Labels `Must` / `Should` / `Could` / `Won't` |
| Kano | `Basique` / `Performance` / `Enthousiasmant` / `Indifférent` |
| Native priority | Nothing: the Urgent / High / Medium / Low field is used |
| RICE · WSJF (SAFe) · ICE | A score label, e.g. `WSJF:13` |
| Value / effort matrix | `Quick win` / `Gros projet` / `Bouche-trou` / `Ingrat` |
| Custom | The PM's own labels, each mapped to a level |

**Delivery**

| Method | What is measured |
|---|---|
| Scrum | Sprints (cycles), velocity, sprint at risk or overdue |
| Kanban | Throughput, WIP against a limit, no sprints |
| Waterfall | Phases (dated modules), missed phase gates |
| Hybrid | Phases, sprints, velocity, and WIP if a limit is set |

Every prioritization method is translated into **four common levels**: *critical, important, optional, excluded*.
Score-based methods use relative levels (top 20 % critical, next 30 % important) or absolute thresholds set by
the PM. Rules are written once on these levels, so they work with every method, while messages keep the team's
own vocabulary. Without a saved choice, a project uses **Hybrid + MoSCoW**.

---

## 6. Getting started

Requirements: Docker, Node ≥ 22, pnpm, [uv](https://docs.astral.sh/uv/).

### Platform

```bash
./setup.sh                                          # generates the .env files
docker compose -f docker-compose-local.yml up -d    # PostgreSQL (:5433), Valkey, RabbitMQ, MinIO, API (:8000)
pnpm install
pnpm dev                                            # web :3000, admin :3001, live :3100
```

1. http://localhost:3001/god-mode — create the instance admin account.
2. http://localhost:3000 — create a workspace and a project.
3. Workspace settings → API tokens — generate the key used by the agent.

### AI agent

```bash
cd ai-service
cp .env.example .env        # set PLANE_API_KEY, PLANE_WORKSPACE_SLUG, GEMINI_API_KEY (optional)
uv sync
uv run python -m scripts.seed_demo          # optional: realistic demo project with planted drifts
uv run uvicorn app.main:app --port 8001
```

| Variable | Purpose |
|---|---|
| `PLANE_BASE_URL` | Platform API URL (`http://api:8000` inside Docker) |
| `PLANE_API_KEY` | Workspace API token |
| `PLANE_WORKSPACE_SLUG` | Workspace to read |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | LLM for the narrative parts (optional) |
| `DATABASE_PATH` | Agent's SQLite file |
| `ORBIT_INTERNAL_TOKEN` | Shared secret expected from the platform backend |

### Production

`docker-compose.yml` runs the whole platform; Kubernetes and an all-in-one image are available in
[`deployments/`](./deployments). The agent ships with its own [`Dockerfile`](./ai-service/Dockerfile) (port 8001).

---

## 7. Agent API

All project endpoints require the `X-Orbit-Token` header.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Service status and LLM mode (`gemini` or `templates`) |
| `GET` | `/methods` | Catalog of prioritization and delivery methods |
| `GET` / `PUT` | `/projects/{id}/method` | Read / set the PM's method for a project |
| `GET` | `/projects/{id}/snapshot` | Normalized project data |
| `GET` | `/projects/{id}/analysis` | Metrics + anomaly register |
| `POST` | `/projects/{id}/reports/progress` | Draft progress report (Team Lead → PM) |
| `POST` | `/projects/{id}/reports/situation` | Draft situation report (PM → Steering Committee) |
| `GET` | `/projects/{id}/reports` | Report history (`?type=progress\|situation`) |
| `GET` | `/reports/{id}` | One report (JSON + Markdown) |
| `POST` | `/reports/{id}/approve` | Human approval, with the optionally edited text |

Interactive documentation: http://localhost:8001/docs

---

## 8. Tests

```bash
cd ai-service && uv run pytest          # metrics, rules, every method combination, reports, API
```

Platform backend tests run in Docker:

```bash
docker compose -f docker-compose-test.yml up --build --abort-on-container-exit --exit-code-from api-tests
```

---

## 9. Repository layout

```
.
├── ai-service/             AI agent (FastAPI)
│   ├── app/
│   │   ├── main.py         HTTP API
│   │   ├── methods.py      prioritization & delivery methods
│   │   ├── plane_client.py platform API client
│   │   ├── llm.py          Gemini wrapper with template fallback
│   │   ├── db.py           SQLite storage
│   │   ├── module1/        contract / baseline (in progress)
│   │   └── module2/        snapshot, metrics, rules, reports
│   ├── scripts/seed_demo.py
│   └── tests/
├── apps/
│   ├── web/                main web app
│   ├── space/              public boards
│   ├── admin/              instance administration
│   ├── api/                Django REST API, workers
│   ├── live/               real-time collaboration server
│   └── proxy/              Caddy reverse proxy
├── packages/               shared TypeScript libraries
├── deployments/            Docker, Kubernetes, all-in-one
└── docs/                   PRD.md, AGENT.md
```

Product and agent specifications: [`docs/PRD.md`](./docs/PRD.md), [`docs/AGENT.md`](./docs/AGENT.md).

---

## 10. Status and roadmap

| Area | Status |
|---|---|
| Module 2 — snapshot, metrics, anomaly rules | ✅ Done, tested |
| Progress and situation reports, approval flow | ✅ Done, tested |
| Methods chosen by the PM (8 prioritization × 4 delivery) | ✅ Done, tested |
| Demo data seeding | ✅ Done |
| "AI Agent" tab in the web app + backend proxy endpoint | 🚧 Next |
| Module 1 — brief → documents → frozen baseline → push to the platform | 🚧 In progress |
| Meeting minutes from transcripts, CI/CD signals | 📋 Planned |
| Pluggable LLM (local model option for full data sovereignty) | 📋 Planned |

---

## 11. License

Orbit is built on top of [Plane](https://github.com/makeplane/plane), © Plane Software, Inc. and contributors,
licensed under the **GNU AGPL-3.0**. Orbit is distributed under the same license — see [`LICENSE.txt`](./LICENSE.txt)
and [`COPYRIGHT.txt`](./COPYRIGHT.txt).

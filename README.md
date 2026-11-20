# Agent IA de pilotage de projet

> Projet hackathon « AI for Work and Business ».
> *Donnez-nous votre brief projet. On gère la paperasse, on surveille le projet, on rédige les rapports. Vous prenez les décisions.*

## Le principe

- **Module 1 — Le contrat** : un brief brut devient un package de documents formels (cas d'affaire, charte, MoSCoW, registre des risques, parties prenantes, plan de communication). Une fois validé par le CDP, il est figé comme **baseline**.
- **Module 2 — L'application du contrat** : l'agent lit l'état réel du projet (issues, cycles, CI/CD, réunions), le compare à la baseline, détecte les dérives et rédige la chaîne de reporting :
  - Rapport d'avancement — Team Lead → PM
  - Rapport de situation — PM → COPIL
  - PV de réunion et registre des anomalies (🔴 / 🟡 / 🔵)

## Architecture

```
Plane (gestion de projet)  ── API v1 + webhooks ──→  ai-service (FastAPI + Gemini)
  issues, cycles, modules,                              baseline, calculs, règles d'anomalies,
  labels MoSCoW, pages     ←── documents/rapports ───   rédaction des rapports
```

| Dossier | Rôle |
|---|---|
| `apps/web` | Frontend (React Router + Vite) — onglet « Agent IA » ajouté |
| `apps/api` | Backend Django de Plane (API `/api/v1/`) |
| `apps/admin` | Administration de l'instance (`/god-mode`) |
| `apps/live` | Collaboration temps réel de l'éditeur de pages |
| `packages/*` | Librairies partagées du frontend |
| `ai-service/` | Notre agent IA (à venir) |

## Lancer en local

Prérequis : Docker, Node ≥ 22, pnpm.

```bash
./setup.sh                                          # génère les fichiers .env
docker compose -f docker-compose-local.yml up -d    # DB (port 5433), Redis, MQ, MinIO, API :8000
pnpm install
pnpm dev                                            # web :3000, admin :3001, live :3100
```

1. http://localhost:3001/god-mode — créer le compte administrateur de l'instance
2. http://localhost:3000 — créer un workspace et un projet
3. Paramètres du workspace → API tokens — générer la clé utilisée par `ai-service`

## Licence et crédits

Ce projet est construit sur [Plane](https://github.com/makeplane/plane), © Plane Software, Inc. and contributors,
distribué sous licence **GNU AGPL-3.0** (voir [`LICENSE.txt`](./LICENSE.txt) et [`COPYRIGHT.txt`](./COPYRIGHT.txt)).
Nos modifications sont distribuées sous la même licence.

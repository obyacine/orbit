# Orbit — L'agent IA (`ai-service`)

> Plane **enregistre** le travail de l'équipe. L'agent le **compare** au contrat validé, **rédige** les rapports et **alerte** sur les dérives.
> Principe : *Module 1 crée le contrat. Module 2 l'applique.*

---

## 1. Rôle

L'`ai-service` est un serveur Python (FastAPI) séparé de Plane. Il :

1. génère les documents de lancement à partir d'un brief ;
2. stocke la **baseline** validée (le contrat projet) ;
3. surveille le projet en continu et tient le **registre des anomalies** ;
4. rédige la chaîne de reporting : Team Lead → PM → COPIL ;
5. rédige les **PV de réunion** et détecte les glissements de scope.

Il ne gère ni les tâches, ni les utilisateurs, ni les droits : c'est le rôle de Plane.

---

## 2. Architecture

```
Utilisateur → Plane web (:3000) → Plane API Django (:8000) ──proxy──→ ai-service (:8001) → Gemini
                                         ↑                                  │
                                         └──── API v1 (X-Api-Key) ──────────┘
                                         └──── webhooks (issue modifiée) ───→ ai-service
GitHub Actions ──── webhook (résultats CI) ─────────────────────────────────→ ai-service
```

| Règle | Raison |
|---|---|
| Le frontend n'appelle jamais l'ai-service directement : il passe par un proxy Django qui vérifie la session | Un seul système d'authentification |
| L'ai-service lit et écrit dans Plane **uniquement via l'API v1** | Il ne touche jamais la base de Plane, et le tracker reste interchangeable (Jira, GitHub Projects) |
| L'ai-service a sa propre base : `baselines`, `reports`, `anomalies` | Aucune migration Django |
| **Python calcule, le LLM rédige** | Les chiffres ne sont jamais inventés |
| Les anomalies sont détectées par des règles fixes en priorité, le LLM ne sert qu'aux transcripts | Fiabilité, pas de fausses alertes en démo |

---

## 3. Module 1 — Génération du contrat

### Flux

```
Brief brut (5 à 20 lignes)
  → Extraction (LLM) : nom, objectifs, parties prenantes, budget, dates, contraintes
  → 1 prompt spécialisé par document → JSON structuré
  → Le CDP édite section par section
  → Le CDP valide → BASELINE figée (versionnée)
  → Poussée dans Plane via l'API v1
```

### Documents générés

| Document | Contenu |
|---|---|
| Cas d'affaire | Problème, bénéfices attendus, coûts, ROI estimé |
| Charte projet | Périmètre, objectifs, budget, jalons, contraintes, gouvernance |
| Cartographie des parties prenantes | Liste + matrice influence / intérêt |
| Tableau MoSCoW | Must / Should / Could / Won't, chaque élément identifié (`M1`, `S3`…) |
| Registre des risques | Risque, probabilité, impact, sévérité, mitigation, responsable |
| Plan de communication | Qui reçoit quoi, à quelle fréquence, par quel canal |

### Ce qui est créé dans Plane à la validation

| Élément de la baseline | Objet Plane |
|---|---|
| Catégories MoSCoW | Labels `Must`, `Should`, `Could`, `Won't` |
| Lots fonctionnels | Modules (epics) |
| Jalons de la charte | Cycles (avec dates) |
| Éléments MoSCoW | Issues labellisées et rattachées à leur module |
| Documents | Pages Plane (lecture seule) |

Le **label MoSCoW sur chaque issue** est le lien entre le contrat et l'exécution.

---

## 4. Module 2 — Surveillance et reporting

### 4.1 Sources de données

| Stream | Source | Déclencheur |
|---|---|---|
| A — Tracker | API Plane v1 : issues, states, cycles, modules, relations, commentaires, activités | Webhook Plane + à la demande + planifié |
| B — Qualité | GitHub Actions : tests, builds, couverture | Webhook GitHub |
| C — Réunions | Transcript texte uploadé | Upload |

Endpoints Plane utilisés :

```
GET /api/v1/workspaces/{slug}/projects/{id}/work-items/
GET /api/v1/workspaces/{slug}/projects/{id}/states/
GET /api/v1/workspaces/{slug}/projects/{id}/cycles/      + /cycles/{c}/cycle-issues/
GET /api/v1/workspaces/{slug}/projects/{id}/modules/     + /modules/{m}/module-issues/
GET /api/v1/.../work-items/{issue}/relations/   /comments/   /activities/
```

### 4.2 Calculs (Python, déterministes)

| Indicateur | Calcul |
|---|---|
| % par epic | Issues au groupe `completed` / total du module |
| Vélocité | Issues passées en `completed` sur la période vs période précédente (via `activities`) |
| Bloqués | Relation `blocked_by` ou label `Bloqué` + dernier commentaire comme raison |
| Jalon à risque | Fin du cycle < 7 jours **et** % réalisé < % de temps écoulé |
| Couverture MoSCoW | Nombre de Must / Should terminés, en cours, en retard |
| Score de dérive | % de conformité à la baseline, pondéré par la sévérité des anomalies ouvertes |

### 4.3 Règles d'anomalies

| Sévérité | Règle | Source |
|---|---|---|
| 🔴 Critique | Issue `Must` non assignée à moins de 7 jours de son jalon | Tracker |
| 🔴 Critique | Issue `Must` en retard sur son jalon | Tracker |
| 🔴 Critique | Build cassé sur `main` | CI/CD |
| 🔴 Critique | Test échoué lié à une issue `Must` | CI/CD |
| 🔴 Critique | Suppression ou report d'un `Must` discuté sans entrée Intake (demande de changement) | Réunion |
| 🔴 Critique | Décision contredisant la charte validée | Réunion |
| 🟡 Avertissement | Issue `Should` en retard | Tracker |
| 🟡 Avertissement | Vélocité en baisse de plus de 20 % | Tracker |
| 🟡 Avertissement | Jalon proche avec dépendances incomplètes | Tracker |
| 🟡 Avertissement | Couverture de tests sous le seuil | CI/CD |
| 🔵 Info | `Could` déprioritisé | Tracker |
| 🔵 Info | Nouveau risque de faible probabilité mentionné | Réunion |

Chaque anomalie référence **l'élément de la baseline qu'elle viole** (ex. « MoSCoW → M2 »).

### 4.4 Rapport d'avancement — Team Lead → PM

| Section | Origine |
|---|---|
| % de complétion par epic | Calcul |
| Vélocité (cette semaine vs précédente) | Calcul |
| Éléments bloqués et leur raison | Calcul + commentaires |
| Jalons à venir à risque | Calcul |
| Synthèse rédigée | LLM, à partir du JSON calculé |

Flux : génération → le Team Lead relit et valide → enregistré en Page Plane → le PM est notifié.

### 4.5 Rapport de situation — PM → COPIL

| Section | Origine |
|---|---|
| Météo du projet 🟢🟡🔴 | Règles fixes |
| Plan vs réel (jalons baseline vs cycles) | Calcul |
| Couverture MoSCoW | Calcul |
| Risques actifs (sévérité mise à jour) | Baseline + anomalies |
| Anomalies de la période | Registre |
| Synthèse exécutive | LLM — validée par le PM |
| Recommandations et décisions attendues | LLM — validées par le PM |

Flux : déclenché par la validation du rapport d'avancement → le PM relit et ajuste → export PDF → envoi au COPIL.

### 4.6 PV de réunion

```
Transcript → extraction LLM : décisions, actions (responsable + échéance), risques, changements de scope
           → PV formaté
           → comparaison avec la baseline → anomalies éventuelles
           → risque déjà au registre ? → mise à jour plutôt que doublon
```

---

## 5. API de l'ai-service

| Route | Rôle |
|---|---|
| `POST /projects/{id}/brief` | Brief → documents (brouillon) |
| `PUT /projects/{id}/documents/{type}` | Édition d'un document par le CDP |
| `POST /projects/{id}/baseline/validate` | Fige la baseline et la pousse dans Plane |
| `POST /projects/{id}/reports/progress` | Génère le rapport d'avancement |
| `POST /projects/{id}/reports/status` | Génère le rapport de situation |
| `POST /reports/{id}/approve` | Validation humaine → Page Plane |
| `GET /reports/{id}/pdf` | Export PDF |
| `GET /projects/{id}/anomalies` | Registre + score de dérive |
| `POST /projects/{id}/transcripts` | Transcript → PV + anomalies |
| `POST /webhooks/plane` | Réévaluation des règles à chaque changement |
| `POST /webhooks/github` | Résultat CI/CD → anomalies |

## 6. Données

| Table | Champs principaux |
|---|---|
| `baselines` | project_id, version, documents (JSON), statut (brouillon / validée), validée_par, validée_le |
| `reports` | project_id, type (avancement / situation / PV), période, contenu (JSON + texte), statut, validé_par |
| `anomalies` | project_id, sévérité, source (tracker / ci / réunion), message, référence baseline, issue liée, statut (ouverte / résolue) |

## 7. Structure du code

```
ai-service/
├── main.py              routes FastAPI
├── plane_client.py      client API Plane v1
├── llm.py               client Gemini
├── db.py                tables
├── module1/             extract.py, generate.py, prompts/, apply.py
├── module2/             metrics.py, rules.py, report_progress.py, report_status.py, transcript.py, cicd.py
├── pdf.py               export PDF
└── seed_demo.py         projet de démo
```

---

## 8. Niveau réel d'automatisation

| Niveau | Tâches |
|---|---|
| **Automatique** (sans humain) | Collecte des données, calculs, détection par règles, registre des anomalies, mise en forme des rapports |
| **Assisté** (l'IA rédige, l'humain valide) | Documents de lancement, synthèse et recommandations COPIL, PV, détection de scope dans les transcripts |
| **Non automatisable** | Mise à jour des issues par l'équipe, informations hors outil, décisions et arbitrages |

### Gain de temps réaliste

| Tâche | Avant | Avec Orbit |
|---|---|---|
| Documents de lancement | 3 à 5 jours | ½ à 1 jour (relecture + corrections) |
| Rapport d'avancement | 1 à 2 h / semaine | 10 à 15 min |
| Rapport COPIL | 2 à 4 h / semaine | 30 à 45 min |
| Reporting dans le temps du CDP | 30 à 40 % | ~10 à 15 % |

## 9. Limites et risques

| Risque | Réponse |
|---|---|
| Données mal saisies dans le tracker | Conventions d'équipe ; anomalie si un Must n'a pas de label, d'assigné ou de cycle |
| Erreur dans un rapport → perte de confiance | Chiffres calculés en Python ; validation humaine obligatoire |
| Fatigue d'alertes | Peu de règles, ciblées sur les Must et les jalons |
| Faux positifs sur les transcripts | Alertes « réunion » proposées au CDP avant d'être confirmées |
| Données sensibles envoyées au LLM | En entreprise : LLM hébergé en interne ou contrat adapté |

## 10. Consommation LLM (tokens)

Le LLM n'est appelé que pour rédiger ; les calculs et les règles n'en consomment aucun.

| Opération | Appels LLM | Ordre de grandeur |
|---|---|---|
| Brief → 6 documents | 1 extraction + 6 générations | ~20 à 40 k tokens, une fois par projet |
| Rapport d'avancement | 1 | ~3 à 6 k tokens |
| Rapport de situation | 1 | ~5 à 10 k tokens |
| Transcript → PV + comparaison | 1 à 2 | ~10 à 30 k tokens selon la durée de la réunion |
| Webhooks, calculs, règles | 0 | 0 |

Pour réduire : envoyer au LLM le **JSON calculé** plutôt que les issues brutes, et seulement les éléments de la baseline pertinents.

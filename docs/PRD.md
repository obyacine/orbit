# Orbit — Product Requirements Document

| | |
|---|---|
| **Produit** | Orbit — agent IA de pilotage de projet |
| **Contexte** | Hackathon « AI for Work and Business » |
| **Version** | 0.1 — 2026-11-20 |
| **Statut** | Brouillon |

---

## 1. Résumé

Orbit transforme un brief projet en **contrat validé** (la baseline), puis surveille en continu si l'équipe le respecte. Il automatise la chaîne de reporting **Team Lead → PM → COPIL** et signale les dérives dès qu'elles apparaissent.

> *Module 1 crée le contrat. Module 2 l'applique.*

**Pitch :** *Orbit fait la collecte, les calculs et le premier jet. Le CDP passe de rédacteur à relecteur et récupère environ une journée par semaine. Surtout, Orbit voit les dérives par rapport au contrat validé, que personne ne surveille aujourd'hui.*

---

## 2. Problème

| Phase | Aujourd'hui | Coût |
|---|---|---|
| Lancement | Le CDP rédige à la main charte, MoSCoW, risques, parties prenantes, plan de communication | 3 à 5 jours par projet |
| Exécution | Collecte des avancements, rapport d'avancement, rapport COPIL, PV de réunion | 30 à 40 % du temps hebdomadaire |
| Gouvernance | Personne ne compare l'exécution à ce qui a été acté au lancement | Dérives découvertes trop tard, en COPIL |

Les outils existants (Jira, Linear, Monday) savent **afficher** l'état des tâches et intègrent de l'IA pour résumer. Aucun ne **garde en mémoire le contrat validé** pour mesurer l'écart.

---

## 3. Utilisateurs

| Persona | Besoin | Ce qu'Orbit lui apporte |
|---|---|---|
| **Team Lead dev** | Ne plus rédiger le rapport d'avancement | Brouillon généré depuis le tracker, validé en un clic |
| **PM / CDP** | Moins de paperasse, voir les dérives tôt | Documents de lancement générés, rapport COPIL prêt à relire, alertes |
| **COPIL** | Un rapport fiable, régulier, chiffré | Rapport de situation structuré avec météo et recommandations |
| **Développeur** | Ne pas avoir plus de travail | Rien ne change : il met à jour ses tâches comme avant |

---

## 4. Objectifs et indicateurs

| Objectif | Indicateur | Cible |
|---|---|---|
| Accélérer le lancement | Temps brief → baseline validée | < 1 jour (vs 3 à 5) |
| Réduire le reporting | Temps de relecture du rapport COPIL | < 45 min (vs 2 à 4 h) |
| Détecter les dérives tôt | Délai entre la dérive et l'alerte | Le jour même |
| Fiabilité | Chiffres erronés dans un rapport | 0 (calculés, jamais générés) |
| Pertinence | Alertes critiques ignorées par le CDP | < 20 % |

---

## 5. Périmètre fonctionnel

Priorités : **P0** = indispensable à la démo · **P1** = important · **P2** = si le temps le permet.

### Module 1 — Le contrat

| ID | Fonctionnalité | Priorité |
|---|---|---|
| M1-1 | Saisie d'un brief en texte libre | P0 |
| M1-2 | Extraction des entités (objectifs, budget, dates, parties prenantes, contraintes) | P0 |
| M1-3 | Génération de la charte et du tableau MoSCoW (éléments identifiés `M1`, `S2`…) | P0 |
| M1-4 | Génération du registre des risques | P1 |
| M1-5 | Génération du cas d'affaire, de la cartographie des parties prenantes et du plan de communication | P2 |
| M1-6 | Édition section par section par le CDP | P0 |
| M1-7 | Validation → baseline figée et versionnée | P0 |
| M1-8 | Création automatique dans le tracker : labels MoSCoW, epics, sprints / jalons, issues | P0 |

### Module 2 — L'application du contrat

| ID | Fonctionnalité | Priorité |
|---|---|---|
| M2-1 | Snapshot normalisé du projet depuis le tracker | P0 |
| M2-2 | Calculs : % par epic, vélocité, bloqués, jalons à risque, couverture MoSCoW | P0 |
| M2-3 | Règles d'anomalies déterministes (🔴 / 🟡 / 🔵) avec référence à la baseline | P0 |
| M2-4 | Rapport d'avancement (Team Lead → PM) + validation | P0 |
| M2-5 | Rapport de situation (PM → COPIL) : météo, plan vs réel, risques, anomalies, recommandations | P0 |
| M2-6 | Score de dérive | P1 |
| M2-7 | Export PDF des rapports | P1 |
| M2-8 | Réévaluation en temps réel via webhook du tracker | P1 |
| M2-9 | Transcript → PV + détection de glissement de scope | P1 |
| M2-10 | Suggestions d'issues (actions du PV, demandes de changement) à confirmer par le CDP | P1 |
| M2-11 | Webhook CI/CD → anomalie sur test échoué lié à un Must | P2 |
| M2-12 | Génération planifiée hebdomadaire | P2 |

### Hors périmètre

- Gestion des tâches, des utilisateurs et des droits (rôle du tracker)
- Audio vers texte (on part d'un transcript texte)
- Décisions automatiques : Orbit propose, l'humain valide
- Multi-langue de l'interface

---

## 6. Règles d'anomalies (P0)

| Sévérité | Règle |
|---|---|
| 🔴 | Issue `Must` non assignée à moins de 7 jours de son jalon |
| 🔴 | Issue `Must` en retard sur son échéance ou son jalon |
| 🔴 | Issue `Must` bloquée depuis plus de 3 jours |
| 🟡 | Issue `Should` en retard |
| 🟡 | Vélocité en baisse de plus de 20 % |
| 🟡 | Jalon à risque : % réalisé < % de temps écoulé |
| 🔵 | Issue `Could` reportée |

P1 : 🔴 suppression d'un `Must` discutée en réunion sans demande de changement · 🔴 décision contraire à la charte.
P2 : 🔴 build cassé sur `main` · 🔴 test échoué lié à un `Must` · 🟡 couverture sous le seuil.

---

## 7. Parcours utilisateur

**Lancement**
1. Le CDP colle son brief → Orbit génère charte, MoSCoW et risques.
2. Le CDP corrige → valide → la baseline est figée.
3. Orbit crée les labels, epics, sprints et issues dans le tracker.

**Chaque semaine**
1. Le Team Lead clique sur « Générer » → relit → valide le rapport d'avancement.
2. Orbit prépare le rapport de situation → le PM relit et ajuste → PDF au COPIL.

**En continu**
- Une issue change → Orbit réévalue les règles → nouvelle anomalie visible sur le tableau de bord.
- Un transcript est uploadé → PV + alertes de scope + issues suggérées.

---

## 8. Architecture

```
Tracker (issues, sprints, epics, labels)  ── API + webhooks ──→  ai-service (FastAPI)
                                          ←── issues, docs ────    ├─ baseline (contrat)
Interface Orbit ── proxy authentifié ────────────────────────→     ├─ calculs (Python)
                                                                   ├─ règles d'anomalies
                                                                   └─ rédaction (Gemini)
```

| Principe | Raison |
|---|---|
| **Python calcule, le LLM rédige** | Aucun chiffre inventé |
| Règles déterministes en priorité | Fiabilité, pas de fausses alertes |
| Accès au tracker uniquement par son API | Tracker interchangeable |
| L'interface n'appelle jamais l'ai-service directement | Une seule authentification |
| Validation humaine avant tout envoi | Responsabilité du CDP, confiance |

**Stack :** FastAPI (Python 3.12), Google Gemini, SQLite pour l'ai-service, WeasyPrint pour le PDF.

**Décision ouverte — le tracker :** une base open source rebrandée, ou GitHub Projects (aucun code tiers dans le repo). L'ai-service est identique dans les deux cas : seul le client du tracker change.

Détail technique de l'agent : [`AGENT.md`](./AGENT.md).

---

## 9. Exigences non fonctionnelles

| Exigence | Cible |
|---|---|
| Génération d'un rapport | < 20 s |
| Génération des documents de lancement | < 60 s |
| Traçabilité | Chaque anomalie référence un élément de la baseline |
| Historique | Baselines et rapports versionnés, jamais écrasés |
| Secrets | Aucune clé dans le repo ; `.env.example` à jour |
| Confidentialité | Seules les données nécessaires sont envoyées au LLM (JSON calculé, pas les données brutes) |

---

## 10. Scénario de démo (3 à 4 min)

1. Le CDP colle un brief de 5 lignes → charte, MoSCoW et risques générés.
2. Il valide → baseline figée, issues créées dans le tracker.
3. On passe au **jour 21** (projet de démo pré-rempli).
4. « Générer le rapport d'avancement » → % par epic, vélocité, bloqués.
5. Le rapport de situation suit → météo 🔴, plan vs réel, recommandations → PDF.
6. Tableau de bord : 🔴 « Paiement QR (Must) non assigné et bloqué », 🔴 « Biométrie (Must) en retard sur le MVP ».
7. *(P1)* Upload d'un transcript → PV → 🔴 « Suppression d'un Must discutée sans demande de changement » + demande de changement suggérée.

---

## 11. Planning

| # | Étape | Livrable | Priorité |
|---|---|---|---|
| 1 | Client tracker + projet de démo | Données réalistes au jour 21 | P0 |
| 2 | Snapshot + calculs | JSON des indicateurs | P0 |
| 3 | Règles d'anomalies | Registre 🔴🟡🔵 | P0 |
| 4 | Rapport d'avancement + rapport de situation | Deux rapports validables | P0 |
| 5 | Module 1 : brief → baseline → tracker | Début de la démo | P0 |
| 6 | Interface Orbit | Démo jouable de bout en bout | P0 |
| 7 | PDF, score de dérive, webhook | Finitions | P1 |
| 8 | Transcript → PV, suggestions d'issues | Effet « waouh » | P1 |
| 9 | CI/CD | Bonus | P2 |

---

## 12. Risques

| Risque | Mitigation |
|---|---|
| Données mal saisies dans le tracker | Conventions d'équipe ; anomalie si un Must n'a pas de label, d'assigné ou de sprint |
| Hallucination du LLM | Chiffres calculés ; le LLM ne reçoit que du JSON calculé ; validation humaine |
| Quota Gemini dépassé pendant la démo | Mettre en cache les réponses du scénario de démo |
| Fatigue d'alertes | Règles centrées sur les Must et les jalons |
| Données sensibles chez le fournisseur LLM | Mentionner l'option LLM hébergé en interne |
| Démo trop lourde à lancer | Tout dans un seul `docker compose up` |

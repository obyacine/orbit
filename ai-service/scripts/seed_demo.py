"""Create a realistic demo project in Plane through the public API.

Usage (from ai-service/):  uv run python -m scripts.seed_demo [--reset]

Scenario: day 21 of a mobile banking app redesign. Sprint 1 is done, sprint 2 is
ending, the MVP milestone is close. Planted problems for the demo:
  - a Must-Have (QR payment) is unassigned and blocked,
  - a Must-Have (biometric login) is late on the MVP milestone,
  - a Should-Have is late,
  - velocity is lower than planned.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date, timedelta

from app.plane_client import PlaneClient, PlaneError

PROJECT = {
    "name": "Refonte App Mobile Banque",
    "identifier": "BANK",
    "description": "Refonte de l'application mobile grand public : paiement QR, authentification biométrique, "
    "nouvelle UX. Budget 200 k€, MVP à J+28, V1 à J+56.",
}

LABELS = {"Must": "#dc2626", "Should": "#f59e0b", "Could": "#3b82f6", "Won't": "#6b7280", "Bloqué": "#7c3aed"}

MODULES = ["Authentification", "Paiement", "UX / UI", "Back-office"]

TODAY = date.today()
CYCLES = [  # (name, start offset, end offset) in days relative to today (= project day 21)
    ("Sprint 1", -21, -8),
    ("Sprint 2 — MVP", -7, 6),
    ("Sprint 3 — V1", 7, 20),
]

# title, moscow, module, cycle index, status, priority, assigned, target offset (days), blocked_by (title)
ISSUES: list[tuple] = [
    # --- Authentification
    ("Écran de connexion par identifiant", "Must", "Authentification", 0, "done", "high", True, -10, None),
    ("Authentification biométrique (Face ID / empreinte)", "Must", "Authentification", 1, "in_progress", "urgent", True, -2, None),
    ("Gestion de session et déconnexion auto", "Must", "Authentification", 1, "done", "high", True, 2, None),
    ("Réinitialisation du mot de passe", "Should", "Authentification", 1, "todo", "medium", True, -1, None),
    ("Connexion via FranceConnect", "Could", "Authentification", 2, "backlog", "low", False, 18, None),
    # --- Paiement
    ("API de paiement — intégration PSP", "Must", "Paiement", 0, "done", "urgent", True, -9, None),
    ("Obtention des clés de production PSP", "Must", "Paiement", 1, "in_progress", "urgent", True, 1, None),
    ("Paiement par QR code", "Must", "Paiement", 1, "todo", "urgent", False, 5, "Obtention des clés de production PSP"),
    ("Historique des transactions", "Must", "Paiement", 1, "in_progress", "high", True, 4, None),
    ("Virement instantané entre comptes", "Should", "Paiement", 2, "todo", "medium", True, 15, None),
    ("Paiement fractionné", "Won't", "Paiement", None, "backlog", "none", False, None, None),
    # --- UX / UI
    ("Design system mobile", "Must", "UX / UI", 0, "done", "high", True, -12, None),
    ("Onboarding nouveaux clients", "Should", "UX / UI", 1, "done", "medium", True, 0, None),
    ("Mode sombre", "Could", "UX / UI", 2, "backlog", "low", False, 20, None),
    ("Accessibilité RGAA niveau AA", "Must", "UX / UI", 2, "todo", "high", True, 18, None),
    ("Animations de transition", "Could", "UX / UI", None, "backlog", "none", False, None, None),
    # --- Back-office
    ("Tableau de bord conseiller", "Should", "Back-office", 2, "todo", "medium", True, 19, None),
    ("Export des données réglementaires", "Must", "Back-office", 1, "done", "high", True, 3, None),
    ("Journal d'audit des connexions", "Must", "Back-office", 1, "in_progress", "high", True, 5, None),
    ("Statistiques d'usage", "Could", "Back-office", 2, "backlog", "low", False, 20, None),
]

COMMENTS = {
    "Obtention des clés de production PSP": "En attente du retour du prestataire PSP depuis 6 jours, relance faite lundi.",
    "Paiement par QR code": "Bloqué tant que les clés de production PSP ne sont pas livrées. Personne d'assigné pour l'instant.",
    "Authentification biométrique (Face ID / empreinte)": "Problème de compatibilité Android 12, estimation +4 jours.",
}

# Completion date (days relative to today) of done issues, to simulate history.
# Previous week: 4 items, this week: 2 -> velocity drop visible in the demo.
COMPLETED_OFFSETS = {
    "Design system mobile": -12,
    "Écran de connexion par identifiant": -10,
    "API de paiement — intégration PSP": -9,
    "Onboarding nouveaux clients": -8,
    "Gestion de session et déconnexion auto": -3,
    "Export des données réglementaires": -2,
}

STATUS_TO_GROUP = {"backlog": "backlog", "todo": "unstarted", "in_progress": "started", "done": "completed"}


def main() -> int:
    with PlaneClient() as plane:
        existing = [p for p in plane.list_projects() if p["identifier"] == PROJECT["identifier"]]
        if existing:
            if "--reset" not in sys.argv:
                print(f"Le projet {PROJECT['identifier']} existe déjà. Relance avec --reset pour le recréer.")
                return 1
            plane.delete_project(existing[0]["id"])
            print("Ancien projet de démo supprimé.")

        project = plane.create_project(**PROJECT)
        pid = project["id"]
        print(f"Projet créé : {project['name']} ({pid})")

        state_by_group: dict[str, str] = {}
        for s in plane.list_states(pid):
            state_by_group.setdefault(s["group"], s["id"])

        members = plane.list_members(pid)
        assignee = members[0]["id"] if members else None

        label_ids = {name: plane.create_label(pid, name, color)["id"] for name, color in LABELS.items()}
        module_ids = {name: plane.create_module(pid, name)["id"] for name in MODULES}
        # Plane refuses to add issues to a finished cycle: create past cycles with a future end
        # date first, fill them, then restore their real dates (see below).
        cycle_ids = [
            plane.create_cycle(
                pid, name, (TODAY + timedelta(days=s)).isoformat(), (TODAY + timedelta(days=max(e, 1))).isoformat()
            )["id"]
            for name, s, e in CYCLES
        ]
        print(f"{len(label_ids)} labels, {len(module_ids)} modules, {len(cycle_ids)} cycles")

        issue_ids: dict[str, str] = {}
        by_module: dict[str, list[str]] = {}
        by_cycle: dict[int, list[str]] = {}
        for title, moscow, module, cycle, status, priority, assigned, target, blocked_by in ISSUES:
            labels = [label_ids[moscow]] + ([label_ids["Bloqué"]] if blocked_by else [])
            payload = {
                "name": title,
                "state": state_by_group[STATUS_TO_GROUP[status]],
                "priority": priority,
                "labels": labels,
                "assignees": [assignee] if assigned and assignee else [],
            }
            if target is not None:
                payload["target_date"] = (TODAY + timedelta(days=target)).isoformat()
            issue = plane.create_issue(pid, payload)
            issue_ids[title] = issue["id"]
            by_module.setdefault(module, []).append(issue["id"])
            if cycle is not None:
                by_cycle.setdefault(cycle, []).append(issue["id"])

        for module, ids in by_module.items():
            plane.add_issues_to_module(pid, module_ids[module], ids)
        for cycle, ids in by_cycle.items():
            plane.add_issues_to_cycle(pid, cycle_ids[cycle], ids)
        for (name, _s, e), cid in zip(CYCLES, cycle_ids):
            if e < 1:
                plane.update_cycle(pid, cid, {"end_date": (TODAY + timedelta(days=e)).isoformat()})

        for title, *_rest, blocked_by in ISSUES:
            if blocked_by:
                plane.add_relation(pid, issue_ids[title], "blocked_by", [issue_ids[blocked_by]])
        for title, text in COMMENTS.items():
            plane.add_comment(pid, issue_ids[title], f"<p>{text}</p>")

        print(f"{len(issue_ids)} issues créées, relations et commentaires ajoutés.")
        backdate_completions({issue_ids[t]: off for t, off in COMPLETED_OFFSETS.items()})
        print(f"\nPROJECT_ID={pid}")
        return 0


def backdate_completions(offsets: dict[str, int], container: str = "plane-api-1") -> None:
    """The API cannot set completed_at: rewrite it in the local dev database (demo data only)."""
    lines = ["from datetime import timedelta", "from django.utils import timezone", "from plane.db.models import Issue",
             "now = timezone.now()"]
    lines += [f"Issue.objects.filter(id='{iid}').update(completed_at=now + timedelta(days={off}))"
              for iid, off in offsets.items()]
    try:
        subprocess.run(["docker", "exec", "-i", container, "python", "manage.py", "shell"],
                       input="\n".join(lines), text=True, check=True, capture_output=True)
        print(f"Historique simulé : {len(offsets)} dates de fin antidatées.")
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Historique non simulé (docker indisponible ?) : {exc}")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PlaneError as exc:
        print(f"Erreur API Plane : {exc}", file=sys.stderr)
        sys.exit(2)

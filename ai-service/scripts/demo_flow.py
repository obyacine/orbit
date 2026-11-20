"""End-to-end demo of the agent on the demo project, step by step.

Usage (from ai-service/, with the platform and the agent running):
    uv run python -m scripts.demo_flow            # pauses between steps (press Enter)
    uv run python -m scripts.demo_flow --no-pause

Steps: analysis -> a drift is introduced in the tracker -> the agent detects it -> progress report
-> human approval -> situation report for the steering committee -> the PM switches method.
The drift and the method are restored at the end, so the demo can be replayed.
"""

from __future__ import annotations

import sys
import time

import httpx

from app.config import get_settings
from app.plane_client import PlaneClient

AGENT = "http://localhost:8001"
PROJECT_IDENTIFIER = "BANK"
DRIFT_ISSUE = "Historique des transactions"  # Must-Have, assigned, due in 4 days
SEV = {"critical": "🔴", "warning": "🟡", "info": "🔵"}
PAUSE = "--no-pause" not in sys.argv


def step(n: int, title: str) -> None:
    if PAUSE and n > 1:
        input("\n⏎  Entrée pour continuer…")
    print(f"\n\033[1;35m━━━ {n}. {title} ━━━\033[0m")


def show_analysis(a: dict) -> set[str]:
    m = a["metrics"]
    print(f"Méthode : {a['method']['delivery']} · priorisation {a['method']['prioritization']}")
    print(f"Avancement global : {m['overall_pct']} %", end="")
    if m["velocity"]:
        v = m["velocity"]
        print(f" · rythme {v['this_period']} cette semaine vs {v['previous_period']}", end="")
    if m["wip"]:
        print(f" · WIP {m['wip']['current']}/{m['wip']['limit'] or '∞'}", end="")
    print("\nAnomalies :")
    for x in a["anomalies"]:
        print(f"  {SEV[x['severity']]} {x['message']}")
    return {x["message"] for x in a["anomalies"]}


def main() -> None:
    token = get_settings().orbit_internal_token
    agent = httpx.Client(base_url=AGENT, headers={"X-Orbit-Token": token}, timeout=120)
    if agent.get("/health").json().get("llm") != "gemini":
        print("⚠️  L'agent tourne sans Gemini : les textes seront des templates.")

    with PlaneClient() as plane:
        project = next(p for p in plane.list_projects() if p["identifier"] == PROJECT_IDENTIFIER)
        pid = project["id"]
        issue = next(i for i in plane.list_issues(pid) if i["name"] == DRIFT_ISSUE)
        key = f"{PROJECT_IDENTIFIER}-{issue['sequence_id']}"
        assignees = list(issue.get("assignees", []))
        saved_method = agent.get(f"/projects/{pid}/method").json()

        try:
            step(1, f"L'agent lit le projet « {project['name']} »")
            before = show_analysis(agent.get(f"/projects/{pid}/analysis").json())

            step(2, f"Dans Orbit, un développeur se désassigne de {key} « {DRIFT_ISSUE} » (Must-Have, échéance J+4)")
            plane.update_issue(pid, issue["id"], {"assignees": []})
            print("✔ Tâche modifiée dans Orbit")

            step(3, "L'agent relance l'analyse")
            after = show_analysis(agent.get(f"/projects/{pid}/analysis").json())
            for msg in after - before:
                print(f"\n\033[1;31m➜ Nouvelle dérive détectée : {msg}\033[0m")

            step(4, "Rapport d'avancement Team Lead → PM (rédigé par l'IA à partir des chiffres calculés)")
            t = time.time()
            progress = agent.post(f"/projects/{pid}/reports/progress").json()
            print(f"({time.time() - t:.1f} s, rédaction : {progress['content']['summary_source']})\n")
            print(progress["markdown"])

            step(5, "Le Team Lead relit et valide")
            approved = agent.post(f"/reports/{progress['id']}/approve", json={"approved_by": "Team Lead"}).json()
            print(f"✔ Statut : {approved['status']} par {approved['approved_by']}")

            step(6, "Rapport de situation PM → COPIL (s'appuie sur le rapport validé)")
            t = time.time()
            situation = agent.post(f"/projects/{pid}/reports/situation").json()
            print(f"({time.time() - t:.1f} s, basé sur le rapport validé : {situation['parent_id'] == progress['id']})\n")
            print(situation["markdown"])

            step(7, "Le PM change de méthode : Kanban + priorité native, limite WIP = 3")
            agent.put(f"/projects/{pid}/method", json={"delivery": "kanban", "prioritization": "priority", "wip_limit": 3})
            show_analysis(agent.get(f"/projects/{pid}/analysis").json())
            print("\n➜ Mêmes données, autre méthode : plus de sprints, un contrôle WIP, le vocabulaire Urgent / Haute.")
        finally:
            plane.update_issue(pid, issue["id"], {"assignees": assignees})
            body = {k: saved_method[k] for k in ("delivery", "prioritization", "wip_limit", "score_thresholds", "custom_mapping")}
            agent.put(f"/projects/{pid}/method", json=body)
            print(f"\n✔ Démo terminée : {key} réassignée et méthode d'origine restaurée.")


if __name__ == "__main__":
    main()

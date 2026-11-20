"""Progress report (Team Lead -> PM) and situation report (PM -> COPIL).

Structure and numbers come from metrics/rules; the LLM only writes the narrative parts.
Every narrative part has a deterministic fallback.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any

from app import llm
from app.methods import ProjectMethod
from app.module2.metrics import ProjectMetrics
from app.module2.rules import CRITICAL, WARNING, Anomaly
from app.module2.snapshot import ProjectSnapshot

WEATHER = {"red": "🔴 Rouge", "orange": "🟡 Orange", "green": "🟢 Vert"}


def weather(anomalies: list[Anomaly]) -> str:
    if any(a.severity == CRITICAL for a in anomalies):
        return "red"
    if any(a.severity == WARNING for a in anomalies):
        return "orange"
    return "green"


# ------------------------------------------------------------------ progress report


def _progress_fallback(m: ProjectMetrics, method: ProjectMethod) -> str:
    parts = [f"Le projet est réalisé à {m.overall_pct} %."]
    v = m.velocity
    if v:
        trend = (
            f"en baisse de {-v.change_pct} %" if v.change_pct is not None and v.change_pct < 0
            else f"en hausse de {v.change_pct} %" if v.change_pct else "stable"
        )
        parts.append(
            f"{v.this_period} éléments terminés cette semaine contre {v.previous_period} la semaine précédente "
            f"({method.delivery_method.flow_word.lower()} {trend})."
        )
    if m.wip and m.wip.limit:
        parts.append(f"Travail en cours : {m.wip.current} pour une limite de {m.wip.limit}.")
    if m.blocked:
        parts.append(f"{len(m.blocked)} élément(s) bloqué(s).")
    late_ms = [f"{x.kind} {x.name}" for x in m.milestones if x.at_risk or x.overdue]
    if late_ms:
        parts.append(f"À risque : {', '.join(late_ms)}.")
    return " ".join(parts)


def build_progress_report(
    snapshot: ProjectSnapshot,
    metrics: ProjectMetrics,
    comments: dict[str, str],
    method: ProjectMethod | None = None,
) -> dict[str, Any]:
    method = method or ProjectMethod()
    by_key = {i.key: i for i in snapshot.issues}
    blocked = [
        {
            "key": b.key,
            "title": b.title,
            "category": b.category,
            "blocked_by": [f"{k} — {by_key[k].title}" for k in b.blocked_by if k in by_key],
            "reason": comments.get(b.key),
        }
        for b in metrics.blocked
    ]
    data = {
        "project": snapshot.name,
        "as_of": metrics.as_of.isoformat(),
        "method": method.describe(),
        "overall_pct": metrics.overall_pct,
        "epics": [{"name": e.name, "pct": e.pct, "done": e.done, "total": e.total} for e in metrics.epics],
        "velocity": vars(metrics.velocity) if metrics.velocity else None,
        "wip": vars(metrics.wip) if metrics.wip else None,
        "blocked": blocked,
        "milestones_at_risk": [
            {"kind": x.kind, "name": x.name, "pct_done": x.pct_done, "pct_time": x.pct_time_elapsed,
             "days_left": x.days_left, "overdue": x.overdue}
            for x in metrics.milestones if x.at_risk or x.overdue
        ],
        "late": [{"key": k, "title": by_key[k].title, "category": by_key[k].category} for k in metrics.late if k in by_key],
    }
    summary = llm.write(
        "Rédige la synthèse du rapport d'avancement hebdomadaire que le Team Lead envoie au chef de projet : "
        f"avancement global, {method.delivery_method.flow_word.lower()}, points de blocage et leurs raisons, "
        f"échéances à risque. Le projet suit la méthode {method.delivery_method.name} ; emploie son vocabulaire.",
        data,
    )
    return {"type": "progress", **data, "summary": summary or _progress_fallback(metrics, method),
            "summary_source": "llm" if summary else "template"}


# ------------------------------------------------------------------ situation report

_RECO_BY_RULE = {
    "critical_unassigned": "Assigner immédiatement un responsable à « {title} ».",
    "critical_blocked": "Lever le blocage de « {title} » : escalade auprès du fournisseur ou de la direction concernée.",
    "critical_late": "Arbitrer le retard de « {title} » : renfort, report de l'échéance ou réduction du périmètre.",
    "important_late": "Replanifier « {title} » sur la prochaine échéance.",
    "velocity_drop": "Analyser la baisse de vélocité avec l'équipe (charge, blocages, absences).",
    "throughput_drop": "Analyser la baisse de débit : goulots d'étranglement, blocages, absences.",
    "wip_exceeded": "Finir avant de commencer : geler les nouveaux démarrages jusqu'au retour sous la limite WIP.",
    "milestone_at_risk": "Décider du maintien ou du report de l'échéance concernée.",
    "milestone_overdue": "Statuer sur l'échéance dépassée : passage de jalon sous réserve, report ou replanification.",
    "unprioritized": "Prioriser les éléments sans priorité pour fiabiliser le suivi.",
}


def _recommendations_fallback(anomalies: list[Anomaly], by_key: dict) -> list[str]:
    out: list[str] = []
    for a in anomalies:
        tpl = _RECO_BY_RULE.get(a.rule)
        if not tpl:
            continue
        title = by_key[a.issue_key].title if a.issue_key in by_key else ""
        reco = tpl.format(title=title)
        if reco not in out:
            out.append(reco)
    return out


def build_situation_report(
    snapshot: ProjectSnapshot,
    metrics: ProjectMetrics,
    anomalies: list[Anomaly],
    progress: dict[str, Any] | None = None,
    method: ProjectMethod | None = None,
) -> dict[str, Any]:
    method = method or ProjectMethod()
    by_key = {i.key: i for i in snapshot.issues}
    w = weather(anomalies)
    data = {
        "project": snapshot.name,
        "as_of": metrics.as_of.isoformat(),
        "weather": w,
        "method": method.describe(),
        "overall_pct": metrics.overall_pct,
        "plan_vs_actual": [
            {
                "kind": x.kind,
                "milestone": x.name,
                "end_date": x.end_date.isoformat() if x.end_date else None,
                "pct_done": x.pct_done,
                "pct_time_elapsed": x.pct_time_elapsed,
                "gap_pts": x.pct_done - x.pct_time_elapsed,
                "at_risk": x.at_risk or x.overdue,
            }
            for x in sorted(metrics.milestones, key=lambda c: c.end_date or date.max)
        ],
        "coverage": [vars(c) for c in metrics.coverage],
        "anomalies": [a.to_dict() for a in anomalies],
        "progress_summary": progress.get("summary") if progress else None,
    }
    summary_prompt = (
        "Rédige la synthèse exécutive du rapport de situation destiné au comité de pilotage (COPIL) : "
        f"météo du projet, écart plan/réel, risques majeurs pour les éléments « {method.framework.tier_labels['critical']} » "
        f"(priorisation {method.framework.name}, pilotage {method.delivery_method.name}). Ton direct, pour un directeur."
    )
    recos_prompt = (
        "Propose 3 à 5 recommandations concrètes au COPIL et les décisions attendues, une par ligne, "
        "commençant par un verbe d'action. Appuie-toi uniquement sur les anomalies fournies."
    )
    # Both texts are independent: write them in parallel to halve the wait.
    with ThreadPoolExecutor(max_workers=2) as pool:
        summary_job = pool.submit(llm.write, summary_prompt, data, max_words=120)
        recos_job = pool.submit(llm.write, recos_prompt, data, max_words=120)
        summary, recos_text = summary_job.result(), recos_job.result()
    recos = [r.strip("-•* ").strip() for r in recos_text.splitlines() if r.strip()] if recos_text else None
    fallback_summary = (
        f"Météo {WEATHER[w]}. Avancement global {metrics.overall_pct} %. "
        f"{sum(1 for a in anomalies if a.severity == CRITICAL)} anomalie(s) critique(s) et "
        f"{sum(1 for a in anomalies if a.severity == WARNING)} avertissement(s) sur la période."
    )
    return {
        "type": "situation",
        **data,
        "weather_label": WEATHER[w],
        "summary": summary or fallback_summary,
        "recommendations": recos or _recommendations_fallback(anomalies, by_key),
        "summary_source": "llm" if summary else "template",
    }


# ------------------------------------------------------------------ markdown rendering


def to_markdown(report: dict[str, Any]) -> str:
    if report["type"] == "progress":
        meth = report["method"]
        lines = [f"# Rapport d'avancement — {report['project']}",
                 f"*Au {report['as_of']}* · {meth['delivery']} · priorisation {meth['prioritization']}", "",
                 "## Synthèse", report["summary"], "", f"## Avancement global : {report['overall_pct']} %", "",
                 "| Epic | Avancement | Terminés |", "|---|---|---|"]
        lines += [f"| {e['name']} | {e['pct']} % | {e['done']}/{e['total']} |" for e in report["epics"]]
        v = report["velocity"]
        lines.append("")
        if v:
            lines += [f"## Rythme\n{v['this_period']} terminés cette semaine / {v['previous_period']} la semaine précédente", ""]
        if report["wip"] and report["wip"]["limit"]:
            w = report["wip"]
            lines += [f"## Travail en cours\n{w['current']} / limite {w['limit']}{' ⚠️' if w['exceeded'] else ''}", ""]
        if report["blocked"]:
            lines += ["## Éléments bloqués"]
            for b in report["blocked"]:
                by = f" — bloqué par {', '.join(b['blocked_by'])}" if b["blocked_by"] else ""
                cat = f" ({b['category']})" if b["category"] else ""
                lines.append(f"- **{b['key']}** {b['title']}{cat}{by}")
                if b["reason"]:
                    lines.append(f"  - Raison : {b['reason']}")
            lines.append("")
        if report["milestones_at_risk"]:
            lines += ["## Échéances à risque"]
            lines += [f"- **{x['kind']} {x['name']}** : {x['pct_done']} % réalisé pour {x['pct_time']} % du temps "
                      + (f"(dépassée de {-x['days_left']} j)" if x["overdue"] else f"({x['days_left']} j restants)")
                      for x in report["milestones_at_risk"]]
        return "\n".join(lines) + "\n"

    sev = {"critical": "🔴", "warning": "🟡", "info": "🔵"}
    meth = report["method"]
    lines = [f"# Rapport de situation — {report['project']}", (f"*Au {report['as_of']}* · Météo : **{report['weather_label']}**"
              f" · {meth['delivery']} · priorisation {meth['prioritization']}"),
             "", "## Synthèse exécutive", report["summary"], "", "## Plan vs réel",
             "| Échéance | Date | Réalisé | Temps écoulé | Écart |", "|---|---|---|---|---|"]
    lines += [f"| {p['kind']} {p['milestone']} | {p['end_date']} | {p['pct_done']} % | {p['pct_time_elapsed']} % | "
              f"{p['gap_pts']:+d} pts{' ⚠️' if p['at_risk'] else ''} |" for p in report["plan_vs_actual"]]
    lines += ["", f"## Couverture par priorité ({meth['prioritization']})",
              "| Priorité | Total | Terminés | En cours | En retard |", "|---|---|---|---|---|"]
    lines += [f"| {c['category']} | {c['total']} | {c['done']} | {c['in_progress']} | {c['late']} |" for c in report["coverage"]]
    lines += ["", "## Anomalies de la période"]
    lines += [f"- {sev[a['severity']]} {a['message']}" + (f" *(réf. {a['baseline_ref']})*" if a["baseline_ref"] else "")
              for a in report["anomalies"]] or ["- Aucune"]
    lines += ["", "## Recommandations et décisions attendues"]
    lines += [f"{n}. {r}" for n, r in enumerate(report["recommendations"], 1)]
    return "\n".join(lines) + "\n"

"""Progress report (Team Lead -> PM) and situation report (PM -> COPIL).

Structure and numbers come from metrics/rules; the LLM only writes the narrative parts.
Every narrative part has a deterministic fallback.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app import llm
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


def _progress_fallback(m: ProjectMetrics) -> str:
    v = m.velocity
    trend = (
        f"en baisse de {-v.change_pct} %" if v.change_pct is not None and v.change_pct < 0
        else f"en hausse de {v.change_pct} %" if v.change_pct else "stable"
    )
    late_ms = [x.name for x in m.milestones if x.at_risk]
    parts = [
        f"Le projet est réalisé à {m.overall_pct} %.",
        f"{v.this_period} éléments terminés cette semaine contre {v.previous_period} la semaine précédente (vélocité {trend}).",
    ]
    if m.blocked:
        parts.append(f"{len(m.blocked)} élément(s) bloqué(s).")
    if late_ms:
        parts.append(f"Jalon(s) à risque : {', '.join(late_ms)}.")
    return " ".join(parts)


def build_progress_report(snapshot: ProjectSnapshot, metrics: ProjectMetrics, comments: dict[str, str]) -> dict[str, Any]:
    by_key = {i.key: i for i in snapshot.issues}
    blocked = [
        {
            "key": b.key,
            "title": b.title,
            "moscow": b.moscow,
            "blocked_by": [f"{k} — {by_key[k].title}" for k in b.blocked_by if k in by_key],
            "reason": comments.get(b.key),
        }
        for b in metrics.blocked
    ]
    data = {
        "project": snapshot.name,
        "as_of": metrics.as_of.isoformat(),
        "overall_pct": metrics.overall_pct,
        "epics": [{"name": e.name, "pct": e.pct, "done": e.done, "total": e.total} for e in metrics.epics],
        "velocity": vars(metrics.velocity),
        "blocked": blocked,
        "milestones_at_risk": [
            {"name": x.name, "pct_done": x.pct_done, "pct_time": x.pct_time_elapsed, "days_left": x.days_left}
            for x in metrics.milestones if x.at_risk
        ],
        "late": [{"key": k, "title": by_key[k].title, "moscow": by_key[k].moscow} for k in metrics.late if k in by_key],
    }
    summary = llm.write(
        "Rédige la synthèse du rapport d'avancement hebdomadaire que le Team Lead envoie au chef de projet : "
        "avancement global, vélocité, points de blocage et leurs raisons, jalons à risque.",
        data,
    )
    return {"type": "progress", **data, "summary": summary or _progress_fallback(metrics),
            "summary_source": "llm" if summary else "template"}


# ------------------------------------------------------------------ situation report

_RECO_BY_RULE = {
    "must_unassigned": "Assigner immédiatement un responsable à « {title} ».",
    "must_blocked": "Lever le blocage de « {title} » : escalade auprès du fournisseur ou de la direction concernée.",
    "must_late": "Arbitrer le retard de « {title} » : renfort, report du jalon ou réduction du périmètre.",
    "should_late": "Replanifier « {title} » sur le prochain sprint.",
    "velocity_drop": "Analyser la baisse de vélocité avec l'équipe (charge, blocages, absences).",
    "milestone_at_risk": "Décider du maintien ou du report du jalon concerné.",
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
) -> dict[str, Any]:
    by_key = {i.key: i for i in snapshot.issues}
    w = weather(anomalies)
    data = {
        "project": snapshot.name,
        "as_of": metrics.as_of.isoformat(),
        "weather": w,
        "overall_pct": metrics.overall_pct,
        "plan_vs_actual": [
            {
                "milestone": x.name,
                "end_date": x.end_date.isoformat() if x.end_date else None,
                "pct_done": x.pct_done,
                "pct_time_elapsed": x.pct_time_elapsed,
                "gap_pts": x.pct_done - x.pct_time_elapsed,
                "at_risk": x.at_risk,
            }
            for x in sorted(metrics.milestones, key=lambda c: c.end_date or date.max)
        ],
        "moscow": [vars(c) for c in metrics.moscow],
        "anomalies": [a.to_dict() for a in anomalies],
        "progress_summary": progress.get("summary") if progress else None,
    }
    summary = llm.write(
        "Rédige la synthèse exécutive du rapport de situation destiné au comité de pilotage (COPIL) : "
        "météo du projet, écart plan/réel, risques majeurs pour les Must-Have. Ton direct, pour un directeur.",
        data, max_words=120,
    )
    recos_text = llm.write(
        "Propose 3 à 5 recommandations concrètes au COPIL et les décisions attendues, une par ligne, "
        "commençant par un verbe d'action. Appuie-toi uniquement sur les anomalies fournies.",
        data, max_words=120,
    )
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
        lines = [f"# Rapport d'avancement — {report['project']}", f"*Au {report['as_of']}*", "",
                 "## Synthèse", report["summary"], "", f"## Avancement global : {report['overall_pct']} %", "",
                 "| Epic | Avancement | Terminés |", "|---|---|---|"]
        lines += [f"| {e['name']} | {e['pct']} % | {e['done']}/{e['total']} |" for e in report["epics"]]
        v = report["velocity"]
        lines += ["", f"## Vélocité\n{v['this_period']} cette semaine / {v['previous_period']} la semaine précédente", ""]
        if report["blocked"]:
            lines += ["## Éléments bloqués"]
            for b in report["blocked"]:
                by = f" — bloqué par {', '.join(b['blocked_by'])}" if b["blocked_by"] else ""
                lines.append(f"- **{b['key']}** {b['title']} ({b['moscow']}){by}")
                if b["reason"]:
                    lines.append(f"  - Raison : {b['reason']}")
            lines.append("")
        if report["milestones_at_risk"]:
            lines += ["## Jalons à risque"]
            lines += [f"- **{x['name']}** : {x['pct_done']} % réalisé pour {x['pct_time']} % du temps "
                      f"({x['days_left']} j restants)" for x in report["milestones_at_risk"]]
        return "\n".join(lines) + "\n"

    sev = {"critical": "🔴", "warning": "🟡", "info": "🔵"}
    lines = [f"# Rapport de situation — {report['project']}", f"*Au {report['as_of']}* · Météo : **{report['weather_label']}**",
             "", "## Synthèse exécutive", report["summary"], "", "## Plan vs réel",
             "| Jalon | Échéance | Réalisé | Temps écoulé | Écart |", "|---|---|---|---|---|"]
    lines += [f"| {p['milestone']} | {p['end_date']} | {p['pct_done']} % | {p['pct_time_elapsed']} % | "
              f"{p['gap_pts']:+d} pts{' ⚠️' if p['at_risk'] else ''} |" for p in report["plan_vs_actual"]]
    lines += ["", "## Couverture MoSCoW", "| Catégorie | Total | Terminés | En cours | En retard |", "|---|---|---|---|---|"]
    lines += [f"| {c['category']} | {c['total']} | {c['done']} | {c['in_progress']} | {c['late']} |" for c in report["moscow"]]
    lines += ["", "## Anomalies de la période"]
    lines += [f"- {sev[a['severity']]} {a['message']}" + (f" *(réf. {a['baseline_ref']})*" if a["baseline_ref"] else "")
              for a in report["anomalies"]] or ["- Aucune"]
    lines += ["", "## Recommandations et décisions attendues"]
    lines += [f"{n}. {r}" for n, r in enumerate(report["recommendations"], 1)]
    return "\n".join(lines) + "\n"

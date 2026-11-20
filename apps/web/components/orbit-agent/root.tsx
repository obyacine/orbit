/**
 * Copyright (c) 2026-present Orbit contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useEffect, useState } from "react";
import { observer } from "mobx-react";
import { Button } from "@makeplane/propel/components/button";
import { setToast } from "@plane/blocks/toast";
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
// hooks
import { useUserPermissions } from "@/hooks/store/user";
// services
import type {
  TAgentAnalysis,
  TAgentAnomaly,
  TAgentCatalog,
  TAgentMethod,
  TAgentReport,
  TAgentReportType,
  TAgentSeverity,
} from "@/services/orbit-agent.service";
import { OrbitAgentService } from "@/services/orbit-agent.service";
import { OrbitAgentBaseline } from "./baseline";

const agentService = new OrbitAgentService();

const SEVERITY: Record<TAgentSeverity, { icon: string; label: string; className: string }> = {
  critical: { icon: "🔴", label: "Critique", className: "border-l-danger-primary" },
  warning: { icon: "🟡", label: "Avertissement", className: "border-l-warning-primary" },
  info: { icon: "🔵", label: "Info", className: "border-l-accent-primary" },
};

const WEATHER = {
  red: { icon: "🔴", label: "Rouge" },
  orange: { icon: "🟡", label: "Orange" },
  green: { icon: "🟢", label: "Vert" },
};

const REPORT_LABEL: Record<TAgentReportType, string> = {
  progress: "Rapport d'avancement · Team Lead → PM",
  situation: "Rapport de situation · PM → COPIL",
};

const weatherOf = (anomalies: TAgentAnomaly[]) =>
  anomalies.some((a) => a.severity === "critical")
    ? WEATHER.red
    : anomalies.some((a) => a.severity === "warning")
      ? WEATHER.orange
      : WEATHER.green;

const errorMessage = (error: unknown) =>
  (error as { error?: string })?.error ?? "L'agent IA n'a pas répondu. Vérifiez que le service ai-service est démarré.";

const formatDate = (iso: string) =>
  new Date(iso).toLocaleString("fr-FR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });

// ------------------------------------------------------------------ small building blocks

function Card({ title, children, className = "" }: { title?: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={`rounded-lg border border-subtle bg-surface-1 p-4 ${className}`}>
      {title && <h3 className="mb-3 text-body-sm-semibold text-primary">{title}</h3>}
      {children}
    </section>
  );
}

function Kpi({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="rounded-lg border border-subtle bg-surface-1 px-4 py-3">
      <div className="text-caption-md-regular text-tertiary">{label}</div>
      <div className="mt-1 text-h5-semibold text-primary">{value}</div>
      {hint && <div className="mt-0.5 text-caption-sm-regular text-tertiary">{hint}</div>}
    </div>
  );
}

function ProgressBar({ pct }: { pct: number }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-layer-2">
      <div className="h-full rounded-full bg-accent-primary" style={{ width: `${Math.min(pct, 100)}%` }} />
    </div>
  );
}

function AnomalyList({ anomalies }: { anomalies: TAgentAnomaly[] }) {
  if (anomalies.length === 0)
    return <p className="text-body-xs-regular text-tertiary">Aucune anomalie : le projet respecte le plan.</p>;
  return (
    <ul className="flex flex-col gap-2">
      {anomalies.map((a, i) => (
        <li
          key={`${a.rule}-${a.issue_key}-${i}`}
          className={`rounded-md border border-l-4 border-subtle bg-layer-1 px-3 py-2 ${SEVERITY[a.severity].className}`}
        >
          <div className="text-body-xs-medium text-primary">
            {SEVERITY[a.severity].icon} {a.message}
          </div>
          {a.baseline_ref && <div className="mt-0.5 text-caption-sm-regular text-tertiary">Réf. {a.baseline_ref}</div>}
        </li>
      ))}
    </ul>
  );
}

function Table({ head, rows }: { head: string[]; rows: React.ReactNode[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-body-xs-regular">
        <thead>
          <tr className="border-b border-subtle text-tertiary">
            {head.map((h) => (
              <th key={h} className="py-1.5 pr-3 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-subtle text-secondary last:border-0">
              {row.map((cell, j) => (
                <td key={j} className="py-1.5 pr-3">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ------------------------------------------------------------------ report view

function ReportBody({ report }: { report: TAgentReport }) {
  const c = report.content;
  const summary = (
    <div className="rounded-md bg-layer-1 p-3">
      <div className="mb-1 flex items-center gap-2 text-caption-sm-medium text-tertiary">
        Synthèse
        <span className="rounded bg-accent-subtle px-1.5 py-0.5 text-accent-primary">
          {c.summary_source === "llm" ? "✨ rédigée par l'IA" : "modèle automatique"}
        </span>
      </div>
      <p className="text-body-xs-regular whitespace-pre-line text-primary">{c.summary}</p>
    </div>
  );

  if (report.type === "progress")
    return (
      <div className="flex flex-col gap-4">
        {summary}
        <div>
          <div className="mb-2 text-body-xs-medium text-primary">Avancement global : {c.overall_pct} %</div>
          <Table
            head={["Epic", "Avancement", "Terminés"]}
            rows={(c.epics ?? []).map((e: { name: string; pct: number; done: number; total: number }) => [
              e.name,
              `${e.pct} %`,
              `${e.done}/${e.total}`,
            ])}
          />
        </div>
        {c.blocked?.length > 0 && (
          <div>
            <div className="mb-2 text-body-xs-medium text-primary">Éléments bloqués</div>
            <ul className="flex flex-col gap-1.5 text-body-xs-regular text-secondary">
              {c.blocked.map((b: { key: string; title: string; category: string | null; reason: string | null }) => (
                <li key={b.key}>
                  <span className="font-medium text-primary">{b.key}</span> {b.title}
                  {b.category && ` (${b.category})`}
                  {b.reason && <div className="text-tertiary">Raison : {b.reason}</div>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );

  return (
    <div className="flex flex-col gap-4">
      <div className="text-body-xs-medium text-primary">Météo : {c.weather_label}</div>
      {summary}
      <div>
        <div className="mb-2 text-body-xs-medium text-primary">Plan vs réel</div>
        <Table
          head={["Échéance", "Réalisé", "Temps écoulé", "Écart"]}
          rows={(c.plan_vs_actual ?? []).map(
            (p: {
              kind: string;
              milestone: string;
              pct_done: number;
              pct_time_elapsed: number;
              gap_pts: number;
              at_risk: boolean;
            }) => [
              `${p.kind} ${p.milestone}`,
              `${p.pct_done} %`,
              `${p.pct_time_elapsed} %`,
              <span key="gap" className={p.at_risk ? "text-danger-primary" : ""}>
                {p.gap_pts > 0 ? "+" : ""}
                {p.gap_pts} pts {p.at_risk ? "⚠️" : ""}
              </span>,
            ]
          )}
        />
      </div>
      <div>
        <div className="mb-2 text-body-xs-medium text-primary">Recommandations et décisions attendues</div>
        <ol className="list-decimal pl-5 text-body-xs-regular text-secondary">
          {(c.recommendations ?? []).map((r: string) => (
            <li key={r} className="mb-1">
              {r}
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ page

type Props = { workspaceSlug: string; projectId: string };

export const OrbitAgentRoot = observer(function OrbitAgentRoot({ workspaceSlug, projectId }: Props) {
  const { allowPermissions } = useUserPermissions();
  const isAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.PROJECT);
  const canWrite = allowPermissions([EUserPermissions.ADMIN, EUserPermissions.MEMBER], EUserPermissionsLevel.PROJECT);

  const [catalog, setCatalog] = useState<TAgentCatalog | null>(null);
  const [method, setMethod] = useState<TAgentMethod | null>(null);
  const [draftMethod, setDraftMethod] = useState({ delivery: "hybrid", prioritization: "moscow", wip_limit: "" });
  const [analysis, setAnalysis] = useState<TAgentAnalysis | null>(null);
  const [reports, setReports] = useState<TAgentReport[]>([]);
  const [selected, setSelected] = useState<TAgentReport | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [tab, setTab] = useState<"cadrage" | "pilotage" | null>(null);
  const [editedText, setEditedText] = useState("");

  const refreshAnalysis = useCallback(async () => {
    setBusy("analysis");
    try {
      setAnalysis(await agentService.getAnalysis(workspaceSlug, projectId));
      setLoadError(null);
    } catch (error) {
      setLoadError(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [workspaceSlug, projectId]);

  const refreshReports = useCallback(async () => {
    try {
      setReports(await agentService.listReports(workspaceSlug, projectId));
    } catch {
      // the analysis error already explains what is wrong
    }
  }, [workspaceSlug, projectId]);

  useEffect(() => {
    void (async () => {
      try {
        const [cat, m] = await Promise.all([
          agentService.getCatalog(workspaceSlug, projectId),
          agentService.getMethod(workspaceSlug, projectId),
        ]);
        setCatalog(cat);
        setMethod(m);
        setDraftMethod({
          delivery: m.delivery,
          prioritization: m.prioritization,
          wip_limit: m.wip_limit?.toString() ?? "",
        });
      } catch (error) {
        setLoadError(errorMessage(error));
      }
    })();
    void refreshAnalysis();
    void refreshReports();
  }, [workspaceSlug, projectId, refreshAnalysis, refreshReports]);

  const saveMethod = async () => {
    setBusy("method");
    try {
      const wip = parseInt(draftMethod.wip_limit, 10);
      const saved = await agentService.setMethod(workspaceSlug, projectId, {
        delivery: draftMethod.delivery,
        prioritization: draftMethod.prioritization,
        wip_limit: Number.isNaN(wip) ? null : wip,
      });
      setMethod(saved);
      setToast({
        type: "success",
        title: "Méthode enregistrée",
        message: `${saved.labels.delivery} · ${saved.labels.prioritization}`,
      });
      setBusy(null);
      await refreshAnalysis();
    } catch (error) {
      setToast({ type: "error", title: "Méthode non enregistrée", message: errorMessage(error) });
      setBusy(null);
    }
  };

  const generate = async (type: TAgentReportType) => {
    setBusy(type);
    try {
      const report = await agentService.generateReport(workspaceSlug, projectId, type);
      setSelected(report);
      setEditing(false);
      await refreshReports();
      setToast({ type: "success", title: "Rapport généré", message: REPORT_LABEL[type] });
    } catch (error) {
      setToast({ type: "error", title: "Rapport non généré", message: errorMessage(error) });
    } finally {
      setBusy(null);
    }
  };

  const approve = async () => {
    if (!selected) return;
    setBusy("approve");
    try {
      const report = await agentService.approveReport(
        workspaceSlug,
        projectId,
        selected.id,
        editing ? editedText : undefined
      );
      setSelected(report);
      setEditing(false);
      await refreshReports();
      setToast({ type: "success", title: "Rapport validé", message: `Validé par ${report.approved_by}` });
    } catch (error) {
      setToast({ type: "error", title: "Validation impossible", message: errorMessage(error) });
    } finally {
      setBusy(null);
    }
  };

  const m = analysis?.metrics;
  const weather = analysis ? weatherOf(analysis.anomalies) : null;
  const methodDirty =
    method &&
    (draftMethod.delivery !== method.delivery ||
      draftMethod.prioritization !== method.prioritization ||
      draftMethod.wip_limit !== (method.wip_limit?.toString() ?? ""));
  // An empty project starts on "Cadrage" (brief -> baseline); a running one on "Pilotage".
  const projectIsEmpty =
    !!m && m.coverage.reduce((n, c) => n + c.total, 0) + m.unclassified.length + m.epics.length === 0;
  const activeTab = tab ?? (projectIsEmpty ? "cadrage" : "pilotage");
  const showWip = draftMethod.delivery === "kanban" || draftMethod.delivery === "hybrid";
  const selectClass =
    "rounded-md border border-subtle bg-layer-1 px-2 py-1.5 text-body-xs-regular text-primary disabled:opacity-60";

  return (
    <div className="flex h-full w-full flex-col overflow-y-auto">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-4 p-5">
        {/* Tabs */}
        <div className="flex gap-1 border-b border-subtle">
          {(
            [
              ["cadrage", "1 · Cadrage", "Brief → charte → livrables → baseline"],
              ["pilotage", "2 · Pilotage", "Analyse, anomalies, rapports"],
            ] as const
          ).map(([key, label, hint]) => (
            <button
              key={key}
              type="button"
              title={hint}
              onClick={() => setTab(key)}
              className={`-mb-px border-b-2 px-4 py-2 text-body-sm-medium ${
                activeTab === key
                  ? "border-accent-primary text-primary"
                  : "border-transparent text-tertiary hover:text-secondary"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Method + actions */}
        <div className="flex flex-wrap items-end justify-between gap-4 rounded-lg border border-subtle bg-surface-1 p-4">
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-caption-sm-medium text-tertiary">Méthode de pilotage</span>
              <select
                className={selectClass}
                value={draftMethod.delivery}
                disabled={!isAdmin || !catalog}
                onChange={(e) => setDraftMethod((d) => ({ ...d, delivery: e.target.value }))}
              >
                {catalog?.delivery.map((d) => (
                  <option key={d.id} value={d.id} title={d.description}>
                    {d.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-caption-sm-medium text-tertiary">Méthode de priorisation</span>
              <select
                className={selectClass}
                value={draftMethod.prioritization}
                disabled={!isAdmin || !catalog}
                onChange={(e) => setDraftMethod((d) => ({ ...d, prioritization: e.target.value }))}
              >
                {catalog?.prioritization
                  .filter((p) => p.id !== "custom")
                  .map((p) => (
                    <option key={p.id} value={p.id} title={p.description}>
                      {p.name}
                    </option>
                  ))}
              </select>
            </label>
            {showWip && (
              <label className="flex flex-col gap-1">
                <span className="text-caption-sm-medium text-tertiary">Limite WIP</span>
                <input
                  type="number"
                  min={1}
                  placeholder="aucune"
                  className={`${selectClass} w-24`}
                  value={draftMethod.wip_limit}
                  disabled={!isAdmin}
                  onChange={(e) => setDraftMethod((d) => ({ ...d, wip_limit: e.target.value }))}
                />
              </label>
            )}
            {isAdmin && methodDirty && (
              <Button
                stretch="auto"
                variant="secondary"
                size="sm"
                label="Appliquer"
                loading={busy === "method"}
                onClick={() => void saveMethod()}
              />
            )}
          </div>
          <div className={`flex flex-wrap gap-2 ${activeTab === "pilotage" ? "" : "hidden"}`}>
            <Button
              stretch="auto"
              variant="secondary"
              size="md"
              label="Analyser"
              loading={busy === "analysis"}
              disabled={!!busy && busy !== "analysis"}
              onClick={() => void refreshAnalysis()}
            />
            {canWrite && (
              <>
                <Button
                  stretch="auto"
                  variant="secondary"
                  size="md"
                  label="Rapport d'avancement"
                  loading={busy === "progress"}
                  disabled={!!busy && busy !== "progress"}
                  onClick={() => void generate("progress")}
                />
                <Button
                  stretch="auto"
                  variant="primary"
                  size="md"
                  label="Rapport COPIL"
                  loading={busy === "situation"}
                  disabled={!!busy && busy !== "situation"}
                  onClick={() => void generate("situation")}
                />
              </>
            )}
          </div>
        </div>

        {loadError && (
          <div className="rounded-lg border border-subtle bg-danger-subtle p-3 text-body-xs-regular text-danger-primary">
            {loadError}
          </div>
        )}

        {activeTab === "cadrage" && (
          <OrbitAgentBaseline
            workspaceSlug={workspaceSlug}
            projectId={projectId}
            method={method}
            catalog={catalog}
            isAdmin={isAdmin}
            onValidated={() => void refreshAnalysis()}
          />
        )}

        {activeTab === "pilotage" && (
          <>
            {/* KPIs */}
            {m && weather && (
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                <Kpi
                  label="Météo du projet"
                  value={`${weather.icon} ${weather.label}`}
                  hint={`${analysis.method.delivery} · ${analysis.method.prioritization}`}
                />
                <Kpi
                  label="Avancement global"
                  value={`${m.overall_pct} %`}
                  hint={`Au ${new Date(m.as_of).toLocaleDateString("fr-FR")}`}
                />
                {m.velocity ? (
                  <Kpi
                    label={analysis.method.delivery === "Kanban" ? "Débit (7 j)" : "Vélocité (7 j)"}
                    value={m.velocity.this_period}
                    hint={
                      m.velocity.change_pct === null
                        ? `vs ${m.velocity.previous_period} la semaine précédente`
                        : `${m.velocity.change_pct > 0 ? "+" : ""}${m.velocity.change_pct} % vs semaine précédente`
                    }
                  />
                ) : (
                  <Kpi label="Éléments en retard" value={m.late.length} />
                )}
                {m.wip?.limit ? (
                  <Kpi
                    label="Travail en cours"
                    value={`${m.wip.current} / ${m.wip.limit}`}
                    hint={m.wip.exceeded ? "⚠️ limite dépassée" : "sous la limite"}
                  />
                ) : (
                  <Kpi
                    label="Anomalies"
                    value={analysis.anomalies.length}
                    hint={`${analysis.anomalies.filter((a) => a.severity === "critical").length} critique(s)`}
                  />
                )}
              </div>
            )}

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
              {/* Left: analysis */}
              <div className="flex flex-col gap-4 lg:col-span-2">
                <Card title="Registre des anomalies">
                  {analysis ? (
                    <AnomalyList anomalies={analysis.anomalies} />
                  ) : (
                    <p className="text-body-xs-regular text-tertiary">Analyse en cours…</p>
                  )}
                </Card>
                {m && m.milestones.length > 0 && (
                  <Card title="Plan vs réel">
                    <div className="flex flex-col gap-3">
                      {m.milestones.map((ms) => (
                        <div key={ms.id}>
                          <div className="mb-1 flex justify-between text-body-xs-regular">
                            <span className="text-primary">
                              {ms.kind} {ms.name}
                            </span>
                            <span className={ms.at_risk || ms.overdue ? "text-danger-primary" : "text-tertiary"}>
                              {ms.pct_done} % · {ms.pct_time_elapsed} % du temps {ms.at_risk || ms.overdue ? "⚠️" : ""}
                            </span>
                          </div>
                          <ProgressBar pct={ms.pct_done} />
                        </div>
                      ))}
                    </div>
                  </Card>
                )}
                {m && (
                  <Card title={`Couverture par priorité (${analysis.method.prioritization})`}>
                    <Table
                      head={["Priorité", "Total", "Terminés", "En cours", "En retard"]}
                      rows={m.coverage.map((c) => [c.category, c.total, c.done, c.in_progress, c.late])}
                    />
                  </Card>
                )}
              </div>

              {/* Right: reports */}
              <div className="flex flex-col gap-4 lg:col-span-3">
                <Card title={selected ? REPORT_LABEL[selected.type] : "Rapports"}>
                  {selected ? (
                    <div className="flex flex-col gap-4">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span
                          className={`rounded px-2 py-0.5 text-caption-sm-medium ${
                            selected.status === "approved"
                              ? "bg-success-subtle text-success-primary"
                              : "bg-layer-2 text-secondary"
                          }`}
                        >
                          {selected.status === "approved"
                            ? `✔ Validé par ${selected.approved_by}`
                            : "Brouillon — à relire et valider"}
                        </span>
                        {selected.status === "draft" && canWrite && (
                          <div className="flex gap-2">
                            <Button
                              stretch="auto"
                              variant="ghost"
                              size="sm"
                              label={editing ? "Annuler" : "Modifier"}
                              onClick={() => {
                                setEditedText(selected.markdown);
                                setEditing((e) => !e);
                              }}
                            />
                            <Button
                              stretch="auto"
                              variant="primary"
                              size="sm"
                              label="Valider"
                              loading={busy === "approve"}
                              onClick={() => void approve()}
                            />
                          </div>
                        )}
                      </div>
                      {selected.type === "situation" && selected.parent_id && (
                        <p className="text-caption-sm-regular text-tertiary">
                          Construit à partir du dernier rapport d'avancement validé.
                        </p>
                      )}
                      {editing ? (
                        <textarea
                          className="font-mono min-h-96 w-full rounded-md border border-subtle bg-layer-1 p-3 text-body-xs-regular text-primary"
                          value={editedText}
                          onChange={(e) => setEditedText(e.target.value)}
                        />
                      ) : (
                        <ReportBody report={selected} />
                      )}
                    </div>
                  ) : (
                    <p className="text-body-xs-regular text-tertiary">
                      Générez un rapport d'avancement ou un rapport COPIL. L'agent calcule les chiffres, l'IA rédige le
                      texte, vous relisez et validez.
                    </p>
                  )}
                </Card>

                {reports.length > 0 && (
                  <Card title="Historique">
                    <ul className="flex flex-col divide-y divide-subtle">
                      {reports.map((r) => (
                        <li key={r.id}>
                          <button
                            type="button"
                            className={`flex w-full items-center justify-between gap-2 px-1 py-2 text-left text-body-xs-regular hover:bg-layer-transparent-hover ${
                              selected?.id === r.id ? "text-primary" : "text-secondary"
                            }`}
                            onClick={() => {
                              setSelected(r);
                              setEditing(false);
                            }}
                          >
                            <span>
                              {r.type === "progress" ? "Avancement" : "COPIL"} · {formatDate(r.created_at)}
                            </span>
                            <span className={r.status === "approved" ? "text-success-primary" : "text-tertiary"}>
                              {r.status === "approved" ? "✔ validé" : "brouillon"}
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </Card>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
});

/**
 * Copyright (c) 2026-present Orbit contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
import { Button } from "@makeplane/propel/components/button";
import { setToast } from "@plane/blocks/toast";
// services
import type {
  TAgentCatalog,
  TAgentMethod,
  TBaseline,
  TBaselineContent,
  TBaselineDeliverable,
  TExtractedDocument,
} from "@/services/orbit-agent.service";
import { OrbitAgentService } from "@/services/orbit-agent.service";
import { OrbitAgentLibrary } from "./library";

const agentService = new OrbitAgentService();

const NATIVE_PRIORITIES = [
  { id: "urgent", label: "Urgent" },
  { id: "high", label: "Haute" },
  { id: "medium", label: "Moyenne" },
  { id: "low", label: "Basse" },
];

const EXAMPLE_BRIEF =
  "Nous devons lancer un portail RH en libre-service pour les 1 200 salariés du groupe d'ici fin mars 2027. " +
  "Les salariés doivent pouvoir consulter leurs fiches de paie, poser des congés et mettre à jour leurs informations. " +
  "Les managers valident les congés. Intégration avec le SIRH existant (Workday). Budget : 180 k€. Sponsor : DRH. " +
  "Contraintes : RGPD, authentification SSO Azure AD. Le module notes de frais est hors périmètre.";

const errorMessage = (error: unknown) =>
  (error as { error?: string })?.error ?? "L'agent IA n'a pas répondu. Vérifiez que le service ai-service est démarré.";

const inputClass =
  "w-full rounded-md border border-subtle bg-layer-1 px-2 py-1 text-body-xs-regular text-primary disabled:opacity-70";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1.5 text-caption-md-medium text-tertiary uppercase">{title}</div>
      {children}
    </div>
  );
}

function Bullets({ items }: { items: string[] }) {
  if (!items?.length) return <p className="text-body-xs-regular text-tertiary">—</p>;
  return (
    <ul className="list-disc pl-5 text-body-xs-regular text-secondary">
      {items.map((x) => (
        <li key={x}>{x}</li>
      ))}
    </ul>
  );
}

function CharterView({ content }: { content: TBaselineContent }) {
  const c = content.charter;
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-h5-semibold text-primary">{c.title}</h2>
        <p className="mt-1 text-body-xs-regular text-secondary">{c.context}</p>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Section title="Budget">
          <p className="text-body-sm-medium text-primary">{c.budget}</p>
        </Section>
        <Section title="Début">
          <p className="text-body-sm-medium text-primary">{c.start_date || "À préciser"}</p>
        </Section>
        <Section title="Fin">
          <p className="text-body-sm-medium text-primary">{c.end_date || "À préciser"}</p>
        </Section>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Section title="Objectifs">
          <Bullets items={c.objectives} />
        </Section>
        <Section title="Critères de succès">
          <Bullets items={c.success_criteria} />
        </Section>
        <Section title="Dans le périmètre">
          <Bullets items={c.scope_in} />
        </Section>
        <Section title="Hors périmètre">
          <Bullets items={c.scope_out} />
        </Section>
        <Section title="Parties prenantes">
          <ul className="text-body-xs-regular text-secondary">
            {c.stakeholders.map((s) => (
              <li key={s.name}>
                <span className="font-medium text-primary">{s.name}</span> — {s.role} (influence {s.influence})
              </li>
            ))}
          </ul>
        </Section>
        <Section title="Contraintes">
          <Bullets items={c.constraints} />
        </Section>
      </div>
      <Section title="Registre des risques">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-body-xs-regular">
            <thead>
              <tr className="border-b border-subtle text-tertiary">
                <th className="py-1.5 pr-3 font-medium">Id</th>
                <th className="py-1.5 pr-3 font-medium">Risque</th>
                <th className="py-1.5 pr-3 font-medium">Probabilité</th>
                <th className="py-1.5 pr-3 font-medium">Impact</th>
                <th className="py-1.5 pr-3 font-medium">Mitigation</th>
              </tr>
            </thead>
            <tbody>
              {c.risks.map((r) => (
                <tr key={r.id} className="border-b border-subtle text-secondary last:border-0">
                  <td className="py-1.5 pr-3 font-medium text-primary">{r.id}</td>
                  <td className="py-1.5 pr-3">{r.description}</td>
                  <td className="py-1.5 pr-3">{r.probability}</td>
                  <td className="py-1.5 pr-3">{r.impact}</td>
                  <td className="py-1.5 pr-3">{r.mitigation}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
      <Section title="Découpage">
        <div className="flex flex-wrap gap-2">
          {content.epics.map((e) => (
            <span key={e.id} className="rounded-md bg-layer-2 px-2 py-1 text-body-xs-regular text-secondary">
              <span className="font-medium text-primary">{e.id}</span> {e.name}
              {e.start_date && ` · ${e.start_date} → ${e.end_date}`}
            </span>
          ))}
        </div>
        {content.milestones.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {content.milestones.map((m) => (
              <span
                key={m.id}
                className="rounded-md border border-subtle px-2 py-1 text-caption-sm-regular text-tertiary"
              >
                {m.name} · {m.start_date} → {m.end_date}
              </span>
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}

type Props = {
  workspaceSlug: string;
  projectId: string;
  method: TAgentMethod | null;
  catalog: TAgentCatalog | null;
  isAdmin: boolean;
  onValidated: () => void;
};

export const OrbitAgentBaseline = observer(function OrbitAgentBaseline({
  workspaceSlug,
  projectId,
  method,
  catalog,
  isAdmin,
  onValidated,
}: Props) {
  const [baselines, setBaselines] = useState<TBaseline[]>([]);
  const [current, setCurrent] = useState<TBaseline | null>(null);
  const [content, setContent] = useState<TBaselineContent | null>(null);
  const [brief, setBrief] = useState("");
  const [busy, setBusy] = useState<"draft" | "validate" | null>(null);
  const [writingBrief, setWritingBrief] = useState(false);
  const [imported, setImported] = useState<TExtractedDocument[]>([]);
  const [importing, setImporting] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  // The document's text lands in the brief, where the PM can read and edit what the AI will receive.
  const importFiles = async (files: FileList | File[]) => {
    setImporting(true);
    for (const file of Array.from(files)) {
      try {
        const doc = await agentService.extractDocument(workspaceSlug, projectId, file);
        setBrief((b) => (b.trim() ? `${b.trim()}\n\n--- ${doc.filename} ---\n${doc.text}` : doc.text));
        setImported((list) => [...list, doc]);
        if (doc.truncated)
          setToast({
            type: "warning",
            title: "Document tronqué",
            message: `${doc.filename} est très long : seuls les ${doc.characters.toLocaleString("fr-FR")} premiers caractères sont repris.`,
          });
      } catch (error) {
        setToast({ type: "error", title: `Import impossible : ${file.name}`, message: errorMessage(error) });
      }
    }
    setImporting(false);
    if (fileInput.current) fileInput.current.value = "";
  };

  const load = useCallback(async () => {
    try {
      const list = await agentService.listBaselines(workspaceSlug, projectId);
      setBaselines(list);
      const pick = list.find((b) => b.status === "validated") ?? list[0] ?? null;
      setCurrent(pick);
      setContent(pick ? structuredClone(pick.content) : null);
      if (pick) setBrief(pick.brief);
    } catch {
      // the page-level error banner explains connectivity issues
    }
  }, [workspaceSlug, projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const validated = baselines.find((b) => b.status === "validated");
  const isDraft = current?.status === "draft";
  const editable = isDraft && isAdmin;
  const framework = catalog?.prioritization.find(
    (p) => p.id === (current?.method.prioritization ?? method?.prioritization)
  );
  const priorityOptions =
    framework?.source === "priority"
      ? NATIVE_PRIORITIES
      : (framework?.categories ?? []).map((c) => ({ id: c, label: c }));
  const isScore = framework?.source === "score";

  const generate = async () => {
    setBusy("draft");
    try {
      const draft = await agentService.draftBaseline(workspaceSlug, projectId, brief);
      setCurrent(draft);
      setContent(structuredClone(draft.content));
      setWritingBrief(false);
      setBaselines((list) => [draft, ...list]);
      setToast({ type: "success", title: "Cadrage généré", message: "Relisez, ajustez les livrables, puis validez." });
    } catch (error) {
      setToast({ type: "error", title: "Génération impossible", message: errorMessage(error) });
    } finally {
      setBusy(null);
    }
  };

  const validate = async () => {
    if (!current || !content) return;
    setBusy("validate");
    try {
      const done = await agentService.validateBaseline(workspaceSlug, projectId, current.id, content);
      setToast({
        type: "success",
        title: "Baseline validée et créée dans Orbit",
        message: `${done.counts?.work_items ?? 0} work items, ${done.counts?.modules ?? 0} modules, ${done.counts?.cycles ?? 0} cycles`,
      });
      await load();
      onValidated();
    } catch (error) {
      setToast({ type: "error", title: "Validation impossible", message: errorMessage(error) });
    } finally {
      setBusy(null);
    }
  };

  const updateDeliverable = (index: number, patch: Partial<TBaselineDeliverable>) =>
    setContent((c) =>
      c ? { ...c, deliverables: c.deliverables.map((d, i) => (i === index ? { ...d, ...patch } : d)) } : c
    );

  const removeDeliverable = (index: number) =>
    setContent((c) => (c ? { ...c, deliverables: c.deliverables.filter((_, i) => i !== index) } : c));

  const addDeliverable = () =>
    setContent((c) =>
      c
        ? {
            ...c,
            deliverables: [
              ...c.deliverables,
              {
                id: `D${c.deliverables.length + 1}`,
                title: "Nouveau livrable",
                description: "",
                epic_id: c.epics[0]?.id ?? "E1",
                milestone_id: c.milestones[0]?.id ?? "",
                priority: isScore ? "1" : (priorityOptions[1]?.id ?? priorityOptions[0]?.id ?? ""),
                due_date: c.charter.end_date,
              },
            ],
          }
        : c
    );

  // ---------------------------------------------------------------- brief input
  if (!current || writingBrief) {
    return (
      <div className="flex flex-col gap-4">
        <OrbitAgentLibrary workspaceSlug={workspaceSlug} projectId={projectId} isAdmin={isAdmin} />
        <div className="flex flex-col gap-4 rounded-lg border border-subtle bg-surface-1 p-5">
          <div>
            <h2 className="text-h5-semibold text-primary">Cadrage du projet</h2>
            <p className="mt-1 text-body-xs-regular text-secondary">
              Collez votre brief ou importez vos documents (cahier des charges, note de cadrage…). L'IA prépare la
              charte, le registre des risques, le découpage et les livrables priorisés selon votre méthode (
              {method?.labels.prioritization ?? "…"} · {method?.labels.delivery ?? "…"}, modifiable en haut de la page).
              Vous relisez, vous corrigez, vous validez : Orbit crée alors le projet.
            </p>
          </div>
          <div
            className={`flex flex-col gap-2 rounded-md border border-dashed p-3 ${
              dragOver ? "border-accent-primary bg-accent-subtle" : "border-subtle"
            }`}
            onDragOver={(e) => {
              if (!isAdmin) return;
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              if (isAdmin && e.dataTransfer.files.length) void importFiles(e.dataTransfer.files);
            }}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-body-xs-regular text-secondary">
                Déposez un document ici ou importez-le : PDF, Word (.docx), .txt, .md · 10 Mo max
              </span>
              <input
                ref={fileInput}
                id="orbit-brief-documents"
                type="file"
                multiple
                accept=".pdf,.docx,.txt,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown"
                className="hidden"
                onChange={(e) => e.target.files?.length && void importFiles(e.target.files)}
              />
              <Button
                stretch="auto"
                variant="secondary"
                size="sm"
                label="Importer un document"
                loading={importing}
                disabled={!isAdmin}
                onClick={() => fileInput.current?.click()}
              />
            </div>
            {imported.length > 0 && (
              <ul className="flex flex-wrap gap-2">
                {imported.map((d, i) => (
                  <li
                    key={`${d.filename}-${i}`}
                    className="rounded bg-layer-2 px-2 py-0.5 text-caption-sm-regular text-secondary"
                  >
                    📄 {d.filename} · {d.kind}
                    {d.pages ? ` · ${d.pages} p.` : ""} · {d.characters.toLocaleString("fr-FR")} caractères
                    {d.truncated ? " (tronqué)" : ""}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <textarea
            id="orbit-brief"
            className="min-h-48 w-full rounded-md border border-subtle bg-layer-1 p-3 text-body-xs-regular text-primary"
            placeholder="Besoin, objectifs, périmètre, échéance, budget, parties prenantes, contraintes…"
            value={brief}
            disabled={!isAdmin}
            onChange={(e) => setBrief(e.target.value)}
          />
          <p className="-mt-2 text-caption-sm-regular text-tertiary">
            Ce texte est exactement ce que l'IA recevra : relisez-le et retirez ce qui n'est pas utile (annexes, données
            personnelles).
          </p>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <button
              type="button"
              className="text-body-xs-regular text-accent-primary hover:underline"
              onClick={() => setBrief(EXAMPLE_BRIEF)}
            >
              Utiliser un exemple de brief
            </button>
            <div className="flex gap-2">
              {current && (
                <Button
                  stretch="auto"
                  variant="ghost"
                  size="md"
                  label="Annuler"
                  onClick={() => setWritingBrief(false)}
                />
              )}
              <Button
                stretch="auto"
                variant="primary"
                size="md"
                label="Générer le cadrage"
                loading={busy === "draft"}
                disabled={!isAdmin || brief.trim().length < 30}
                onClick={() => void generate()}
              />
            </div>
          </div>
          {!isAdmin && (
            <p className="text-caption-sm-regular text-tertiary">
              Seul un administrateur du projet peut cadrer le projet.
            </p>
          )}
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------- draft / validated baseline
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-subtle bg-surface-1 p-4">
        <div className="flex flex-col gap-0.5">
          <span
            className={`w-fit rounded px-2 py-0.5 text-caption-sm-medium ${
              isDraft ? "bg-layer-2 text-secondary" : "bg-success-subtle text-success-primary"
            }`}
          >
            {isDraft
              ? `Brouillon v${current.version} — à relire et valider`
              : `✔ Baseline v${current.version} validée par ${current.validated_by} — figée`}
          </span>
          <span className="text-caption-sm-regular text-tertiary">
            Méthode : {catalog?.delivery.find((d) => d.id === current.method.delivery)?.name ?? current.method.delivery}{" "}
            · {framework?.name ?? current.method.prioritization}
          </span>
          {current.sources && (current.sources.documents.length > 0 || current.sources.past_projects.length > 0) && (
            <span className="text-caption-sm-regular text-tertiary">
              Inspiré de :{" "}
              {[
                ...current.sources.documents.map((d) => `📄 ${d}`),
                ...current.sources.past_projects.map((p) => `✔ ${p}`),
              ].join(" · ")}
            </span>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {!validated && isAdmin && (
            <Button
              stretch="auto"
              variant="secondary"
              size="md"
              label="Nouveau brief"
              onClick={() => setWritingBrief(true)}
            />
          )}
          {editable && !validated && (
            <Button
              stretch="auto"
              variant="primary"
              size="md"
              label="Valider et créer dans Orbit"
              loading={busy === "validate"}
              onClick={() => void validate()}
            />
          )}
          {!isDraft && (
            <Link
              href={`/${workspaceSlug}/projects/${projectId}/issues`}
              className="rounded-md border border-subtle px-3 py-1.5 text-body-xs-medium text-primary hover:bg-layer-transparent-hover"
            >
              Voir les work items →
            </Link>
          )}
        </div>
      </div>

      {content && (
        <>
          <section className="rounded-lg border border-subtle bg-surface-1 p-5">
            <CharterView content={content} />
          </section>

          <section className="rounded-lg border border-subtle bg-surface-1 p-5">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-body-sm-semibold text-primary">
                Livrables priorisés ({framework?.name}) · {content.deliverables.length}
              </h3>
              {editable && (
                <Button
                  stretch="auto"
                  variant="ghost"
                  size="sm"
                  label="+ Ajouter un livrable"
                  onClick={addDeliverable}
                />
              )}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-body-xs-regular">
                <thead>
                  <tr className="border-b border-subtle text-tertiary">
                    <th className="py-1.5 pr-2 font-medium">Id</th>
                    <th className="py-1.5 pr-2 font-medium">Livrable</th>
                    <th className="py-1.5 pr-2 font-medium">Priorité</th>
                    <th className="py-1.5 pr-2 font-medium">Epic / phase</th>
                    {content.milestones.length > 0 && <th className="py-1.5 pr-2 font-medium">Sprint / jalon</th>}
                    <th className="py-1.5 pr-2 font-medium">Échéance</th>
                    {editable && <th />}
                  </tr>
                </thead>
                <tbody>
                  {content.deliverables.map((d, i) => (
                    <tr key={`${d.id}-${i}`} className="border-b border-subtle align-top last:border-0">
                      <td className="py-1.5 pr-2 font-medium text-primary">{d.id}</td>
                      <td className="min-w-64 py-1.5 pr-2">
                        {editable ? (
                          <input
                            className={inputClass}
                            value={d.title}
                            onChange={(e) => updateDeliverable(i, { title: e.target.value })}
                          />
                        ) : (
                          <span className="text-primary">{d.title}</span>
                        )}
                        {d.description && (
                          <div className="mt-0.5 text-caption-sm-regular text-tertiary">{d.description}</div>
                        )}
                      </td>
                      <td className="py-1.5 pr-2">
                        {editable && isScore ? (
                          <input
                            type="number"
                            className={`${inputClass} w-20`}
                            value={d.priority}
                            onChange={(e) => updateDeliverable(i, { priority: e.target.value })}
                          />
                        ) : editable ? (
                          <select
                            className={inputClass}
                            value={d.priority}
                            onChange={(e) => updateDeliverable(i, { priority: e.target.value })}
                          >
                            {priorityOptions.map((o) => (
                              <option key={o.id} value={o.id}>
                                {o.label}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <span className="rounded bg-layer-2 px-1.5 py-0.5 text-secondary">
                            {isScore
                              ? `${framework?.name} ${d.priority}`
                              : (priorityOptions.find((o) => o.id === d.priority)?.label ?? d.priority)}
                          </span>
                        )}
                      </td>
                      <td className="py-1.5 pr-2">
                        {editable ? (
                          <select
                            className={inputClass}
                            value={d.epic_id}
                            onChange={(e) => updateDeliverable(i, { epic_id: e.target.value })}
                          >
                            {content.epics.map((e) => (
                              <option key={e.id} value={e.id}>
                                {e.id} · {e.name}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <span className="text-secondary">
                            {content.epics.find((e) => e.id === d.epic_id)?.name ?? d.epic_id}
                          </span>
                        )}
                      </td>
                      {content.milestones.length > 0 && (
                        <td className="py-1.5 pr-2">
                          {editable ? (
                            <select
                              className={inputClass}
                              value={d.milestone_id}
                              onChange={(e) => updateDeliverable(i, { milestone_id: e.target.value })}
                            >
                              <option value="">—</option>
                              {content.milestones.map((m) => (
                                <option key={m.id} value={m.id}>
                                  {m.name}
                                </option>
                              ))}
                            </select>
                          ) : (
                            <span className="text-secondary">
                              {content.milestones.find((m) => m.id === d.milestone_id)?.name ?? "—"}
                            </span>
                          )}
                        </td>
                      )}
                      <td className="py-1.5 pr-2">
                        {editable ? (
                          <input
                            type="date"
                            className={inputClass}
                            value={d.due_date}
                            onChange={(e) => updateDeliverable(i, { due_date: e.target.value })}
                          />
                        ) : (
                          <span className="text-secondary">{d.due_date || "—"}</span>
                        )}
                      </td>
                      {editable && (
                        <td className="py-1.5">
                          <button
                            type="button"
                            className="px-1 text-tertiary hover:text-danger-primary"
                            aria-label="Supprimer le livrable"
                            onClick={() => removeDeliverable(i)}
                          >
                            ✕
                          </button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <details className="rounded-lg border border-subtle bg-surface-1 p-4">
            <summary className="cursor-pointer text-body-xs-medium text-secondary">Brief d'origine</summary>
            <p className="mt-2 text-body-xs-regular whitespace-pre-line text-secondary">{current.brief}</p>
          </details>
        </>
      )}
    </div>
  );
});

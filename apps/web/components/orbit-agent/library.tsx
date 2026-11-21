/**
 * Copyright (c) 2026-present Orbit contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@makeplane/propel/components/button";
import { setToast } from "@plane/blocks/toast";
// services
import type { TLibrary, TLibraryRole } from "@/services/orbit-agent.service";
import { OrbitAgentService } from "@/services/orbit-agent.service";

const agentService = new OrbitAgentService();

const ROLES: { id: TLibraryRole; label: string; hint: string }[] = [
  { id: "template", label: "Modèle", hint: "Charte type, trame de cahier des charges" },
  { id: "past_project", label: "Projet passé", hint: "Documents d'un projet déjà mené" },
  { id: "standard", label: "Standard interne", hint: "Grille de risques, règles de gouvernance" },
];

const errorMessage = (error: unknown) =>
  (error as { error?: string })?.error ?? "L'agent IA n'a pas répondu. Vérifiez que le service ai-service est démarré.";

type Props = { workspaceSlug: string; projectId: string; isAdmin: boolean };

/** Documents the agent learns the organization's habits from, plus the projects already validated. */
export function OrbitAgentLibrary({ workspaceSlug, projectId, isAdmin }: Props) {
  const [library, setLibrary] = useState<TLibrary | null>(null);
  const [role, setRole] = useState<TLibraryRole>("template");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(true);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      setLibrary(await agentService.getLibrary(workspaceSlug, projectId));
    } catch {
      // the page-level banner explains connectivity issues
    }
  }, [workspaceSlug, projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const add = async (files: FileList) => {
    setBusy(true);
    for (const file of Array.from(files)) {
      try {
        await agentService.addToLibrary(workspaceSlug, projectId, file, role);
        setToast({ type: "success", title: "Ajouté à la bibliothèque", message: file.name });
      } catch (error) {
        setToast({ type: "error", title: `Ajout impossible : ${file.name}`, message: errorMessage(error) });
      }
    }
    setBusy(false);
    if (fileInput.current) fileInput.current.value = "";
    await load();
  };

  const remove = async (id: string, name: string) => {
    try {
      await agentService.removeFromLibrary(workspaceSlug, projectId, id);
      setToast({ type: "success", title: "Retiré de la bibliothèque", message: name });
      await load();
    } catch (error) {
      setToast({ type: "error", title: "Suppression impossible", message: errorMessage(error) });
    }
  };

  const docs = library?.documents ?? [];
  const past = library?.past_projects ?? [];
  const total = docs.length + past.length;

  return (
    <section className="rounded-lg border border-subtle bg-surface-1 p-4">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-2 text-left"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="flex flex-col">
          <span className="text-body-sm-semibold text-primary">Bibliothèque de l'organisation · {total}</span>
          <span className="text-caption-sm-regular text-tertiary">
            L'agent reprend la structure, le vocabulaire et les habitudes de ces documents pour chaque nouveau cadrage.
            Les faits (budget, dates, noms) viennent toujours du brief.
          </span>
        </span>
        <span className="text-tertiary">{open ? "▾" : "▸"}</span>
      </button>

      {open && (
        <div className="mt-3 flex flex-col gap-3">
          {isAdmin && (
            <div className="flex flex-wrap items-center gap-2">
              <select
                id="orbit-library-role"
                aria-label="Type de document"
                className="rounded-md border border-subtle bg-layer-1 px-2 py-1.5 text-body-xs-regular text-primary"
                value={role}
                onChange={(e) => setRole(e.target.value as TLibraryRole)}
              >
                {ROLES.map((r) => (
                  <option key={r.id} value={r.id} title={r.hint}>
                    {r.label}
                  </option>
                ))}
              </select>
              <input
                ref={fileInput}
                id="orbit-library-files"
                type="file"
                multiple
                accept=".pdf,.docx,.txt,.md"
                className="hidden"
                onChange={(e) => e.target.files?.length && void add(e.target.files)}
              />
              <Button
                stretch="auto"
                variant="secondary"
                size="sm"
                label="Ajouter un document de référence"
                loading={busy}
                onClick={() => fileInput.current?.click()}
              />
              <span className="text-caption-sm-regular text-tertiary">
                {ROLES.find((r) => r.id === role)?.hint} · PDF, Word, .txt, .md
              </span>
            </div>
          )}

          {total === 0 ? (
            <p className="text-body-xs-regular text-tertiary">
              Vide pour l'instant. Ajoutez une charte type ou les documents d'un projet passé : les prochains cadrages
              suivront ce format. Chaque baseline validée rejoint aussi la bibliothèque automatiquement.
            </p>
          ) : (
            <ul className="flex flex-col divide-y divide-subtle">
              {docs.map((d) => (
                <li key={d.id} className="flex items-center justify-between gap-3 py-2 text-body-xs-regular">
                  <span className="min-w-0">
                    <span className="text-primary">📄 {d.filename}</span>
                    <span className="text-tertiary">
                      {" "}
                      · {ROLES.find((r) => r.id === d.role)?.label ?? d.role} · {d.characters.toLocaleString("fr-FR")}{" "}
                      caractères
                      {d.has_layout && d.role === "template" ? " · mise en page utilisée pour les exports" : ""}
                      {d.created_by ? ` · ajouté par ${d.created_by}` : ""}
                    </span>
                  </span>
                  {isAdmin && (
                    <button
                      type="button"
                      className="shrink-0 px-1 text-tertiary hover:text-danger-primary"
                      aria-label={`Retirer ${d.filename}`}
                      onClick={() => void remove(d.id, d.filename)}
                    >
                      ✕
                    </button>
                  )}
                </li>
              ))}
              {past.map((p) => (
                <li key={p.project_id} className="py-2 text-body-xs-regular">
                  <span className="text-primary">✔ {p.title}</span>
                  <span className="text-tertiary">
                    {" "}
                    · baseline v{p.version} validée · {p.deliverables} livrables · ajoutée automatiquement
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

/**
 * Copyright (c) 2026-present Orbit contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// components
import { PageHead } from "@/components/core/page-title";
import { OrbitAgentRoot } from "@/components/orbit-agent/root";
// hooks
import { useProject } from "@/hooks/store/use-project";
import type { Route } from "./+types/page";

function ProjectAgentPage({ params }: Route.ComponentProps) {
  const { workspaceSlug, projectId } = params;
  const { currentProjectDetails } = useProject();

  return (
    <div className="flex h-full flex-col">
      <PageHead title={`${currentProjectDetails?.name ?? "Projet"} - Agent IA`} />
      <OrbitAgentRoot workspaceSlug={workspaceSlug} projectId={projectId} />
    </div>
  );
}

export default observer(ProjectAgentPage);

/**
 * Copyright (c) 2026-present Orbit contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import { APIService } from "@/services/api.service";

// ------------------------------------------------------------------ types (mirror ai-service JSON)

export type TAgentSeverity = "critical" | "warning" | "info";

export type TAgentAnomaly = {
  rule: string;
  severity: TAgentSeverity;
  message: string;
  issue_key: string | null;
  baseline_ref: string | null;
};

export type TAgentMilestone = {
  id: string;
  name: string;
  kind: string;
  end_date: string | null;
  done: number;
  total: number;
  pct_done: number;
  pct_time_elapsed: number;
  days_left: number | null;
  at_risk: boolean;
  overdue: boolean;
};

export type TAgentCoverage = {
  tier: string;
  category: string;
  total: number;
  done: number;
  in_progress: number;
  late: number;
};

export type TAgentMetrics = {
  as_of: string;
  overall_pct: number;
  epics: { id: string; name: string; done: number; total: number; pct: number }[];
  velocity: { this_period: number; previous_period: number; change_pct: number | null } | null;
  blocked: { key: string; title: string; category: string | null; blocked_by: string[] }[];
  milestones: TAgentMilestone[];
  coverage: TAgentCoverage[];
  unclassified: string[];
  wip: { current: number; limit: number | null; exceeded: boolean } | null;
  late: string[];
};

export type TAgentMethodLabels = { delivery: string; prioritization: string };

export type TAgentAnalysis = {
  project: { id: string; name: string };
  method: TAgentMethodLabels;
  metrics: TAgentMetrics;
  anomalies: TAgentAnomaly[];
};

export type TAgentMethod = {
  configured: boolean;
  delivery: string;
  prioritization: string;
  wip_limit: number | null;
  score_thresholds: Record<string, number> | null;
  custom_mapping: Record<string, string>;
  labels: TAgentMethodLabels;
};

export type TAgentCatalogItem = {
  id: string;
  name: string;
  description: string;
  source?: string;
  categories?: string[];
};
export type TAgentCatalog = { prioritization: TAgentCatalogItem[]; delivery: TAgentCatalogItem[] };

export type TAgentReportType = "progress" | "situation";

export type TAgentReport = {
  id: string;
  project_id: string;
  type: TAgentReportType;
  status: "draft" | "approved";
  // oxlint-disable-next-line typescript/no-explicit-any -- report body differs per type, rendered defensively
  content: Record<string, any>;
  markdown: string;
  parent_id: string | null;
  created_at: string;
  approved_at: string | null;
  approved_by: string | null;
};

// ------------------------------------------------------------------ Module 1: baseline

export type TBaselineDeliverable = {
  id: string;
  title: string;
  description: string;
  epic_id: string;
  milestone_id: string;
  priority: string;
  due_date: string;
};

export type TBaselineContent = {
  charter: {
    title: string;
    context: string;
    objectives: string[];
    scope_in: string[];
    scope_out: string[];
    budget: string;
    start_date: string;
    end_date: string;
    stakeholders: { name: string; role: string; influence: string }[];
    constraints: string[];
    success_criteria: string[];
    risks: { id: string; description: string; probability: string; impact: string; mitigation: string }[];
  };
  epics: { id: string; name: string; description: string; start_date: string; end_date: string }[];
  milestones: { id: string; name: string; start_date: string; end_date: string }[];
  deliverables: TBaselineDeliverable[];
};

export type TBaseline = {
  id: string;
  project_id: string;
  version: number;
  status: "draft" | "validated";
  brief: string;
  method: { delivery: string; prioritization: string };
  content: TBaselineContent;
  work_items: Record<string, string> | null;
  created_at: string;
  created_by: string | null;
  validated_at: string | null;
  validated_by: string | null;
  counts?: { work_items: number; modules: number; cycles: number };
  sources?: { documents: string[]; past_projects: string[] } | null;
};

export type TLibraryRole = "template" | "past_project" | "standard";

export type TLibrary = {
  documents: {
    id: string;
    filename: string;
    kind: string;
    role: TLibraryRole;
    characters: number;
    created_at: string;
    created_by: string | null;
  }[];
  past_projects: { project_id: string; title: string; version: number; validated_at: string; deliverables: number }[];
};

export type TExtractedDocument = {
  filename: string;
  kind: string;
  pages: number | null;
  characters: number;
  truncated: boolean;
  text: string;
};

// ------------------------------------------------------------------ service

export class OrbitAgentService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  private base(workspaceSlug: string, projectId: string) {
    return `/api/workspaces/${workspaceSlug}/projects/${projectId}/agent`;
  }

  async getCatalog(workspaceSlug: string, projectId: string): Promise<TAgentCatalog> {
    return this.get(`${this.base(workspaceSlug, projectId)}/methods/`)
      .then((res) => res?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async getMethod(workspaceSlug: string, projectId: string): Promise<TAgentMethod> {
    return this.get(`${this.base(workspaceSlug, projectId)}/method/`)
      .then((res) => res?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async setMethod(
    workspaceSlug: string,
    projectId: string,
    data: Pick<TAgentMethod, "delivery" | "prioritization" | "wip_limit">
  ): Promise<TAgentMethod> {
    return this.put(`${this.base(workspaceSlug, projectId)}/method/`, data)
      .then((res) => res?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async getAnalysis(workspaceSlug: string, projectId: string): Promise<TAgentAnalysis> {
    return this.get(`${this.base(workspaceSlug, projectId)}/analysis/`)
      .then((res) => res?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async listReports(workspaceSlug: string, projectId: string): Promise<TAgentReport[]> {
    return this.get(`${this.base(workspaceSlug, projectId)}/reports/`)
      .then((res) => res?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async generateReport(workspaceSlug: string, projectId: string, type: TAgentReportType): Promise<TAgentReport> {
    return this.post(`${this.base(workspaceSlug, projectId)}/reports/${type}/`)
      .then((res) => res?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async extractDocument(workspaceSlug: string, projectId: string, file: File): Promise<TExtractedDocument> {
    const form = new FormData();
    form.append("file", file);
    return this.post(`${this.base(workspaceSlug, projectId)}/documents/extract/`, form)
      .then((res) => res?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async getLibrary(workspaceSlug: string, projectId: string): Promise<TLibrary> {
    return this.get(`${this.base(workspaceSlug, projectId)}/library/`)
      .then((res) => res?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async addToLibrary(workspaceSlug: string, projectId: string, file: File, role: TLibraryRole): Promise<unknown> {
    const form = new FormData();
    form.append("file", file);
    form.append("role", role);
    return this.post(`${this.base(workspaceSlug, projectId)}/library/`, form)
      .then((res) => res?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async removeFromLibrary(workspaceSlug: string, projectId: string, referenceId: string): Promise<unknown> {
    return this.delete(`${this.base(workspaceSlug, projectId)}/library/${referenceId}/`)
      .then((res) => res?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async listBaselines(workspaceSlug: string, projectId: string): Promise<TBaseline[]> {
    return this.get(`${this.base(workspaceSlug, projectId)}/baselines/`)
      .then((res) => res?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async draftBaseline(workspaceSlug: string, projectId: string, brief: string): Promise<TBaseline> {
    return this.post(`${this.base(workspaceSlug, projectId)}/baselines/draft/`, { brief })
      .then((res) => res?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async saveBaseline(
    workspaceSlug: string,
    projectId: string,
    baselineId: string,
    content: TBaselineContent
  ): Promise<TBaseline> {
    return this.put(`${this.base(workspaceSlug, projectId)}/baselines/${baselineId}/`, { content })
      .then((res) => res?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async validateBaseline(
    workspaceSlug: string,
    projectId: string,
    baselineId: string,
    content: TBaselineContent
  ): Promise<TBaseline> {
    return this.post(`${this.base(workspaceSlug, projectId)}/baselines/${baselineId}/validate/`, { content })
      .then((res) => res?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async approveReport(
    workspaceSlug: string,
    projectId: string,
    reportId: string,
    markdown?: string
  ): Promise<TAgentReport> {
    return this.post(`${this.base(workspaceSlug, projectId)}/reports/${reportId}/approve/`, { markdown })
      .then((res) => res?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}

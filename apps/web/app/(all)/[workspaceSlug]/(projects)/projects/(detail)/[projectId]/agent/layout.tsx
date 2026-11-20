/**
 * Copyright (c) 2026-present Orbit contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Outlet } from "react-router";
// components
import { AppHeader } from "@/components/core/app-header";
import { ContentWrapper } from "@/components/core/content-wrapper";
import { OrbitAgentHeader } from "@/components/orbit-agent/header";

export default function ProjectAgentLayout() {
  return (
    <>
      <AppHeader header={<OrbitAgentHeader />} />
      <ContentWrapper>
        <Outlet />
      </ContentWrapper>
    </>
  );
}

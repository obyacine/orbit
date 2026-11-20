/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import * as React from "react";

export type PlaneLogoProps = React.ComponentPropsWithoutRef<"svg">;

/** Orbit brand mark. */
export function PlaneLogo({ width = "52", height = "52", className, color = "currentColor" }: PlaneLogoProps) {
  return (
    <svg width={width} height={height} viewBox="0 0 52 52" xmlns="http://www.w3.org/2000/svg" className={className}>
      <ellipse cx="26" cy="26" rx="23" ry="9" fill="none" stroke={color} strokeWidth="3.5" transform="rotate(-25 26 26)" />
      <circle cx="26" cy="26" r="11" fill={color} />
      <circle cx="46" cy="16.5" r="4" fill={color} />
    </svg>
  );
}

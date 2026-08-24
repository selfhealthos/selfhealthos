"use client";

import { setNavCollapsed, useNavCollapsed } from "./navCollapse";

/** Collapses the sidebar to an icon-only rail. Sits top-right of the sidebar,
 *  and is icon-only there - same 7-square button as the top nav's icons.
 *  Desktop only: below `lg` the sidebar is already a short scrolling strip
 *  with nothing to collapse. */
export function NavCollapseToggle() {
  const collapsed = useNavCollapsed();
  const label = collapsed ? "Expand menu" : "Collapse menu";

  return (
    <button
      type="button"
      onClick={() => setNavCollapsed(!collapsed)}
      aria-label={label}
      aria-expanded={!collapsed}
      title={label}
      className="hidden size-7 items-center justify-center rounded-md text-ink-muted transition-colors hover:bg-surface-2 hover:text-ink lg:flex"
    >
      {/* A panel with its sidebar column shaded while the sidebar is open, and
          hollow once it is collapsed - the same shape browsers use for their
          own sidebar toggle, which survives being drawn at 16px better than a
          chevron does. */}
      <svg
        viewBox="0 0 24 24"
        className="size-4"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.6}
        aria-hidden
      >
        <rect x="3" y="4.5" width="18" height="15" rx="2.5" />
        <path d="M9.3 4.5v15" />
        {!collapsed && (
          <rect
            x="4.6"
            y="6.1"
            width="3.6"
            height="11.8"
            rx="1"
            fill="currentColor"
            stroke="none"
            opacity={0.35}
          />
        )}
      </svg>
    </button>
  );
}

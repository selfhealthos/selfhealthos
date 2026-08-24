"use client";

import { useEffect, useState } from "react";

/**
 * Sidebar collapse state, kept on <html data-nav> rather than in React state
 * alone.
 *
 * The attribute is what the CSS (`lg:nav-collapsed:` in globals.css) actually
 * keys off, and the inline script in the root layout stamps it before first
 * paint - same trick as the theme toggle, for the same reason: a stored
 * "collapsed" that only landed after hydration would paint the full-width
 * sidebar first and snap it narrow.
 *
 * The hook below exists only for the bits CSS can't do (the toggle's icon and
 * label, the tooltips that are useful only on the icon rail); an event keeps
 * every subscriber in sync since there's no shared React state here.
 */

export const NAV_STORAGE_KEY = "selfhealthos-nav";
const NAV_EVENT = "selfhealthos-nav-change";

export function setNavCollapsed(collapsed: boolean) {
  document.documentElement.setAttribute(
    "data-nav",
    collapsed ? "collapsed" : "expanded",
  );
  try {
    window.localStorage.setItem(
      NAV_STORAGE_KEY,
      collapsed ? "collapsed" : "expanded",
    );
  } catch {
    // Private mode / storage disabled: the toggle still works for this page.
  }
  window.dispatchEvent(new Event(NAV_EVENT));
}

/**
 * Always false on the server and on the first client render - reading the
 * attribute during render would be a hydration mismatch. Nothing renders
 * differently enough for that first frame to matter.
 */
export function useNavCollapsed() {
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const read = () =>
      setCollapsed(
        document.documentElement.getAttribute("data-nav") === "collapsed",
      );

    read();
    window.addEventListener(NAV_EVENT, read);
    return () => window.removeEventListener(NAV_EVENT, read);
  }, []);

  return collapsed;
}

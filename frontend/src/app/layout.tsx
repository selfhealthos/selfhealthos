import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "selfhealthos",
  description: "Self-hosted nutrition and fitness tracker",
};

// Dark is the default theme (see globals.css) - this runs before first paint
// so a stored preference never flashes the wrong theme first. Always sets the
// attribute explicitly (never leaves it absent): Tailwind's `dark:` variant
// is redefined in globals.css to key off data-theme="dark" specifically, and
// ThemeToggle does the same on every change.
const NO_FLASH_THEME_SCRIPT = `
(function () {
  try {
    var stored = localStorage.getItem("selfhealthos-theme");
    document.documentElement.setAttribute("data-theme", stored === "light" ? "light" : "dark");
  } catch (e) {
    document.documentElement.setAttribute("data-theme", "dark");
  }
})();
`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    // The theme script below sets data-theme on this element before React
    // hydrates, on purpose - that's what avoids a flash of the wrong theme.
    // suppressHydrationWarning stops React from flagging the mismatch that
    // creates, without turning off hydration warnings anywhere else.
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH_THEME_SCRIPT }} />
      </head>
      <body className="min-h-screen bg-bg text-ink antialiased">{children}</body>
    </html>
  );
}

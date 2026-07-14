// Plain (non-"use client") module: shared between app/layout.tsx (a Server Component,
// which needs this at render time to build the anti-FOUC inline script) and
// ThemeProvider.tsx (a Client Component). Keeping it out of ThemeProvider.tsx matters -
// Next's RSC boundary wraps every export of a "use client" file in a client reference
// when imported from a Server Component, including plain constants, so a server-side
// import of THEME_STORAGE_KEY from ThemeProvider.tsx would not resolve to the real string.
export const THEME_STORAGE_KEY = "crag_theme";

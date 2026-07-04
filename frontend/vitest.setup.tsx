import "@testing-library/jest-dom";
import React from "react";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});

// next/navigation's useRouter() throws outside a real App Router tree, and next/link
// pulls in the same router context for prefetching - both are mocked globally so
// component tests can render pages/providers in plain jsdom without a full Next runtime.
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) =>
    React.createElement("a", { href, ...props }, children),
}));

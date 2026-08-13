"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearAuth, getStoredUser } from "@/lib/api";
import { useEffect, useState } from "react";

type AppShellProps = {
  children: React.ReactNode;
  /** Full-viewport layout for chat workspace (no content max-width / padding). */
  variant?: "default" | "immersive";
};

export function AppShell({ children, variant = "default" }: AppShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [name, setName] = useState("");
  const [role, setRole] = useState("");

  useEffect(() => {
    const u = getStoredUser();
    setName(u?.name ?? "");
    setRole(u?.role ?? "");
  }, [pathname]);

  const links =
    role === "admin"
      ? [
          { href: "/admin", label: "Create" },
          { href: "/admin/settings", label: "Brief" },
          { href: "/admin/workspace", label: "Space" },
          { href: "/feed", label: "Feed" },
        ]
      : [{ href: "/feed", label: "Feed" }];

  function logout() {
    clearAuth();
    router.push("/login");
  }

  const isActive = (href: string) =>
    pathname === href || (href !== "/admin" && pathname.startsWith(href));

  const immersive = variant === "immersive";

  return (
    <div
      className={
        immersive
          ? "flex h-dvh flex-col overflow-hidden bg-[var(--canvas)]"
          : "min-h-dvh bg-[var(--canvas)] pb-[calc(4.5rem+env(safe-area-inset-bottom))] sm:pb-0"
      }
    >
      <header
        className={`z-40 shrink-0 border-b border-[var(--line)] bg-[var(--surface)]/90 backdrop-blur-xl ${
          immersive ? "relative" : "sticky top-0"
        }`}
        style={{ paddingTop: "env(safe-area-inset-top)" }}
      >
        <div
          className={`mx-auto flex items-center justify-between gap-3 px-4 py-3 sm:px-6 ${
            immersive ? "max-w-none" : "max-w-5xl sm:py-3.5"
          }`}
        >
          <Link
            href={role === "admin" ? "/admin" : "/feed"}
            className="group flex items-baseline gap-2"
          >
            <span className="font-display text-[1.3rem] leading-none tracking-tight text-fjord sm:text-[1.45rem]">
              OER Social
            </span>
            <span className="hidden text-[10px] font-medium uppercase tracking-[0.16em] text-mist sm:inline">
              Clinical learning
            </span>
          </Link>

          <nav className="hidden items-center gap-0.5 sm:flex">
            {links.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                className={`rounded-md px-3 py-2 text-sm transition-colors ${
                  isActive(l.href)
                    ? "bg-ice/80 font-medium text-fjord"
                    : "text-ink/50 hover:bg-ice/40 hover:text-fjord"
                }`}
              >
                {l.label}
              </Link>
            ))}
            <button
              type="button"
              onClick={logout}
              className="ml-2 rounded-md px-3 py-2 text-xs font-medium uppercase tracking-[0.12em] text-mist transition-colors hover:text-fjord"
            >
              Log out
            </button>
          </nav>

          <span className="max-w-[9rem] truncate text-right text-xs text-ink/45 sm:hidden">
            {name || role}
          </span>
        </div>
      </header>

      {immersive ? (
        <div className="flex min-h-0 flex-1 flex-col">{children}</div>
      ) : (
        <main className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6 sm:py-10">
          {children}
        </main>
      )}

      {!immersive ? (
        <nav
          className="fixed inset-x-0 bottom-0 z-40 border-t border-[var(--line)] bg-[var(--surface)]/95 backdrop-blur-xl sm:hidden"
          style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
        >
          <div className="mx-auto flex max-w-5xl">
            {links.map((l) => {
              const active = isActive(l.href);
              return (
                <Link
                  key={l.href}
                  href={l.href}
                  className={`flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 px-1 text-[11px] font-medium uppercase tracking-[0.1em] ${
                    active ? "text-fjord" : "text-mist"
                  }`}
                >
                  <span
                    className={`h-0.5 w-5 rounded-full ${active ? "bg-fjord" : "bg-transparent"}`}
                    aria-hidden
                  />
                  {l.label}
                </Link>
              );
            })}
            <button
              type="button"
              onClick={logout}
              className="flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 px-1 text-[11px] font-medium uppercase tracking-[0.1em] text-mist"
            >
              <span className="h-0.5 w-5 bg-transparent" aria-hidden />
              Out
            </button>
          </div>
        </nav>
      ) : null}
    </div>
  );
}

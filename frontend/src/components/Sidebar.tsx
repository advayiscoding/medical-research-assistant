"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";
import {
  LayoutDashboard,
  Search,
  MessagesSquare,
  FileText,
  History,
  LogOut,
  Stethoscope,
} from "lucide-react";
import { useAuth } from "@/lib/auth";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/search", label: "Search", icon: Search },
  { href: "/chat", label: "Chat", icon: MessagesSquare },
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/history", label: "History", icon: History },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)]">
      <div className="flex items-center gap-2 px-5 py-5">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--color-primary)] text-white">
          <Stethoscope size={20} aria-hidden />
        </span>
        <span className="font-sans text-lg font-semibold">MedResearch</span>
      </div>

      <nav className="flex-1 space-y-1 px-3" aria-label="Primary">
        {NAV.map(({ href, label, icon: Icon }) => {
          // Active if exact match or a sub-route (e.g. /chat/[id]).
          const active = pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={clsx(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                active
                  ? "bg-cyan-50 text-[var(--color-primary)]"
                  : "text-[var(--color-muted-foreground)] hover:bg-[var(--color-surface-muted)] hover:text-[var(--color-foreground)]",
              )}
            >
              <Icon size={18} aria-hidden />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-[var(--color-border)] p-3">
        <div className="truncate px-3 py-1 text-xs text-[var(--color-muted-foreground)]">
          {user?.email}
        </div>
        <button
          onClick={logout}
          className="mt-1 flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-[var(--color-muted-foreground)] transition-colors hover:bg-[var(--color-surface-muted)] hover:text-[var(--color-destructive)] cursor-pointer"
        >
          <LogOut size={18} aria-hidden />
          Sign out
        </button>
      </div>
    </aside>
  );
}

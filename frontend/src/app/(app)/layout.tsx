"use client";

// Shell for every authenticated page: the RequireAuth guard + persistent
// sidebar. The (app) route group means all these pages share this chrome
// without affecting the URL (/dashboard, not /app/dashboard).

import { RequireAuth } from "@/lib/auth";
import { Sidebar } from "@/components/Sidebar";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <div className="flex min-h-dvh">
        <Sidebar />
        <main className="flex-1 overflow-hidden">{children}</main>
      </div>
    </RequireAuth>
  );
}

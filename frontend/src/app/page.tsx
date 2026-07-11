"use client";

// Entry point: bounce to the app or the login screen depending on auth state.
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export default function Home() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    router.replace(user ? "/dashboard" : "/login");
  }, [user, loading, router]);

  return (
    <div className="flex min-h-dvh items-center justify-center text-[var(--color-muted-foreground)]">
      Loading…
    </div>
  );
}

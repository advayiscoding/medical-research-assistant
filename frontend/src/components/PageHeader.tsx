export function PageHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}) {
  return (
    <header className="flex items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-surface)] px-8 py-5">
      <div>
        <h1 className="font-sans text-xl font-semibold">{title}</h1>
        {subtitle && (
          <p className="mt-0.5 text-sm text-[var(--color-muted-foreground)]">{subtitle}</p>
        )}
      </div>
      {action}
    </header>
  );
}

import type { ReactNode } from "react";

export function Panel({
  title,
  children,
  action,
  lead,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
  lead?: string;
}) {
  return (
    <section className="panel p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="brand-mark text-[1.35rem] font-medium tracking-tight text-[var(--ink)]">{title}</h2>
          {lead ? <p className="muted mt-1 max-w-2xl text-sm">{lead}</p> : null}
        </div>
        {action ? <div className="flex flex-wrap gap-2">{action}</div> : null}
      </div>
      {children}
    </section>
  );
}

export function PageIntro({
  kicker,
  title,
  body,
}: {
  kicker?: string;
  title: string;
  body?: string;
}) {
  return (
    <header className="mb-5">
      {kicker ? (
        <p className="mb-1 text-xs font-medium uppercase tracking-[0.16em] text-[var(--muted)]">{kicker}</p>
      ) : null}
      <h1 className="brand-mark text-3xl font-medium tracking-tight text-[var(--ink)] md:text-[2.1rem]">{title}</h1>
      {body ? <p className="mt-2 max-w-2xl text-sm leading-relaxed text-[var(--muted)]">{body}</p> : null}
    </header>
  );
}

export function Banner({ text }: { text: string }) {
  return (
    <p className="border-b border-[rgba(154,103,0,0.25)] bg-[rgba(255,236,179,0.55)] px-4 py-2 text-sm text-[#5c4300]">
      {text}
    </p>
  );
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof Error ? error.message : "The request failed.";
  return <p className="text-sm text-[var(--danger)]">{message}</p>;
}

export function Button({
  children,
  onClick,
  kind = "primary",
  type = "button",
  disabled = false,
}: {
  children: ReactNode;
  onClick?: () => void;
  kind?: "primary" | "quiet" | "danger";
  type?: "button" | "submit";
  disabled?: boolean;
}) {
  const styles = {
    primary: "btn-primary",
    quiet: "btn-quiet",
    danger: "btn-danger",
  }[kind];
  return (
    <button type={type} disabled={disabled} onClick={onClick} className={`btn ${styles}`}>
      {children}
    </button>
  );
}

export function Field({
  label,
  value,
  onChange,
  secret = false,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  secret?: boolean;
  placeholder?: string;
}) {
  return (
    <label className="block text-sm">
      <span className="muted mb-1 block text-xs font-medium uppercase tracking-[0.08em]">{label}</span>
      <input
        className="field"
        type={secret ? "password" : "text"}
        autoComplete="off"
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

export function CodeBlock({ children, soft = false }: { children: string; soft?: boolean }) {
  return <pre className={soft ? "code-block-soft" : "code-block"}>{children}</pre>;
}

export function statusClass(status: string): string {
  if (status === "approved") return "status-chip status-approved";
  if (status === "rejected" || status === "failed") return "status-chip status-rejected";
  if (status === "unresolved") return "status-chip status-unresolved";
  return "status-chip status-default";
}

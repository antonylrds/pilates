import type { ReactNode } from "react";

export function Badge({ tone, children }: { tone: string; children: ReactNode }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function Loading() {
  return <div className="muted pad">Carregando…</div>;
}

export function ErrorBox({ message }: { message: string }) {
  return <div className="alert alert-error">{message}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

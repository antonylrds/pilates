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

/** Ícone "?" que explica o campo ao passar o mouse ou focar (também funciona ao tocar). */
export function HelpTip({ children, align = "left" }: { children: ReactNode; align?: "left" | "right" }) {
  return (
    <span className="help-tip">
      <button type="button" className="help-tip-btn" aria-label="O que significa este valor?">
        ?
      </button>
      <span role="tooltip" className={`help-tip-text help-tip-${align}`}>
        {children}
      </span>
    </span>
  );
}

import type { ReactNode } from "react";

type Props = {
  title: string;
  children: ReactNode;
  confirmLabel: string;
  /** "danger" para ações destrutivas (vermelho); "warning" para ações que desfazem algo. */
  tone?: "danger" | "warning";
  busy?: boolean;
  /** Bloqueia só o botão de confirmar (ex.: a ação não é permitida agora). */
  confirmDisabled?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

/** Confirmação dentro do painel, no lugar do `window.confirm` do navegador. */
export function ConfirmPanel({ title, children, confirmLabel, tone = "warning", busy, confirmDisabled, onConfirm, onCancel }: Props) {
  return (
    <div className={`picker confirm-panel is-${tone}`} role="alertdialog" aria-label={title}>
      <div className="picker-header">
        <strong>{title}</strong>
      </div>
      <div className="confirm-body">{children}</div>
      <div className="cancel-actions">
        <button type="button" className="btn btn-ghost" disabled={busy} onClick={onCancel}>
          Voltar
        </button>
        <button
          type="button"
          className={`btn ${tone === "danger" ? "btn-danger" : "btn-primary"}`}
          disabled={busy || confirmDisabled}
          onClick={onConfirm}
          autoFocus
        >
          {confirmLabel}
        </button>
      </div>
    </div>
  );
}

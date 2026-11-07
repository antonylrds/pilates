import { type ReactNode, useEffect } from "react";

type Props = {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
};

export function Modal({ title, subtitle, onClose, children, footer, wide }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className={`modal ${wide ? "modal-wide" : ""}`} role="dialog" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <header className="modal-header">
          <div className="modal-title">
            <h2 title={title}>{title}</h2>
            {subtitle && <p className="muted small">{subtitle}</p>}
          </div>
          <button className="btn btn-ghost modal-close" onClick={onClose} aria-label="Fechar">
            ✕
          </button>
        </header>
        <div className="modal-body">{children}</div>
        {footer && <footer className="modal-footer">{footer}</footer>}
      </div>
    </div>
  );
}

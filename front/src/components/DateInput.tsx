import { type ChangeEvent, useEffect, useRef, useState } from "react";

/**
 * Campo de data sempre no formato dd/mm/aaaa, independente do idioma do navegador
 * (o `<input type="date">` nativo segue a localidade do sistema, ex.: mm/dd/yyyy).
 *
 * Recebe e devolve a data em ISO (`yyyy-mm-dd`), como o input nativo; `""` quando vazio.
 * O botão de calendário abre o seletor nativo.
 */
type Props = {
  value: string;
  onChange: (iso: string) => void;
  min?: string;
  max?: string;
  required?: boolean;
  className?: string;
  title?: string;
  "aria-label"?: string;
};

function isoToText(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : "";
}

function textToISO(text: string): string | null {
  const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(text);
  if (!m) return null;
  const [, dd, mm, yyyy] = m;
  const d = new Date(Number(yyyy), Number(mm) - 1, Number(dd));
  if (d.getFullYear() !== Number(yyyy) || d.getMonth() !== Number(mm) - 1 || d.getDate() !== Number(dd)) return null;
  return `${yyyy}-${mm}-${dd}`;
}

function mask(raw: string): string {
  const digits = raw.replace(/\D/g, "").slice(0, 8);
  if (digits.length <= 2) return digits;
  if (digits.length <= 4) return `${digits.slice(0, 2)}/${digits.slice(2)}`;
  return `${digits.slice(0, 2)}/${digits.slice(2, 4)}/${digits.slice(4)}`;
}

function rangeError(iso: string, min?: string, max?: string): string {
  if (min && iso < min) return `A data deve ser a partir de ${isoToText(min)}.`;
  if (max && iso > max) return `A data deve ser até ${isoToText(max)}.`;
  return "";
}

export function DateInput({ value, onChange, min, max, required, className, title, ...rest }: Props) {
  const [text, setText] = useState(() => isoToText(value));
  const textRef = useRef<HTMLInputElement>(null);
  const pickerRef = useRef<HTMLInputElement>(null);

  // Mantém o texto em sincronia quando o valor muda por fora (ex.: botão "Hoje").
  useEffect(() => {
    setText((current) => (textToISO(current) === value ? current : isoToText(value)));
  }, [value]);

  function validate(next: string) {
    const el = textRef.current;
    if (!el) return;
    if (!next) return el.setCustomValidity("");
    const iso = textToISO(next);
    el.setCustomValidity(iso ? rangeError(iso, min, max) : "Informe a data no formato dd/mm/aaaa.");
  }

  function handleText(e: ChangeEvent<HTMLInputElement>) {
    const next = mask(e.target.value);
    setText(next);
    validate(next);
    if (!next) return onChange("");
    const iso = textToISO(next);
    if (iso && !rangeError(iso, min, max)) onChange(iso);
  }

  function handleBlur() {
    // Texto incompleto/inválido volta para o último valor válido.
    if (text && !textToISO(text)) {
      setText(isoToText(value));
      validate(isoToText(value));
    }
  }

  function openPicker() {
    const el = pickerRef.current;
    if (!el) return;
    try {
      el.showPicker();
    } catch {
      el.focus();
    }
  }

  return (
    <span className={`date-input ${className ?? ""}`.trim()} title={title}>
      <input
        ref={textRef}
        type="text"
        inputMode="numeric"
        placeholder="dd/mm/aaaa"
        value={text}
        onChange={handleText}
        onBlur={handleBlur}
        required={required}
        aria-label={rest["aria-label"]}
        maxLength={10}
      />
      <button type="button" className="date-input-btn" onClick={openPicker} aria-label="Abrir calendário" tabIndex={-1}>
        📅
      </button>
      <input
        ref={pickerRef}
        type="date"
        className="date-input-native"
        value={value}
        min={min}
        max={max}
        tabIndex={-1}
        aria-hidden="true"
        onChange={(e) => {
          setText(isoToText(e.target.value));
          validate(isoToText(e.target.value));
          onChange(e.target.value);
        }}
      />
    </span>
  );
}

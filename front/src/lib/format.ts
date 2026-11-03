const pad = (n: number) => String(n).padStart(2, "0");

/** Date local -> "YYYY-MM-DD" (sem conversão de fuso). */
export const toISO = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

/** "YYYY-MM-DD" -> Date local. */
export function parseISO(s: string): Date {
  const [y, m, d] = s.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d);
}

export const addDays = (d: Date, days: number) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + days);

export function mondayOf(d: Date): Date {
  const offset = (d.getDay() + 6) % 7; // segunda = 0
  return addDays(d, -offset);
}

export const todayISO = () => toISO(new Date());

export const fmtDate = (s: string) => parseISO(s).toLocaleDateString("pt-BR");

export const fmtWeekday = (s: string) =>
  parseISO(s).toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "long" });

export const fmtShortDay = (s: string) =>
  parseISO(s).toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit" });

export const fmtHour = (h: number) => `${pad(h)}:00`;

export const money = (v: string | number) =>
  Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

export const fmtDateTime = (s: string) =>
  new Date(s).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

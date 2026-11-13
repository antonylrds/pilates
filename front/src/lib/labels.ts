export const lessonStatus: Record<string, string> = {
  confirmed: "Confirmada",
  inactive: "Inativa",
  cancelled: "Cancelada",
  completed: "Concluída",
};

export const attendanceStatus: Record<string, string> = {
  pending: "Pendente",
  present: "Presente",
  absent: "Falta",
  rescheduled: "Reagendado",
};

export const attendanceTone: Record<string, string> = {
  pending: "neutral",
  present: "success",
  absent: "danger",
  rescheduled: "warning",
};

export const subscriptionStatus: Record<string, string> = {
  active: "Ativo",
  exhausted: "Esgotado",
  cancelled: "Cancelado",
};

export const subscriptionUsage: Record<string, string> = {
  in_use: "Em uso",
  queued: "Aguardando",
  finished: "Encerrado",
  cancelled: "Cancelado",
};

export const usageTone: Record<string, string> = {
  in_use: "success",
  queued: "info",
  finished: "neutral",
  cancelled: "danger",
};

/** Frequência do plano: "2x por semana" ou "sem recorrência" (0 = só aulas avulsas). */
export function perWeekLabel(n: number, short = false): string {
  if (n === 0) return "sem recorrência";
  return short ? `${n}x/semana` : `${n}x por semana`;
}

export function roleLabel(role: string): string {
  return role === "admin" ? "Administrador" : "Professor";
}

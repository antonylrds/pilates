import { NavLink, Outlet, useLocation } from "react-router-dom";

import { api, call } from "../lib/api";
import { useAsync } from "../lib/hooks";
import { useSession } from "../lib/session";

const NAV = [
  { to: "/", label: "Agenda", icon: "▦", end: true },
  { to: "/finalizar", label: "Finalizar aulas", icon: "✓", badge: "pending" },
  { to: "/salas", label: "Salas e turmas", icon: "▤" },
  { to: "/alunos", label: "Alunos", icon: "◉" },
  { to: "/catalogo", label: "Planos e serviços", icon: "★" },
  { to: "/professores", label: "Professores", icon: "✦" },
  { to: "/avisos", label: "Avisos", icon: "◔", badge: "unread" },
] as const;

export function Layout() {
  const { session, logout } = useSession();
  const location = useLocation();
  const unread = useAsync(
    () => call(api.GET("/api/v1/notifications", { params: { query: { unread_only: true } } })),
    [location.pathname],
  );
  const pending = useAsync(() => call(api.GET("/api/v1/lessons/pending")), [location.pathname]);
  const badges: Record<string, number> = {
    unread: unread.data?.length ?? 0,
    pending: pending.data?.length ?? 0,
  };

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">P</span>
          <div>
            <div className="brand-name">{session?.studio.name}</div>
            <div className="brand-sub">Gestão do estúdio</div>
          </div>
        </div>
        <nav className="nav">
          {NAV.map((item) => {
            const count = "badge" in item ? badges[item.badge] : 0;
            return (
              <NavLink key={item.to} to={item.to} end={"end" in item ? item.end : false} className="nav-link">
                <span className="nav-icon" aria-hidden>
                  {item.icon}
                </span>
                <span>{item.label}</span>
                {count > 0 && <span className="nav-badge">{count}</span>}
              </NavLink>
            );
          })}
        </nav>
        <div className="sidebar-footer">
          <div>
            <div className="user-name">{session?.user.name}</div>
            <div className="user-role">{session?.user.role === "admin" ? "Administrador" : "Professor"}</div>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={logout}>
            Sair
          </button>
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}

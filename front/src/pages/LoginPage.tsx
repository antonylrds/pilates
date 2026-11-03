import { type FormEvent, useState } from "react";

import { ErrorBox } from "../components/ui";
import { useSession } from "../lib/session";

// Em desenvolvimento o formulário já vem preenchido com o estúdio demo.
const DEMO = import.meta.env.DEV ? { studio: "demo", email: "admin@demo.com", password: "admin123" } : null;

export function LoginPage() {
  const { login } = useSession();
  const [studio, setStudio] = useState(DEMO?.studio ?? "");
  const [email, setEmail] = useState(DEMO?.email ?? "");
  const [password, setPassword] = useState(DEMO?.password ?? "");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await login(studio, email, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <form className="login-card" onSubmit={submit}>
        <div className="brand brand-center">
          <span className="brand-mark">P</span>
          <div className="brand-name">Pilates Studio</div>
        </div>
        <h1>Entrar</h1>
        <label className="field">
          <span>Estúdio</span>
          <input value={studio} onChange={(e) => setStudio(e.target.value)} placeholder="ex.: demo" required />
        </label>
        <label className="field">
          <span>E-mail</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label className="field">
          <span>Senha</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {error && <ErrorBox message={error} />}
        <button className="btn btn-primary btn-block" disabled={busy}>
          {busy ? "Entrando…" : "Entrar"}
        </button>
        {DEMO && <p className="muted small center">Professora: ana@demo.com / admin123</p>}
      </form>
    </div>
  );
}

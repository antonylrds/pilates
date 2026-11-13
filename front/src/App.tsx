import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { useSession } from "./lib/session";
import { AgendaPage } from "./pages/AgendaPage";
import { CashPage } from "./pages/CashPage";
import { FinalizePage } from "./pages/FinalizePage";
import { LoginPage } from "./pages/LoginPage";
import { NotificationsPage } from "./pages/NotificationsPage";
import { PaymentsPage } from "./pages/PaymentsPage";
import { PlatformPage } from "./pages/PlatformPage";
import { RoomsPage } from "./pages/RoomsPage";
import { CatalogPage } from "./pages/CatalogPage";
import { StudentsPage } from "./pages/StudentsPage";
import { TeachersPage } from "./pages/TeachersPage";

export function App() {
  const { session, platform } = useSession();

  // Usuário da plataforma sem estúdio aberto: escolhe o estúdio e a visão (admin/professor).
  if (!session && platform) {
    return (
      <Routes>
        <Route path="*" element={<PlatformPage />} />
      </Routes>
    );
  }

  if (!session) {
    return (
      <Routes>
        <Route path="*" element={<LoginPage />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<AgendaPage />} />
        <Route path="alunos" element={<StudentsPage />} />
        <Route path="alunos/:studentId" element={<StudentsPage />} />
        <Route path="finalizar" element={<FinalizePage />} />
        <Route path="finalizar/servico/:sessionId" element={<FinalizePage />} />
        <Route path="finalizar/:groupId/:date" element={<FinalizePage />} />
        <Route path="salas" element={<RoomsPage />} />
        <Route path="catalogo" element={<CatalogPage />} />
        <Route path="servicos" element={<Navigate to="/catalogo?aba=servicos" replace />} />
        <Route path="professores" element={<TeachersPage />} />
        <Route path="caixa" element={<CashPage />} />
        <Route path="pagamentos" element={<PaymentsPage />} />
        <Route path="avisos" element={<NotificationsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

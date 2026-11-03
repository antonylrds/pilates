import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { useSession } from "./lib/session";
import { AgendaPage } from "./pages/AgendaPage";
import { FinalizePage } from "./pages/FinalizePage";
import { LoginPage } from "./pages/LoginPage";
import { NotificationsPage } from "./pages/NotificationsPage";
import { RoomsPage } from "./pages/RoomsPage";
import { StudentsPage } from "./pages/StudentsPage";
import { TeachersPage } from "./pages/TeachersPage";

export function App() {
  const { session } = useSession();

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
        <Route path="finalizar/:groupId/:date" element={<FinalizePage />} />
        <Route path="salas" element={<RoomsPage />} />
        <Route path="professores" element={<TeachersPage />} />
        <Route path="avisos" element={<NotificationsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

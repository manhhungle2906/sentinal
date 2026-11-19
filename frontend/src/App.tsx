import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./components/AppLayout";
import { LoadingState } from "./components/States";
import { AlertDetailPage } from "./pages/AlertDetailPage";
import { AlertsPage } from "./pages/AlertsPage";
import { EventsPage } from "./pages/EventsPage";
import { LoginPage } from "./pages/LoginPage";
import { OverviewPage } from "./pages/OverviewPage";
import { SourcesPage } from "./pages/SourcesPage";
import { TeamPage } from "./pages/TeamPage";
import { useAuth } from "./state/auth-context";

export default function App() {
  const { user, loading } = useAuth();

  if (loading) {
    return <LoadingState label="Starting API Sentinel…" />;
  }

  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route path="/login" element={<Navigate to="/" replace />} />
      <Route element={<AppLayout />}>
        <Route index element={<OverviewPage />} />
        <Route path="/events" element={<EventsPage />} />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route path="/alerts/:alertId" element={<AlertDetailPage />} />
        <Route path="/sources" element={<SourcesPage />} />
        <Route path="/team" element={<TeamPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "@/lib/query";
import { Toaster } from "@/components/ui/sonner";

import { AuthGate } from "@/components/AuthGate";
import { AppShell } from "@/components/AppShell";
import { LoginPage } from "@/pages/LoginPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { HealthPage } from "@/pages/HealthPage";
import { ChangePasswordPage } from "@/pages/ChangePasswordPage";
import { SessionsPage } from "@/pages/SessionsPage";
import { UsersPage } from "@/pages/UsersPage";
import { WorkoutsPage } from "@/pages/WorkoutsPage";
import { MeasurementsPage } from "@/pages/MeasurementsPage";
import { PRsPage } from "@/pages/PRsPage";
import { ExercisesPage } from "@/pages/ExercisesPage";
import { AIUsagePage } from "@/pages/AIUsagePage";
import { AdminUsersPage } from "@/pages/AdminUsersPage";
import { PlansPage } from "@/pages/PlansPage";
import { PlanDetailPage } from "@/pages/PlanDetailPage";
import { ConfigPage } from "@/pages/ConfigPage";
import { PromptsPage } from "@/pages/PromptsPage";
import { PlaygroundPage } from "@/pages/PlaygroundPage";
import { BackupPage } from "@/pages/BackupPage";
import { LogsPage } from "@/pages/LogsPage";
import { TriggersPage } from "@/pages/TriggersPage";

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename="/admin">
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/"
            element={
              <AuthGate>
                <AppShell />
              </AuthGate>
            }
          >
            <Route index element={<DashboardPage />} />
            <Route path="health" element={<HealthPage />} />
            <Route path="account/password" element={<ChangePasswordPage />} />
            <Route path="account/sessions" element={<SessionsPage />} />
            <Route path="users" element={<UsersPage />} />
            <Route path="plans" element={<PlansPage />} />
            <Route path="plans/:id" element={<PlanDetailPage />} />
            <Route path="workouts" element={<WorkoutsPage />} />
            <Route path="measurements" element={<MeasurementsPage />} />
            <Route path="prs" element={<PRsPage />} />
            <Route path="exercises" element={<ExercisesPage />} />
            <Route path="ai/usage" element={<AIUsagePage />} />
            <Route path="ai/config" element={<ConfigPage />} />
            <Route path="ai/prompts" element={<PromptsPage />} />
            <Route path="ai/playground" element={<PlaygroundPage />} />
            <Route path="admin-users" element={<AdminUsersPage />} />
            <Route path="ops/backup" element={<BackupPage />} />
            <Route path="ops/logs" element={<LogsPage />} />
            <Route path="ops/triggers" element={<TriggersPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster />
    </QueryClientProvider>
  );
}

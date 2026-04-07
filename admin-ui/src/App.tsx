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
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster />
    </QueryClientProvider>
  );
}

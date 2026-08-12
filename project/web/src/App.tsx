import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { ToastProvider } from "@/components/ui/Toast";
import { HealthProvider } from "@/hooks/useHealth";
import { AskView } from "@/features/ask/AskView";
import { CorpusView } from "@/features/corpus/CorpusView";
import { SettingsView } from "@/features/settings/SettingsView";

export function App() {
  return (
    <ToastProvider>
      <HealthProvider>
        <AppShell>
          <Routes>
            <Route path="/" element={<AskView />} />
            <Route path="/corpus" element={<CorpusView />} />
            <Route path="/settings" element={<SettingsView />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AppShell>
      </HealthProvider>
    </ToastProvider>
  );
}

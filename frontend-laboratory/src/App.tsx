import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { DirectoriesPage } from "./pages/DirectoriesPage";
import { ExperimentDetailsPage } from "./pages/ExperimentDetailsPage";
import { ExperimentFormPage } from "./pages/ExperimentFormPage";
import { JournalPage } from "./pages/JournalPage";
import { FuelQualityPage } from "./fuel-quality/FuelQualityPage";

export default function App() {
  return <AppShell><Routes>
    <Route path="/" element={<Navigate to="/experiments" replace />} />
    <Route path="/experiments" element={<JournalPage />} />
    <Route path="/experiments/new" element={<ExperimentFormPage />} />
    <Route path="/experiments/:id" element={<ExperimentDetailsPage />} />
    <Route path="/experiments/:id/edit" element={<ExperimentFormPage />} />
    <Route path="/directories" element={<DirectoriesPage />} />
    <Route path="/fuel-quality" element={<FuelQualityPage />} />
    <Route path="*" element={<Navigate to="/experiments" replace />} />
  </Routes></AppShell>;
}

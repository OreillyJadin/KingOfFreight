import { useQuery } from "@tanstack/react-query";
import { Navigate, Route, Routes } from "react-router-dom";
import { api } from "./api";
import AppLayout from "./components/AppLayout";
import Inbox from "./pages/Inbox";
import Login from "./pages/Login";
import Status from "./pages/Status";
import Tracking from "./pages/Tracking";
import TruckStop from "./pages/TruckStop";

function ProtectedApp() {
  const auth = useQuery({ queryKey: ["auth"], queryFn: api.me });
  if (auth.isPending) {
    return (
      <div className="grid min-h-screen place-items-center bg-canvas text-slate-500">
        <span className="animate-pulse text-sm font-medium">Loading workspace…</span>
      </div>
    );
  }
  if (auth.isError || !auth.data?.authenticated) return <Navigate to="/login" replace />;
  return (
    <AppLayout>
      <Routes>
        <Route path="/inbox" element={<Inbox />} />
        <Route path="/truckstop" element={<TruckStop />} />
        <Route path="/status" element={<Status />} />
        <Route path="*" element={<Navigate to="/inbox" replace />} />
      </Routes>
    </AppLayout>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/t/:token" element={<Tracking />} />
      <Route path="/*" element={<ProtectedApp />} />
    </Routes>
  );
}

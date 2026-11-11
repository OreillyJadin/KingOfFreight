import { Loader2 } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Navigate, Route, Routes } from "react-router-dom";
import { api } from "./api";
import AppLayout from "./components/AppLayout";
import Inbox from "./pages/Inbox";
import CustomerUpdates from "./pages/CustomerUpdates";
import Login from "./pages/Login";
import Status from "./pages/Status";
import Settings from "./pages/Settings";
import Tracking from "./pages/Tracking";
import TruckStop from "./pages/TruckStop";
import SetPassword from "./pages/SetPassword";
import Users from "./pages/Users";
import Dashboard from "./pages/kof/Dashboard";
import KofTracking from "./pages/kof/KofTracking";
import Loads from "./pages/kof/Loads";
import Customers from "./pages/kof/Customers";
import Branches from "./pages/kof/Branches";
import Carriers from "./pages/kof/Carriers";
import Sales from "./pages/kof/Sales";
import { setBrokerTimeZone } from "./utils";

function ProtectedApp() {
  const auth = useQuery({ queryKey: ["auth"], queryFn: api.me });
  if (auth.isPending) {
    return (
      <div className="grid min-h-screen place-items-center bg-bg text-muted">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    );
  }
  if (auth.isError || !auth.data?.authenticated) return <Navigate to="/login" replace />;
  if (auth.data.must_set_password) return <Navigate to="/set-password" replace />;
  setBrokerTimeZone(auth.data.broker_timezone);
  return (
    <AppLayout>
      <Routes>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/tracking" element={<KofTracking />} />
        <Route path="/loads" element={<Loads />} />
        <Route path="/customers" element={<Customers />} />
        <Route path="/branches" element={<Branches />} />
        <Route path="/carriers" element={<Carriers />} />
        <Route path="/sales" element={<Sales />} />
        <Route path="/inbox" element={<Inbox />} />
        <Route path="/customer-updates" element={<CustomerUpdates />} />
        <Route path="/truckstop" element={<TruckStop />} />
        <Route path="/status" element={<Status />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/users" element={<Users />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AppLayout>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/set-password" element={<SetPassword />} />
      <Route path="/t/:token" element={<Tracking />} />
      <Route path="/*" element={<ProtectedApp />} />
    </Routes>
  );
}

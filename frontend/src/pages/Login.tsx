import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, LockKeyhole, Truck } from "lucide-react";
import { Navigate, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useToast } from "../useToast";

export default function Login() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const login = useMutation({
    mutationFn: api.login,
    onSuccess: async () => {
      await queryClient.invalidateQueries();
      showToast("Welcome back.");
      navigate("/inbox", { replace: true });
    },
    onError: (issue: Error) => setError(issue.message || "Unable to sign in."),
  });
  if (login.isSuccess) return <Navigate to="/inbox" replace />;
  return (
    <main className="grid min-h-screen bg-white md:grid-cols-[1.05fr_0.95fr]">
      <section className="relative hidden overflow-hidden bg-slate-950 px-12 py-14 text-white md:flex md:flex-col md:justify-between lg:px-20">
        <div className="absolute -right-28 -top-32 h-[420px] w-[420px] rounded-full border border-white/10" />
        <div className="absolute -right-10 -top-14 h-[285px] w-[285px] rounded-full border border-white/10" />
        <div className="relative flex items-center gap-3">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-blue-600">
            <Truck className="h-6 w-6" />
          </span>
          <span className="text-lg font-extrabold tracking-tight">KingOfFreight</span>
        </div>
        <div className="relative max-w-lg">
          <p className="mb-5 text-xs font-bold uppercase tracking-[0.22em] text-blue-300">
            Freight operations
          </p>
          <h1 className="text-4xl font-bold leading-tight tracking-tight lg:text-5xl">
            Keep every load moving.
          </h1>
          <p className="mt-5 max-w-md text-base leading-7 text-slate-300">
            One clear view of your inbox, active loads, driver check-ins, and customer updates.
          </p>
        </div>
        <p className="relative text-xs text-slate-500">A quieter way to run the day.</p>
      </section>
      <section className="flex min-h-screen items-center justify-center bg-canvas px-5 py-10 md:bg-white">
        <div className="w-full max-w-[410px]">
          <div className="mb-9 flex items-center gap-3 md:hidden">
            <span className="grid h-11 w-11 place-items-center rounded-xl bg-blue-600 text-white">
              <Truck className="h-6 w-6" />
            </span>
            <span className="text-lg font-extrabold text-slate-900">KingOfFreight</span>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-card sm:p-8 md:border-0 md:p-0 md:shadow-none">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-blue-600">
              Broker workspace
            </p>
            <h2 className="mt-2 text-3xl font-extrabold tracking-tight text-slate-900">
              Welcome back
            </h2>
            <p className="mt-2 text-sm text-slate-500">
              Sign in to pick up where you left off.
            </p>
            <form
              className="mt-8 space-y-5"
              onSubmit={(event) => {
                event.preventDefault();
                setError("");
                login.mutate(password);
              }}
            >
              <label className="block">
                <span className="mb-2 block text-sm font-semibold text-slate-700">
                  Broker password
                </span>
                <span className="relative block">
                  <LockKeyhole className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <input
                    autoFocus
                    required
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="Enter your password"
                    className="h-12 w-full rounded-xl border border-slate-300 bg-white pl-10 pr-3 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
                  />
                </span>
              </label>
              {error && (
                <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">
                  {error}
                </p>
              )}
              <button
                type="submit"
                disabled={login.isPending}
                className="flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 text-sm font-bold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-wait disabled:opacity-70"
              >
                {login.isPending ? "Signing in…" : "Sign in"}
                {!login.isPending && <ArrowRight className="h-4 w-4" />}
              </button>
            </form>
          </div>
          <p className="mt-6 text-center text-xs text-slate-400">
            Secure broker access · Single-user workspace
          </p>
        </div>
      </section>
    </main>
  );
}

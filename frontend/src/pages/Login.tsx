import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, LockKeyhole } from "lucide-react";
import { Navigate, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useToast } from "../useToast";
import { Button, Card, Input } from "../components/ui";
import { Wordmark } from "../components/Brand";
import ThemeToggle from "../components/ThemeToggle";

export default function Login() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  useEffect(() => {
    document.title = "Sign in · Fifth Wheel";
  }, []);
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
    <main className="relative grid min-h-screen bg-bg md:grid-cols-[1.05fr_0.95fr]">
      <ThemeToggle className="absolute right-4 top-4 z-20" />
      <section className="relative hidden overflow-hidden bg-hero px-12 py-14 text-hero-fg md:flex md:flex-col md:justify-between lg:px-20">
        <div className="absolute -left-40 bottom-[-180px] h-[460px] w-[460px] rounded-full bg-accent/10 blur-3xl" />
        <div className="absolute -right-28 -top-32 h-[420px] w-[420px] rounded-full border border-hero-fg/10" />
        <div className="absolute -right-10 -top-14 h-[285px] w-[285px] rounded-full border border-hero-fg/10" />
        <div className="relative">
          <Wordmark markClassName="h-11 w-11 text-accent" />
        </div>
        <div className="relative max-w-lg">
          <p className="mb-5 text-xs font-bold uppercase tracking-[0.22em] text-accent">
            Freight operations
          </p>
          <h1 className="text-4xl font-bold leading-tight tracking-tight lg:text-5xl">
            Every load, connected.
          </h1>
          <p className="mt-5 max-w-md text-base leading-7 text-hero-fg/70">
            One clear view of your inbox, active loads, driver check-ins, and customer updates.
          </p>
        </div>
        <p className="relative text-xs text-hero-fg/50">A quieter way to run the day.</p>
      </section>
      <section className="flex min-h-screen items-center justify-center bg-bg px-5 py-10 md:bg-surface">
        <div className="w-full max-w-[410px]">
          <div className="mb-9 md:hidden">
            <Wordmark markClassName="h-11 w-11 text-accent" />
          </div>
          <Card className="rounded-2xl p-6 sm:p-8 md:border-0 md:bg-transparent md:p-0 md:shadow-none">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-muted">
              Broker workspace
            </p>
            <h2 className="mt-2 text-3xl font-extrabold tracking-tight text-fg">
              Welcome back
            </h2>
            <p className="mt-2 text-sm text-muted">
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
                <span className="mb-2 block text-sm font-semibold text-fg-2">
                  Broker password
                </span>
                <span className="relative block">
                  <LockKeyhole className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle" />
                  <Input
                    autoFocus
                    required
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="Enter your password"
                    className="h-12 pl-10 pr-3"
                  />
                </span>
              </label>
              {error && (
                <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-ink" role="alert">
                  {error}
                </p>
              )}
              <Button
                type="submit"
                disabled={login.isPending}
                loading={login.isPending}
                variant="primary"
                full
                className="h-12 shadow-sm disabled:cursor-wait disabled:opacity-70"
              >
                {login.isPending ? "Signing in…" : "Sign in"}
                {!login.isPending && <ArrowRight className="h-4 w-4" />}
              </Button>
            </form>
          </Card>
          <p className="mt-6 text-center text-xs text-subtle">
            Secure broker access · Single-user workspace
          </p>
        </div>
      </section>
    </main>
  );
}

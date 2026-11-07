import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound } from "lucide-react";
import { Navigate, useNavigate } from "react-router-dom";
import { api } from "../api";
import { Button, Card, Input } from "../components/ui";
import { Wordmark } from "../components/Brand";
import ThemeToggle from "../components/ThemeToggle";
import { useToast } from "../useToast";

const MIN_LENGTH = 10;

export default function SetPassword() {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const auth = useQuery({ queryKey: ["auth"], queryFn: api.me });

  useEffect(() => {
    document.title = "Set your password · Fifth Wheel";
  }, []);

  const save = useMutation({
    mutationFn: () => api.setPassword(password),
    onSuccess: async () => {
      await queryClient.invalidateQueries();
      showToast("Password saved.");
      navigate("/dashboard", { replace: true });
    },
    onError: (issue: Error) => setError(issue.message || "Could not save the password."),
  });

  if (auth.isError || (auth.data && !auth.data.authenticated)) return <Navigate to="/login" replace />;
  if (auth.data && !auth.data.must_set_password && !save.isPending) return <Navigate to="/dashboard" replace />;

  return (
    <main className="relative flex min-h-screen items-center justify-center bg-bg px-5 py-10">
      <ThemeToggle className="absolute right-4 top-4" />
      <div className="w-full max-w-[420px]">
        <div className="mb-8">
          <Wordmark markClassName="h-10 w-10 text-accent" />
        </div>
        <Card className="p-6 sm:p-8">
          <span className="grid h-11 w-11 place-items-center rounded-2xl bg-accent/15 text-accent-ink">
            <KeyRound className="h-5 w-5" />
          </span>
          <h1 className="mt-4 text-2xl font-extrabold tracking-tight text-fg">
            Set your password{auth.data?.username ? `, ${auth.data.username}` : ""}
          </h1>
          <p className="mt-1.5 text-sm text-muted">
            Choose a password only you know. Use at least {MIN_LENGTH} characters, and don't reuse your King of Freight password.
          </p>
          <form
            className="mt-6 space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              setError("");
              if (password.length < MIN_LENGTH) {
                setError(`Use at least ${MIN_LENGTH} characters.`);
                return;
              }
              if (password !== confirm) {
                setError("The two passwords don't match.");
                return;
              }
              save.mutate();
            }}
          >
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-fg-2">New password</span>
              <Input
                autoFocus
                required
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="h-12"
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-fg-2">Confirm password</span>
              <Input
                required
                type="password"
                autoComplete="new-password"
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
                className="h-12"
              />
            </label>
            {error && (
              <p role="alert" className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-ink">
                {error}
              </p>
            )}
            <Button type="submit" variant="primary" full loading={save.isPending} className="h-12">
              Save password
            </Button>
          </form>
        </Card>
      </div>
    </main>
  );
}

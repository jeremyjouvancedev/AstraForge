import { useMemo, useState } from "react";
import { isAxiosError } from "axios";
import { toast } from "sonner";
import { useForm } from "react-hook-form";
import { Link, Navigate, useNavigate } from "react-router-dom";

import BrandSurface from "@/components/brand-surface";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth";

type LoginFormValues = {
  username: string;
  password: string;
};

export default function LoginPage() {
  const { login, isAuthenticated, authSettings } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [accessNotice, setAccessNotice] = useState<string | null>(null);
  const inputClassName =
    "rounded-xl border-white/10 bg-black/30 text-zinc-100 ring-1 ring-white/5 placeholder:text-zinc-500 focus-visible:border-indigo-400/60 focus-visible:ring-indigo-400/60 focus-visible:ring-offset-0";
  const {
    register,
    handleSubmit,
    formState: { isSubmitting }
  } = useForm<LoginFormValues>({
    defaultValues: { username: "", password: "" }
  });

  const waitlistActive = useMemo(
    () => Boolean(authSettings?.waitlist_enabled && !authSettings?.allow_all_users),
    [authSettings]
  );
  const showWaitlistAlert = waitlistActive && !authSettings?.self_hosted;

  if (isAuthenticated) {
    return <Navigate to="/app" replace />;
  }

  const onSubmit = handleSubmit(async (values) => {
    try {
      setError(null);
      setAccessNotice(null);
      await login(values);
      toast.success("Welcome back");
      navigate("/app", { replace: true });
    } catch (err) {
      if (isAxiosError(err)) {
        const accessStatus = err.response?.data?.access?.status;
        if (accessStatus === "pending") {
          setAccessNotice(
            "Your account is on the waitlist. We will notify you once an administrator approves access."
          );
          toast.info("You're already on the waitlist. Watch your inbox for approval.");
          return;
        }
        if (accessStatus === "blocked") {
          setAccessNotice("This account is blocked. Contact an administrator for support.");
          toast.error("This account is blocked. Reach out to an administrator.");
          return;
        }
        const detail = err.response?.data?.detail;
        setError(detail || "Invalid username or password");
      } else {
        setError("Invalid username or password");
      }
      toast.error("Unable to sign in");
      console.error(err);
    }
  });

  return (
    <BrandSurface contentClassName="flex items-center justify-center px-6 py-12" glow="bold">
      <div className="w-full max-w-xl space-y-6">
        <Link to="/" className="group inline-flex items-center gap-3 text-sm text-zinc-300 hover:text-white">
          <div
            className="h-10 w-10 rounded-2xl home-ring-soft home-glow"
            style={{
              background:
                "radial-gradient(circle at 30% 30%, rgba(99,102,241,1), rgba(168,85,247,1))"
            }}
          />
          <div className="leading-tight">
            <div className="text-sm font-semibold text-white">AstraForge</div>
            <div className="text-xs text-zinc-400">Sandbox factory for DeepAgents</div>
          </div>
        </Link>

        <div className="home-card home-ring-soft rounded-2xl border border-white/10 bg-black/30 p-8 shadow-2xl shadow-indigo-500/20 backdrop-blur">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.35em] text-indigo-200/80">
                Welcome back
              </p>
              <h1 className="mt-2 text-2xl font-semibold text-white">Sign in to AstraForge</h1>
              <p className="mt-2 text-sm text-zinc-300">
                Access the console to run, audit, and replay DeepAgent sandboxes.
              </p>
            </div>
            <span className="rounded-full bg-white/5 px-3 py-1 text-xs text-zinc-300 ring-1 ring-white/10">
              Secure by design
            </span>
          </div>

          {showWaitlistAlert ? (
            <Alert className="mt-4 border-indigo-400/40 bg-indigo-400/10 text-indigo-50">
              <AlertTitle className="font-semibold text-indigo-100">Access is gated</AlertTitle>
              <AlertDescription className="text-indigo-50/90">
                AstraForge sign-in currently requires approval. Join the waitlist and we&apos;ll
                notify you as soon as your account is enabled.
              </AlertDescription>
            </Alert>
          ) : null}

          <form onSubmit={onSubmit} className="mt-6 space-y-4">
            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400" htmlFor="username">
                Username
              </label>
              <Input
                id="username"
                autoComplete="username"
                className={inputClassName}
                {...register("username", { required: true })}
              />
            </div>
            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400" htmlFor="password">
                Password
              </label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                className={inputClassName}
                {...register("password", { required: true })}
              />
            </div>
            {error ? <p className="text-sm text-rose-300">{error}</p> : null}
            {accessNotice ? <p className="text-sm text-amber-200">{accessNotice}</p> : null}
            <Button type="submit" variant="brand" className="w-full" disabled={isSubmitting}>
              {isSubmitting ? "Signing in..." : "Sign in"}
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-zinc-400">
            Need an account?{" "}
            <Link to="/register" className="text-indigo-300 hover:text-white">
              Join the waitlist
            </Link>
          </p>
        </div>
      </div>
    </BrandSurface>
  );
}

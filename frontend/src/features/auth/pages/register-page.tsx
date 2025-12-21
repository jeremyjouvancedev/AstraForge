import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, Navigate, useNavigate } from "react-router-dom";

import BrandSurface from "@/components/brand-surface";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth";

type RegisterFormValues = {
  username: string;
  email?: string;
  password: string;
};

export default function RegisterPage() {
  const { register: registerUser, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const inputClassName =
    "rounded-xl border-white/10 bg-black/30 text-zinc-100 ring-1 ring-white/5 placeholder:text-zinc-500 focus-visible:border-indigo-400/60 focus-visible:ring-indigo-400/60 focus-visible:ring-offset-0";
  const {
    register,
    handleSubmit,
    formState: { isSubmitting }
  } = useForm<RegisterFormValues>({
    defaultValues: { username: "", email: "", password: "" }
  });

  if (isAuthenticated) {
    return <Navigate to="/app" replace />;
  }

  const onSubmit = handleSubmit(async (values) => {
    try {
      setError(null);
      await registerUser(values);
      navigate("/app", { replace: true });
    } catch (err) {
      setError("Unable to register with provided details");
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
                Create access
              </p>
              <h1 className="mt-2 text-2xl font-semibold text-white">Join AstraForge</h1>
              <p className="mt-2 text-sm text-zinc-300">
                Provision secure sandboxes, replay runs, and ship with confidence.
              </p>
            </div>
            <span className="rounded-full bg-white/5 px-3 py-1 text-xs text-zinc-300 ring-1 ring-white/10">
              DeepAgent ready
            </span>
          </div>

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
              <label className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400" htmlFor="email">
                Email (optional)
              </label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                placeholder="you@example.com"
                className={inputClassName}
                {...register("email")}
              />
            </div>
            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400" htmlFor="password">
                Password
              </label>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                className={inputClassName}
                {...register("password", { required: true, minLength: 8 })}
              />
            </div>
            {error ? <p className="text-sm text-rose-300">{error}</p> : null}
            <Button type="submit" variant="brand" className="w-full" disabled={isSubmitting}>
              {isSubmitting ? "Creating account..." : "Create account"}
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-zinc-400">
            Already have an account?{" "}
            <Link to="/login" className="text-indigo-300 hover:text-white">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </BrandSurface>
  );
}

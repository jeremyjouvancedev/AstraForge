import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from "@/components/ui/select";
import { createRepositoryLink } from "@/lib/api-client";

const schema = z
  .object({
    provider: z.enum(["gitlab", "github"]),
    repository: z.string().min(2, "Repository is required"),
    access_token: z.string().min(1, "Token is required"),
    base_url: z
      .string()
      .trim()
      .optional()
      .transform((value) => (value ? value : undefined))
  })
  .superRefine((data, ctx) => {
    if (data.base_url) {
      try {
        // URL constructor throws on invalid URLs; leverage it for validation.
        // eslint-disable-next-line no-new
        new URL(data.base_url);
      } catch {
        ctx.addIssue({
          path: ["base_url"],
          code: z.ZodIssueCode.custom,
          message: "Enter a valid URL"
        });
      }
    }
    if (data.provider === "github" && data.base_url) {
      ctx.addIssue({
        path: ["base_url"],
        code: z.ZodIssueCode.custom,
        message: "GitHub links do not support custom base URLs"
      });
    }
  });

export type RepositoryLinkFormValues = z.infer<typeof schema>;

export function RepositoryLinkForm() {
  const queryClient = useQueryClient();
  const inputClassName =
    "rounded-xl border-white/10 bg-black/30 text-zinc-100 ring-1 ring-white/5 placeholder:text-zinc-500 focus-visible:border-indigo-400/60 focus-visible:ring-indigo-400/60 focus-visible:ring-offset-0";
  const form = useForm<RepositoryLinkFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      provider: "gitlab",
      repository: "",
      access_token: "",
      base_url: undefined
    }
  });

  const provider = form.watch("provider");
  const handleProviderChange = (value: RepositoryLinkFormValues["provider"]) => {
    form.setValue("provider", value, { shouldValidate: true, shouldDirty: true });
  };

  const mutation = useMutation({
    mutationFn: (values: RepositoryLinkFormValues) =>
      createRepositoryLink({
        provider: values.provider,
        repository: values.repository,
        access_token: values.access_token,
        ...(values.provider === "gitlab" && values.base_url
          ? { base_url: values.base_url }
          : {})
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["repository-links"] });
      form.reset({
        provider: form.getValues("provider"),
        repository: "",
        access_token: "",
        base_url: undefined
      });
    }
  });

  const onSubmit = form.handleSubmit((values) => mutation.mutate(values));

  return (
    <Card className="home-card home-ring-soft border-white/10 bg-black/30 text-zinc-100 shadow-lg shadow-indigo-500/15 backdrop-blur">
      <CardHeader>
        <CardTitle className="text-lg font-semibold text-white">Link Repository</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-2">
            <label className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400" htmlFor="provider">
              Provider
            </label>
            <Select value={provider} onValueChange={handleProviderChange}>
              <SelectTrigger
                id="provider"
                className="h-12 w-full rounded-xl border border-white/10 bg-black/30 px-4 text-sm text-zinc-100 ring-1 ring-white/5 focus-visible:ring-2 focus-visible:ring-indigo-400/60 focus-visible:ring-offset-0"
              >
                <SelectValue placeholder="Select provider" />
              </SelectTrigger>
              <SelectContent className="rounded-xl border border-white/10 bg-black/90 text-zinc-100 shadow-2xl shadow-indigo-500/20 backdrop-blur">
                <SelectItem value="gitlab" className="rounded-lg px-2 py-2.5 text-sm text-zinc-100 data-[highlighted]:bg-indigo-500/20 data-[highlighted]:text-white">
                  GitLab
                </SelectItem>
                <SelectItem value="github" className="rounded-lg px-2 py-2.5 text-sm text-zinc-100 data-[highlighted]:bg-indigo-500/20 data-[highlighted]:text-white">
                  GitHub
                </SelectItem>
              </SelectContent>
            </Select>
            {form.formState.errors.provider && (
              <p className="text-sm text-destructive">
                {form.formState.errors.provider.message}
              </p>
            )}
          </div>
          <div className="space-y-2">
            <label className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400" htmlFor="repository">
              Repository
            </label>
            <Input
              id="repository"
              placeholder="org/project"
              className={inputClassName}
              {...form.register("repository")}
            />
            {form.formState.errors.repository && (
              <p className="text-sm text-destructive">
                {form.formState.errors.repository.message}
              </p>
            )}
          </div>
          {provider === "gitlab" && (
            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400" htmlFor="base_url">
                GitLab base URL (optional)
              </label>
              <Input
                id="base_url"
                placeholder="https://gitlab.example.com"
                className={inputClassName}
                {...form.register("base_url")}
              />
              <p className="text-xs text-zinc-400">
                Leave blank to use the default public GitLab instance.
              </p>
              {form.formState.errors.base_url && (
                <p className="text-sm text-destructive">
                  {form.formState.errors.base_url.message}
                </p>
              )}
            </div>
          )}
          <div className="space-y-2">
            <label className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400" htmlFor="access_token">
              Personal access token
            </label>
            <Input
              id="access_token"
              type="password"
              placeholder="Token"
              className={inputClassName}
              {...form.register("access_token")}
            />
            {form.formState.errors.access_token && (
              <p className="text-sm text-destructive">
                {form.formState.errors.access_token.message}
              </p>
            )}
          </div>
          <Button type="submit" variant="brand" className="rounded-xl" disabled={mutation.isPending}>
            {mutation.isPending ? "Linking..." : "Link Repository"}
          </Button>
          {mutation.isError && (
            <p className="text-sm text-destructive">
              Failed to link the repository. Please try again.
            </p>
          )}
        </form>
      </CardContent>
    </Card>
  );
}

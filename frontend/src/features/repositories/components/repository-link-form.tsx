import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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
    <Card>
      <CardHeader>
        <CardTitle>Link Repository</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="provider">
              Provider
            </label>
            <select
              id="provider"
              className="w-full rounded border px-3 py-2 text-sm"
              {...form.register("provider")}
            >
              <option value="gitlab">GitLab</option>
              <option value="github">GitHub</option>
            </select>
            {form.formState.errors.provider && (
              <p className="text-sm text-destructive">
                {form.formState.errors.provider.message}
              </p>
            )}
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="repository">
              Repository
            </label>
            <Input
              id="repository"
              placeholder="org/project"
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
              <label className="text-sm font-medium" htmlFor="base_url">
                GitLab base URL (optional)
              </label>
              <Input
                id="base_url"
                placeholder="https://gitlab.example.com"
                {...form.register("base_url")}
              />
              <p className="text-xs text-muted-foreground">
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
            <label className="text-sm font-medium" htmlFor="access_token">
              Personal access token
            </label>
            <Input
              id="access_token"
              type="password"
              placeholder="Token"
              {...form.register("access_token")}
            />
            {form.formState.errors.access_token && (
              <p className="text-sm text-destructive">
                {form.formState.errors.access_token.message}
              </p>
            )}
          </div>
          <Button type="submit" disabled={mutation.isPending}>
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

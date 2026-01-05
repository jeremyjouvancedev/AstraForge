import { useMutation, useQueryClient } from "@tanstack/react-query";
import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { z } from "zod";
import type { AxiosError } from "axios";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/components/ui/sonner";
import {
  createRequest,
  CreateRequestInput,
  CreateRequestResponse,
  RepositoryLink
} from "@/lib/api-client";
import { extractApiErrorMessage } from "@/lib/api-error";
import { ArrowUp, Cpu, Layers, Monitor } from "lucide-react";
import { useWorkspace } from "@/features/workspaces/workspace-context";

const llmProviders = ["openai", "ollama"] as const;

const schema = z.object({
  projectId: z.string().uuid({ message: "Selectionnez un projet" }),
  prompt: z.string().min(10, "Decrivez brievement votre besoin"),
  llmProvider: z.union([z.literal(""), z.enum(llmProviders)]),
  llmModel: z.string().max(120, "Le modele est trop long").optional(),
}).superRefine((data, ctx) => {
  if (data.llmModel?.trim() && !data.llmProvider) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["llmProvider"],
      message: "Selectionnez un fournisseur pour preciser un modele",
    });
  }
});

type FormValues = z.infer<typeof schema>;

interface NewRequestFormProps {
  projects: RepositoryLink[];
}

export function NewRequestForm({ projects }: NewRequestFormProps) {
  const { activeWorkspace } = useWorkspace();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const defaultProjectId = projects[0]?.id ?? "";
  const form = useForm<FormValues>({
    defaultValues: { projectId: defaultProjectId, prompt: "", llmProvider: "", llmModel: "" },
    resolver: zodResolver(schema)
  });
  const [submissionError, setSubmissionError] = useState<string | null>(null);

  useEffect(() => {
    if (projects.length > 0) {
      form.setValue("projectId", projects[0].id);
    } else {
      form.setValue("projectId", "");
    }
  }, [projects, form]);

  const mutation = useMutation<CreateRequestResponse, AxiosError, CreateRequestInput>({
    mutationFn: (input: CreateRequestInput) => createRequest(input),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ["requests"] });
      if (activeWorkspace?.uid) {
        queryClient.invalidateQueries({
          queryKey: ["workspace-usage", activeWorkspace.uid]
        });
      }
      setSubmissionError(null);
      const resetProjectId = projects[0]?.id ?? "";
      form.reset({ projectId: resetProjectId, prompt: "", llmProvider: "", llmModel: "" });
      navigate(`/app/requests/${response.id}/run`);
    },
    onError: (error) => {
      const detail =
        extractApiErrorMessage(error.response?.data) ??
        error.message ??
        "Unable to create the request.";
      setSubmissionError(detail);
      toast.error("Request blocked", {
        description: detail
      });
    }
  });

  const onSubmit = form.handleSubmit((values) => {
    const rawPrompt = values.prompt;
    const normalized = rawPrompt.trim();
    if (!normalized) {
      return;
    }
    if (submissionError) {
      setSubmissionError(null);
    }
    const llmProvider = values.llmProvider || undefined;
    const llmModel = values.llmModel?.trim() || undefined;

    mutation.mutate({
      prompt: rawPrompt,
      projectId: values.projectId,
      tenantId: activeWorkspace?.uid,
      ...(llmProvider ? { llmProvider } : {}),
      ...(llmModel ? { llmModel } : {})
    });
  });

  return (
    <div className="space-y-6">
      <div className="text-center">
        <p className="text-xs font-semibold uppercase tracking-[0.3em] text-muted-foreground">
          Launch a run
        </p>
        <h2 className="mt-2 text-2xl font-semibold">What should AstraForge build next?</h2>
        <p className="text-sm text-muted-foreground">
          Give as much context as possible.
        </p>
      </div>
      <Card className="rounded-[2.5rem] border border-border/50 bg-gradient-to-br from-background via-card to-accent/10 shadow-xl shadow-primary/10">
        <form onSubmit={onSubmit} className="flex flex-col">
          <Textarea
            rows={5}
            className="resize-none rounded-t-[2.5rem] rounded-b-none border-0 bg-transparent px-8 py-8 text-base leading-relaxed text-foreground placeholder:text-muted-foreground/80 focus-visible:ring-0"
            placeholder="Describe the feature, constraints, test coverage, and any artifacts we should reference…"
            {...form.register("prompt")}
          />
          {form.formState.errors.prompt && (
            <p className="px-8 pb-1 text-sm text-destructive">
              {form.formState.errors.prompt.message}
            </p>
          )}
          <div className="flex flex-col gap-4 rounded-b-[2.5rem] border-t border-border/60 bg-card/40 px-6 py-4 text-sm text-muted-foreground md:flex-row md:items-center md:justify-between">
            <div className="flex w-full flex-col gap-2">
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex w-full items-center gap-2 sm:w-auto">
                  <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-secondary text-secondary-foreground">
                    <Monitor size={16} />
                  </div>
                  <div className="relative">
                    <select
                      aria-label="Project"
                      className="w-full max-w-full rounded-2xl border border-border/60 bg-background/70 px-4 py-2 text-sm font-medium text-foreground shadow-inner focus:outline-none focus:ring-1 focus:ring-primary/60 sm:min-w-[220px] sm:w-auto"
                      {...form.register("projectId")}
                      disabled={mutation.isPending}
                    >
                      {projects.map((project) => (
                        <option key={project.id} value={project.id}>
                          {project.provider === "gitlab" ? "GitLab" : "GitHub"} · {project.repository}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="flex w-full items-center gap-2 sm:w-auto">
                  <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-muted/70 text-muted-foreground">
                    <Cpu size={16} />
                  </div>
                  <div className="relative">
                    <select
                      aria-label="LLM provider"
                      className="w-full max-w-full rounded-2xl border border-border/60 bg-background/70 px-4 py-2 text-sm font-medium text-foreground shadow-inner focus:outline-none focus:ring-1 focus:ring-primary/60 sm:min-w-[180px] sm:w-auto"
                      {...form.register("llmProvider")}
                      disabled={mutation.isPending}
                    >
                      <option value="">Default provider</option>
                      <option value="openai">OpenAI</option>
                      <option value="ollama">Ollama</option>
                    </select>
                  </div>
                </div>
                <div className="flex w-full items-center gap-2 sm:min-w-[240px] sm:flex-1">
                  <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-muted/70 text-muted-foreground">
                    <Layers size={16} />
                  </div>
                  <Input
                    aria-label="Model"
                    placeholder="Model (optional)"
                    className="h-10 w-full flex-1 rounded-2xl border border-border/60 bg-background/70 px-4 py-2 text-sm font-medium text-foreground shadow-inner focus-visible:ring-1 focus-visible:ring-primary/60"
                    {...form.register("llmModel")}
                    disabled={mutation.isPending}
                  />
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                Optionally choose a provider and model for this request.
              </p>
              {form.formState.errors.projectId ? (
                <p className="text-sm text-destructive">
                  {form.formState.errors.projectId.message}
                </p>
              ) : null}
              {form.formState.errors.llmProvider ? (
                <p className="text-sm text-destructive">
                  {form.formState.errors.llmProvider.message}
                </p>
              ) : null}
              {form.formState.errors.llmModel ? (
                <p className="text-sm text-destructive">
                  {form.formState.errors.llmModel.message}
                </p>
              ) : null}
            </div>
            <div className="flex flex-col items-end gap-2 text-right">
              {submissionError ? (
                <p className="text-sm text-destructive">{submissionError}</p>
              ) : null}
              <Button type="submit" disabled={mutation.isPending} className="h-11 w-11 p-0">
                <ArrowUp size={16} />
              </Button>
            </div>
          </div>
        </form>
      </Card>
    </div>
  );
}

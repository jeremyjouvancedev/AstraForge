import { useMutation, useQueryClient } from "@tanstack/react-query";
import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import {
  createRequest,
  CreateRequestInput,
  CreateRequestResponse,
  RepositoryLink
} from "@/lib/api-client";
import { ArrowUp, GitBranch, Layers, Mic, Monitor, Plus } from "lucide-react";

const schema = z.object({
  projectId: z.string().uuid({ message: "Selectionnez un projet" }),
  prompt: z.string().min(10, "Decrivez brievement votre besoin"),
});

type FormValues = z.infer<typeof schema>;

interface NewRequestFormProps {
  projects: RepositoryLink[];
}

export function NewRequestForm({ projects }: NewRequestFormProps) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const defaultProjectId = projects[0]?.id ?? "";
  const form = useForm<FormValues>({
    defaultValues: { projectId: defaultProjectId, prompt: "" },
    resolver: zodResolver(schema)
  });

  useEffect(() => {
    if (projects.length > 0) {
      form.setValue("projectId", projects[0].id);
    }
  }, [projects, form]);

  const mutation = useMutation<CreateRequestResponse, Error, CreateRequestInput>({
    mutationFn: (input: CreateRequestInput) => createRequest(input),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ["requests"] });
      const resetProjectId = projects[0]?.id ?? "";
      form.reset({ projectId: resetProjectId, prompt: "" });
      navigate(`/requests/${response.id}/run`);
    }
  });

  const onSubmit = form.handleSubmit((values) => {
    const rawPrompt = values.prompt;
    const normalized = rawPrompt.trim();
    if (!normalized) {
      return;
    }

    mutation.mutate({
      prompt: rawPrompt,
      projectId: values.projectId,
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
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                <Plus size={16} />
              </div>
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-secondary text-secondary-foreground">
                <Monitor size={16} />
              </div>
              <div className="relative">
                <select
                  aria-label="Project"
                  className="rounded-2xl border border-border/60 bg-background/70 px-4 py-2 text-sm font-medium text-foreground shadow-inner focus:outline-none focus:ring-1 focus:ring-primary/60"
                  {...form.register("projectId")}
                  disabled={mutation.isLoading}
                >
                  {projects.map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.provider === "gitlab" ? "GitLab" : "GitHub"} · {project.repository}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-muted/70 text-muted-foreground">
                <GitBranch size={16} />
              </div>
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-muted/70 text-muted-foreground">
                <Layers size={16} />
              </div>
            </div>
            <div className="flex items-center gap-2">
              {form.formState.errors.projectId && (
                <p className="text-sm text-destructive">
                  {form.formState.errors.projectId.message}
                </p>
              )}
              <div className="flex h-10 w-10 items-center justify-center rounded-full border border-border/60 text-muted-foreground">
                <Mic size={16} />
              </div>
              <Button type="submit" disabled={mutation.isLoading} className="h-11 w-11 p-0">
                <ArrowUp size={16} />
              </Button>
            </div>
          </div>
        </form>
      </Card>
    </div>
  );
}

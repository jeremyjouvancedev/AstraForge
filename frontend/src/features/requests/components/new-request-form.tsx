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

    const title = createTitleFromPrompt(normalized);
    mutation.mutate({
      title,
      description: rawPrompt,
      projectId: values.projectId,
    });
  });

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-2xl font-semibold">Qu'allons-nous coder maintenant ?</h2>
        <p className="text-sm text-muted-foreground">
          Posez une question avec <span className="font-medium">/plan</span>
        </p>
      </div>
      <Card className="rounded-[2rem] border border-border/60 shadow-lg">
        <form onSubmit={onSubmit} className="flex flex-col">
          <Textarea
            rows={5}
            className="resize-none rounded-t-[2rem] rounded-b-none border-0 px-6 py-6 text-base shadow-none focus-visible:ring-0"
            placeholder="Decrivez votre besoin de developpement"
            {...form.register("prompt")}
          />
          {form.formState.errors.prompt && (
            <p className="px-6 text-sm text-destructive">{form.formState.errors.prompt.message}</p>
          )}
          <div className="flex items-center justify-between gap-4 rounded-b-[2rem] border-t px-4 py-3 text-sm text-muted-foreground">
            <div className="flex items-center gap-3">
              <Plus size={16} />
              <Monitor size={16} />
              <div className="relative">
                <select
                  aria-label="Project"
                  className="rounded-md border bg-transparent px-3 py-1 text-sm font-medium text-foreground"
                  {...form.register("projectId")}
                  disabled={mutation.isLoading}
                >
                  {projects.map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.provider === "gitlab" ? "GitLab" : "GitHub"} - {project.repository}
                    </option>
                  ))}
                </select>
              </div>
              <GitBranch size={16} />
              <Layers size={16} />
            </div>
            <div className="flex items-center gap-2">
              {form.formState.errors.projectId && (
                <p className="text-sm text-destructive">
                  {form.formState.errors.projectId.message}
                </p>
              )}
              <div className="flex h-9 w-9 items-center justify-center rounded-full border text-foreground">
                <Mic size={16} />
              </div>
              <Button
                type="submit"
                disabled={mutation.isLoading}
                className="h-9 w-9 rounded-full p-0"
              >
                <ArrowUp size={16} />
              </Button>
            </div>
          </div>
        </form>
      </Card>
    </div>
  );
}

function createTitleFromPrompt(prompt: string): string {
  const firstLine = prompt.split("\n")[0]?.trim() ?? "";
  if (firstLine.length >= 12) {
    return truncate(firstLine, 72);
  }
  return truncate(prompt, 72);
}

function truncate(value: string, limit: number): string {
  return value.length > limit ? `${value.slice(0, limit - 3)}...` : value;
}

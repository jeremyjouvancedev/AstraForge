import { ChangeEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import { useNavigate, useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useRequestDetail } from "@/features/requests/hooks/use-request-detail";
import { DevelopmentSpecDto, executeRequest } from "@/lib/api-client";

interface SpecDraft {
  title: string;
  summary: string;
  requirements: string;
  implementationSteps: string;
  risks: string;
  acceptanceCriteria: string;
}

const terminalStates = new Set(["PATCH_READY", "FAILED", "MR_OPENED", "REVIEWED", "DONE"]);

export default function RequestDetailPage() {
  const params = useParams<{ id: string }>();
  const requestId = params.id ?? "";
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data, isLoading } = useRequestDetail(requestId);
  const [specDraft, setSpecDraft] = useState<SpecDraft | null>(null);
  const [isDirty, setIsDirty] = useState(false);

  const executeMutation = useMutation({
    mutationFn: async (draft: SpecDraft) =>
      executeRequest({ requestId, spec: draftToSpec(draft) }),
    onSuccess: () => {
      setIsDirty(false);
      queryClient.invalidateQueries({ queryKey: ["request-detail", requestId] });
      queryClient.invalidateQueries({ queryKey: ["requests"] });
      navigate(`/requests/${requestId}/run`, { replace: true });
    },
  });

  const specFromServer = useMemo(() => {
    const raw = (data?.metadata as { spec?: DevelopmentSpecDto } | undefined)?.spec;
    return raw ?? null;
  }, [data]);

  useEffect(() => {
    if (!specFromServer || isDirty) {
      return;
    }
    setSpecDraft((previous) => {
      const next = specToDraft(specFromServer);
      if (previous && draftsEqual(previous, next)) {
        return previous;
      }
      return next;
    });
  }, [specFromServer, isDirty]);

  const handleFieldChange = (field: keyof SpecDraft) =>
    (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      if (!specDraft) return;
      setSpecDraft({ ...specDraft, [field]: event.target.value });
      setIsDirty(true);
    };

  const handleReset = () => {
    if (specFromServer) {
      setSpecDraft(specToDraft(specFromServer));
    }
    setIsDirty(false);
  };

  const handleExecute = () => {
    if (!specDraft) return;
    executeMutation.mutate(specDraft);
  };

  if (!requestId) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <Card>
          <CardHeader>
            <CardTitle>Request not found</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Provide a valid request identifier to continue.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const currentState = data?.state ?? "RECEIVED";
  const waitingForSpec = !specFromServer && !terminalStates.has(currentState);
  const executionInFlight = currentState === "EXECUTING" || executeMutation.isLoading;
  const executeError = getErrorMessage(executeMutation.error);

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6 p-6">
      <header className="space-y-2">
        <p className="text-sm uppercase text-muted-foreground">Request</p>
        <h1 className="text-2xl font-semibold">{data?.payload.title ?? "Preparing request"}</h1>
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <span className="rounded-full bg-secondary px-3 py-1 text-xs font-semibold uppercase tracking-wide">
            {currentState}
          </span>
          {data?.project?.repository && <span>{data.project.repository}</span>}
        </div>
      </header>

      {isLoading ? (
        <Card>
          <CardHeader>
            <CardTitle>Loading request details...</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Fetching latest information from the orchestrator.
            </p>
          </CardContent>
        </Card>
      ) : waitingForSpec ? (
        <Card>
          <CardHeader>
            <CardTitle>Generating specification</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p>
              Your request has been queued. We&apos;re assembling a structured development
              specification—this usually takes a few seconds.
            </p>
            <p>Leave this tab open; the details will appear automatically when ready.</p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Review specification</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <section className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Title</label>
                <Input
                  value={specDraft?.title ?? ""}
                  disabled={executionInFlight}
                  onChange={handleFieldChange("title")}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Summary</label>
                <Textarea
                  rows={4}
                  value={specDraft?.summary ?? ""}
                  disabled={executionInFlight}
                  onChange={handleFieldChange("summary")}
                />
              </div>
              <SpecListField
                label="Requirements"
                value={specDraft?.requirements ?? ""}
                onChange={handleFieldChange("requirements")}
                disabled={executionInFlight}
              />
              <SpecListField
                label="Implementation Steps"
                value={specDraft?.implementationSteps ?? ""}
                onChange={handleFieldChange("implementationSteps")}
                disabled={executionInFlight}
              />
              <SpecListField
                label="Risks"
                value={specDraft?.risks ?? ""}
                onChange={handleFieldChange("risks")}
                disabled={executionInFlight}
              />
              <SpecListField
                label="Acceptance Criteria"
                value={specDraft?.acceptanceCriteria ?? ""}
                onChange={handleFieldChange("acceptanceCriteria")}
                disabled={executionInFlight}
              />
            </section>
            <div className="flex flex-wrap items-center gap-3">
              <Button
                onClick={handleExecute}
                disabled={executionInFlight || !specDraft}
              >
                Start implementation
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={handleReset}
                disabled={!isDirty || !specDraft || executionInFlight}
              >
                Reset changes
              </Button>
              {executionInFlight && (
                <span className="text-sm text-muted-foreground">
                  Provisioning workspace and orchestrating Codex…
                </span>
              )}
              {executeError && (
                <span className="text-sm text-destructive">{executeError}</span>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {data?.metadata && data.metadata.execution && (
        <Card>
          <CardHeader>
            <CardTitle>Execution summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p>Diff artifact length: {(data.metadata.execution as { diff?: string }).diff?.length ?? 0} bytes.</p>
            <p>
              Proceed to validate or iterate on these changes from the conversation view if
              needed.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function draftsEqual(a: SpecDraft, b: SpecDraft): boolean {
  return (
    a.title === b.title &&
    a.summary === b.summary &&
    a.requirements === b.requirements &&
    a.implementationSteps === b.implementationSteps &&
    a.risks === b.risks &&
    a.acceptanceCriteria === b.acceptanceCriteria
  );
}

function specToDraft(spec: DevelopmentSpecDto): SpecDraft {
  return {
    title: spec.title ?? "",
    summary: spec.summary ?? "",
    requirements: (spec.requirements ?? []).join("\n"),
    implementationSteps: (spec.implementation_steps ?? []).join("\n"),
    risks: (spec.risks ?? []).join("\n"),
    acceptanceCriteria: (spec.acceptance_criteria ?? []).join("\n"),
  };
}

function draftToSpec(draft: SpecDraft): DevelopmentSpecDto {
  return {
    title: draft.title.trim(),
    summary: draft.summary.trim(),
    requirements: splitLines(draft.requirements),
    implementation_steps: splitLines(draft.implementationSteps),
    risks: splitLines(draft.risks),
    acceptance_criteria: splitLines(draft.acceptanceCriteria),
  };
}

function splitLines(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

function getErrorMessage(error: unknown): string | null {
  if (!error) return null;
  if (isAxiosError(error)) {
    const data = error.response?.data as { detail?: string } | undefined;
    return data?.detail ?? error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

interface SpecListFieldProps {
  label: string;
  value: string;
  onChange: (event: ChangeEvent<HTMLTextAreaElement>) => void;
  disabled?: boolean;
}

function SpecListField({ label, value, onChange, disabled }: SpecListFieldProps) {
  return (
    <div className="space-y-2">
      <label className="text-sm font-medium">{label}</label>
      <Textarea rows={4} value={value} onChange={onChange} disabled={disabled} />
      <p className="text-xs text-muted-foreground">One item per line.</p>
    </div>
  );
}

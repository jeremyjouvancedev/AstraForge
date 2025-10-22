import { useMutation, useQueryClient } from "@tanstack/react-query";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { createRequest } from "@/lib/api-client";

const schema = z.object({
  title: z.string().min(4),
  description: z.string().min(10),
  context: z.string().optional()
});

type FormValues = z.infer<typeof schema>;

export function NewRequestForm() {
  const queryClient = useQueryClient();
  const form = useForm<FormValues>({
    defaultValues: { title: "", description: "", context: "" },
    resolver: zodResolver(schema)
  });

  const mutation = useMutation({
    mutationFn: (values: FormValues) =>
      createRequest({
        title: values.title,
        description: values.description,
        context: values.context ? { notes: values.context } : {}
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["requests"] });
      form.reset();
    }
  });

  const onSubmit = form.handleSubmit((values) => mutation.mutate(values));

  return (
    <Card>
      <CardHeader>
        <CardTitle>New Request</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="title">
              Title
            </label>
            <Input id="title" {...form.register("title")} placeholder="Add retry logic to data loader" />
            {form.formState.errors.title && (
              <p className="text-sm text-destructive">{form.formState.errors.title.message}</p>
            )}
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="description">
              Description
            </label>
            <Textarea
              id="description"
              rows={4}
              {...form.register("description")}
              placeholder="Handle intermittent network errors and add exponential backoff."
            />
            {form.formState.errors.description && (
              <p className="text-sm text-destructive">{form.formState.errors.description.message}</p>
            )}
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="context">
              Context (optional)
            </label>
            <Input id="context" {...form.register("context")} placeholder="ingestion/data_loader.py" />
          </div>
          <Button type="submit" disabled={mutation.isLoading}>
            {mutation.isLoading ? "Submitting..." : "Submit Request"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

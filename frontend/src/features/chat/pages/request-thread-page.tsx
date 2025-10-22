import { useParams } from "react-router-dom";

import { ChatApprovalBar } from "@/features/chat/components/chat-approval-bar";
import { ChatComposer } from "@/features/chat/components/chat-composer";
import { ChatTimeline } from "@/features/chat/components/chat-timeline";
import { useChatThread } from "@/features/chat/hooks/use-chat-thread";
import { rendererRegistry } from "@/lib/renderers/registry";

export default function RequestThreadPage() {
  const params = useParams<{ id: string }>();
  const requestId = params.id ?? "";
  const { data, isLoading } = useChatThread(requestId);
  const DiffRenderer = rendererRegistry.resolve("diff");
  const SpecRenderer = rendererRegistry.resolve("spec");
  const TestRenderer = rendererRegistry.resolve("test-report");

  const handleSend = (message: string) => {
    console.log("send message", message); // placeholder wiring
  };

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4 p-6">
      <header className="space-y-1">
        <h2 className="text-lg font-semibold">Conversation</h2>
        <p className="text-sm text-muted-foreground">Discuss requirements and approvals for request {requestId}.</p>
      </header>
      <ChatApprovalBar
        onApprove={() => console.log("approved")}
        onRequestChanges={() => console.log("request changes")}
      />
      <section className="min-h-[300px] space-y-4">
        {isLoading ? <p>Loading conversation…</p> : <ChatTimeline messages={data?.messages} />}
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2 space-y-2">
            <h3 className="text-sm font-semibold">Spec Preview</h3>
            {SpecRenderer && <SpecRenderer spec="<p>Auto-generated functional spec placeholder.</p>" />}
          </div>
          <div className="space-y-2">
            <h3 className="text-sm font-semibold">Diff Preview</h3>
            {DiffRenderer && <DiffRenderer diff="--- a/file
+++ b/file
" />}
            <h3 className="text-sm font-semibold">Test Report</h3>
            {TestRenderer && <TestRenderer results={[{ name: "pytest", status: "pass" }]} />}
          </div>
        </div>
      </section>
      <ChatComposer onSend={handleSend} />
    </div>
  );
}

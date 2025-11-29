import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChatTimeline } from "@/features/chat/components/chat-timeline";

describe("ChatTimeline link handling", () => {
  it("calls onLinkClick for download links", () => {
    const handleClick = vi.fn();
    render(
      <ChatTimeline
        messages={[
          {
            id: "1",
            role: "assistant",
            content: "[file.md](/download?path=/workspace/file.md&download=1)",
            created_at: new Date().toISOString(),
          },
        ]}
        onLinkClick={handleClick}
      />
    );

    const link = screen.getByRole("link", { name: "file.md" });
    fireEvent.click(link);

    expect(handleClick).toHaveBeenCalledTimes(1);
    expect(handleClick.mock.calls[0][0]).toContain("/download?path=/workspace/file.md");
    expect(handleClick.mock.calls[0][1]).toBe("file.md");
  });
});

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { Markdown } from "./Markdown";
import type { CopilotEvidence } from "../types";

const evidence: CopilotEvidence = {
  id: "E1",
  kind: "file",
  title: "app/main.py",
  content: "print('hello')",
  file_path: "app/main.py",
  line_start: 3,
  line_end: 4,
  reason: "retrieved",
  score: 1,
};

describe("Markdown", () => {
  it("renders headings, lists, inline code and code fences", () => {
    const { container } = render(
      <Markdown
        content={"## Answer\n\n- use `helper`\n\n```python\nprint('x')\n```"}
      />,
    );

    expect(screen.getByRole("heading", { name: "Answer" })).toBeInTheDocument();
    expect(screen.getByText("helper").tagName).toBe("CODE");
    expect(screen.getByText("print('x')").tagName).toBe("CODE");
    expect(container.querySelector("ul li")).not.toBeNull();
  });

  it("makes known citations clickable and leaves unknown ids inert", () => {
    const onCitation = vi.fn();
    render(
      <Markdown content={"Fact [E1]. Unknown [E9]."} evidence={[evidence]} onCitation={onCitation} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Show evidence E1" }));
    expect(onCitation).toHaveBeenCalledWith(evidence);
    expect(screen.queryByRole("button", { name: "Show evidence E9" })).not.toBeInTheDocument();
  });

  it("does not inject raw HTML or unsafe links", () => {
    const { container } = render(
      <Markdown
        content={"<script>alert('x')</script>\n\n[bad](javascript:alert(1))\n\n[good](https://example.com)"}
      />,
    );

    expect(container.querySelector("script")).toBeNull();
    expect(container.textContent).toContain("<script>alert('x')</script>");
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
    expect(screen.getByRole("link", { name: "good" })).toHaveAttribute(
      "href",
      "https://example.com",
    );
  });
});

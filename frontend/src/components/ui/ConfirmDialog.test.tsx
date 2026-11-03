import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ConfirmDialog } from "./ConfirmDialog";

function Harness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Delete repository
      </button>
      <ConfirmDialog
        open={open}
        title="Delete repository"
        description="This removes the local index."
        confirmLabel="Delete"
        onConfirm={() => setOpen(false)}
        onCancel={() => setOpen(false)}
      />
    </>
  );
}

describe("ConfirmDialog", () => {
  it("traps focus, closes on Escape, and restores focus", async () => {
    render(<Harness />);

    const trigger = screen.getByRole("button", { name: "Delete repository" });
    trigger.focus();
    fireEvent.click(trigger);
    await screen.findByRole("dialog");
    const cancel = screen.getByRole("button", { name: "Cancel" });
    const confirm = screen.getByRole("button", { name: "Delete" });

    await waitFor(() => expect(cancel).toHaveFocus());

    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(confirm).toHaveFocus();

    fireEvent.keyDown(document, { key: "Tab" });
    expect(cancel).toHaveFocus();

    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", { name: "Delete repository" }),
    ).toHaveFocus();
  });

  it("dismisses when the backdrop is clicked", async () => {
    render(<Harness />);

    fireEvent.click(screen.getByRole("button", { name: "Delete repository" }));
    const dialog = await screen.findByRole("dialog");
    const backdrop = dialog.parentElement;
    expect(backdrop).not.toBeNull();

    fireEvent.click(backdrop as HTMLElement);
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
  });
});

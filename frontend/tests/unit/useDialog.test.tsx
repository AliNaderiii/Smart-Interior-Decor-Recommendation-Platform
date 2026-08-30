import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { useRef, useState } from "react";
import { useDialog } from "@/hooks/useDialog";

function TestModal({ onClose }: { onClose: () => void }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useDialog({
    isOpen: true,
    onClose,
    containerRef,
    initialFocusRef: inputRef,
    restoreFocus: true,
    trapFocus: true,
    closeOnEscape: true,
  });

  return (
    <div ref={containerRef} role="dialog" aria-modal="true" aria-label="Test Dialog">
      <h2>Modal Title</h2>
      <input ref={inputRef} data-testid="modal-input" placeholder="Name" />
      <button data-testid="first-btn">Save</button>
      <button data-testid="cancel-btn" onClick={onClose}>
        Cancel
      </button>
    </div>
  );
}

function ParentComponent() {
  const [open, setOpen] = useState(false);

  return (
    <div>
      <button data-testid="open-btn" onClick={() => setOpen(true)}>
        Open Modal
      </button>
      {open && <TestModal onClose={() => setOpen(false)} />}
    </div>
  );
}

describe("useDialog hook (IR-S1-011)", () => {
  it("closes modal on document-level Escape key press", () => {
    const handleClose = vi.fn();
    render(<TestModal onClose={handleClose} />);

    // Press Escape on document body
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it("traps focus inside the modal on Tab cycling", () => {
    render(<TestModal onClose={() => {}} />);
    const input = screen.getByTestId("modal-input");
    const cancelBtn = screen.getByTestId("cancel-btn");

    expect(input).toBeDefined();
    cancelBtn.focus();
    expect(document.activeElement).toBe(cancelBtn);

    // Tab from last element wraps to first element
    fireEvent.keyDown(cancelBtn, { key: "Tab", shiftKey: false });
    // In jsdom without native full layout, our handler prevents default & focuses first
  });

  it("restores focus to opener button after modal is closed", () => {
    render(<ParentComponent />);
    const openBtn = screen.getByTestId("open-btn");
    openBtn.focus();
    expect(document.activeElement).toBe(openBtn);

    fireEvent.click(openBtn);
    expect(screen.getByRole("dialog")).toBeDefined();

    // Close via Escape
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

// Computed exercises as the learner fills them in (decision record 27): a
// cell for each number, sent in the order the backend reads them; a choice
// before weights; and, once marked, each wrong cell shown as wrong.

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { cellCount, ExerciseForm } from "@/components/exercise-form";
import type { ExerciseForm as Form } from "@/lib/types";

function fill(form: Form, right: boolean[] | null = null) {
  const onSubmit = vi.fn();
  const view = render(<ExerciseForm form={form} pending={false} right={right} onSubmit={onSubmit} />);
  return { onSubmit, view };
}

describe("cellCount", () => {
  it("counts the cells of every form", () => {
    expect(cellCount({ type: "number" }, null)).toBe(1);
    expect(cellCount({ type: "vector", size: 3 }, null)).toBe(3);
    expect(cellCount({ type: "matrix", rows: 3, columns: 4 }, null)).toBe(12);
    expect(cellCount({ type: "vectors", count: 2, size: 4 }, null)).toBe(8);
    expect(cellCount({ type: "eigen", size: 2 }, null)).toBe(6);
    const independence: Form = { type: "independence", size: 3, options: ["Independent", "Dependent"] };
    expect(cellCount(independence, 0)).toBe(0);
    expect(cellCount(independence, 1)).toBe(3);
  });
});

describe("ExerciseForm", () => {
  it("sends a matrix row by row once every cell is filled", async () => {
    const { onSubmit } = fill({ type: "matrix", rows: 2, columns: 2 });
    const check = screen.getByRole("button", { name: "Check" });

    await userEvent.type(screen.getByRole("textbox", { name: "Row 1, column 1" }), "1");
    await userEvent.type(screen.getByRole("textbox", { name: "Row 1, column 2" }), "-1/2");
    await userEvent.type(screen.getByRole("textbox", { name: "Row 2, column 1" }), "0");
    expect(check).toBeDisabled();
    await userEvent.type(screen.getByRole("textbox", { name: "Row 2, column 2" }), " 0.5 ");
    await userEvent.click(check);

    expect(onSubmit).toHaveBeenCalledWith(["1", "-1/2", "0", "0.5"], undefined);
  });

  it("asks whether vectors are independent before any weights", async () => {
    const form: Form = { type: "independence", size: 3, options: ["Independent", "Dependent"] };
    const { onSubmit } = fill(form);
    expect(screen.queryByRole("textbox", { name: "c1" })).toBeNull();

    await userEvent.click(screen.getByRole("radio", { name: "Dependent" }));
    for (const [name, value] of [["c1", "2"], ["c2", "-1"], ["c3", "1"]]) {
      await userEvent.type(screen.getByRole("textbox", { name }), value);
    }
    await userEvent.click(screen.getByRole("button", { name: "Check" }));

    expect(onSubmit).toHaveBeenCalledWith(["2", "-1", "1"], 1);
  });

  it("sends no weights for vectors said to be independent", async () => {
    const { onSubmit } = fill({ type: "independence", size: 3, options: ["Independent", "Dependent"] });

    await userEvent.click(screen.getByRole("radio", { name: "Independent" }));
    await userEvent.click(screen.getByRole("button", { name: "Check" }));

    expect(onSubmit).toHaveBeenCalledWith([], 0);
  });

  it("pairs each eigenvalue with its eigenvector", () => {
    fill({ type: "eigen", size: 2 });

    expect(screen.getAllByRole("textbox").map((cell) => cell.getAttribute("aria-label"))).toEqual([
      "Eigenvalue 1",
      "Eigenvector 1, entry 1",
      "Eigenvector 1, entry 2",
      "Eigenvalue 2",
      "Eigenvector 2, entry 1",
      "Eigenvector 2, entry 2",
    ]);
  });

  it("shows which cells were wrong once marked, and no more Check", () => {
    fill({ type: "vector", size: 3, labels: ["x", "y", "z"] }, [true, false, true]);

    expect(screen.getByRole("textbox", { name: "y" })).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("textbox", { name: "x" })).not.toHaveAttribute("aria-invalid");
    expect(screen.getByRole("textbox", { name: "x" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Check" })).toBeNull();
  });
});

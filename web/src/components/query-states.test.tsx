// The states every section that loads data shows besides its data (decision
// record 19): loading, a failure with Try again and the API's Reference, and
// the section itself once it loads.

import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LoadError, QueryState } from "@/components/query-states";
import { ApiError } from "@/lib/api";

describe("LoadError", () => {
  it("says what failed and why, with the API's reference shortened", () => {
    const error = new ApiError(500, "Something went wrong on the server.", "9cfa424a1b2c3d4e");

    render(<LoadError what="the knowledge map" error={error} onRetry={() => {}} />);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Could not load the knowledge map: Something went wrong on the server.",
    );
    // Hovering shows the whole id.
    expect(screen.getByText("Reference 9cfa424a")).toHaveAttribute("title", "9cfa424a1b2c3d4e");
  });

  it("shows no reference when no answer arrived", () => {
    const error = new ApiError(0, "Could not reach the API. Is the backend running?");

    render(<LoadError what="the roadmap" error={error} onRetry={() => {}} />);

    expect(screen.queryByText(/Reference/)).not.toBeInTheDocument();
  });

  it("tries again on request, and not twice at once", async () => {
    const onRetry = vi.fn();
    const error = new Error("Timed out");
    const { rerender } = render(<LoadError what="the plan" error={error} onRetry={onRetry} />);

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();

    rerender(<LoadError what="the plan" error={error} onRetry={onRetry} retrying />);
    expect(screen.getByRole("button", { name: "Trying again…" })).toBeDisabled();
  });
});

describe("QueryState", () => {
  function Section({ load }: { load: () => Promise<string> }) {
    const query = useQuery({ queryKey: ["section"], queryFn: load, retry: false });
    return (
      <QueryState query={query} what="the summary">
        {(text) => <p>{text}</p>}
      </QueryState>
    );
  }

  function renderSection(load: () => Promise<string>) {
    const client = new QueryClient();
    return render(
      <QueryClientProvider client={client}>
        <Section load={load} />
      </QueryClientProvider>,
    );
  }

  it("shows the loading lines, then the section", async () => {
    renderSection(async () => "Threads share an address space.");

    expect(screen.getByRole("status")).toHaveTextContent("Loading the summary…");
    expect(await screen.findByText("Threads share an address space.")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("shows the failure, and the section once trying again works", async () => {
    const load = vi
      .fn<() => Promise<string>>()
      .mockRejectedValueOnce(new ApiError(503, "The database is not reachable.", "abc12345"))
      .mockResolvedValueOnce("Loaded on the second try.");
    renderSection(load);

    expect(await screen.findByRole("alert")).toHaveTextContent("The database is not reachable.");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("Loaded on the second try.")).toBeInTheDocument();
    expect(load).toHaveBeenCalledTimes(2);
  });
});

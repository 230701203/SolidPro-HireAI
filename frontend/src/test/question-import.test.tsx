import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import QuestionImportDialog from "@/components/QuestionImportDialog";
import { api } from "@/services/api";

const check = { dry_run: true, total_rows: 3, valid: 2, imported: 0, duplicates: 0, failed: 1, issues: [{ row: 4, message: "Topic must be one of: Numerical ability", skipped: false }] };

beforeEach(() => vi.restoreAllMocks());

function open() {
  return render(
    <QueryClientProvider client={new QueryClient()}><ToastProvider><QuestionImportDialog bankId={1} bankName="Starter" onClose={() => {}} /></ToastProvider></QueryClientProvider>,
  );
}

describe("Question import dialog", () => {
  it("checks the file first, shows row problems, and only imports after confirmation", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValueOnce({ data: check }).mockResolvedValueOnce({ data: { ...check, dry_run: false, imported: 2 } });
    open();
    expect(screen.getByRole("button", { name: "Check file" })).toBeDisabled();
    const file = new File(["x"], "questions.xlsx");
    await userEvent.upload(screen.getByLabelText("Excel file"), file);
    await userEvent.click(screen.getByRole("button", { name: "Check file" }));
    expect(await screen.findByText(/Row 4:/)).toBeInTheDocument();
    expect(post).toHaveBeenCalledTimes(1);
    expect(post.mock.calls[0][2]).toMatchObject({ params: { dry_run: true } });
    await userEvent.click(screen.getByRole("button", { name: "Import 2 questions" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(post.mock.calls[1][2]).toMatchObject({ params: { dry_run: false } });
    expect(await screen.findByText(/Imported 2 of 3 rows/)).toBeInTheDocument();
  });

  it("rejects files that are not .xlsx before uploading", async () => {
    const post = vi.spyOn(api, "post");
    open();
    await userEvent.upload(screen.getByLabelText("Excel file"), new File(["x"], "questions.csv"), { applyAccept: false });
    expect(await screen.findByText(/Upload an Excel .xlsx file/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });
});

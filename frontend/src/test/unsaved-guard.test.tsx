import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Link, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { useUnsavedChangesGuard } from "@/components/useUnsavedChangesGuard";

function Form({ save }: { save: () => Promise<boolean> }) {
  const [dirty, setDirty] = useState(false);
  const guard = useUnsavedChangesGuard(dirty, save);
  return <div>{guard}<button onClick={() => setDirty(true)}>edit</button><Link to="/other">Other module</Link><span>form page</span></div>;
}
const app = (save = vi.fn().mockResolvedValue(true)) => render(
  <MemoryRouter initialEntries={["/form"]}><Routes><Route path="/form" element={<Form save={save} />} /><Route path="/other" element={<span>other page</span>} /></Routes></MemoryRouter>);

describe("unsaved changes guard", () => {
  it("lets you leave freely when nothing changed", async () => {
    app();
    await userEvent.click(screen.getByText("Other module"));
    expect(screen.getByText("other page")).toBeInTheDocument();
  });
  it("asks first when there are unsaved changes, and Keep editing stays", async () => {
    app();
    await userEvent.click(screen.getByText("edit"));
    await userEvent.click(screen.getByText("Other module"));
    expect(await screen.findByText("You have unsaved changes")).toBeInTheDocument();
    expect(screen.getByText("form page")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Keep editing" }));
    expect(screen.queryByText("You have unsaved changes")).toBeNull();
    expect(screen.getByText("form page")).toBeInTheDocument();
  });
  it("Discard and leave navigates; Save and leave saves first and only leaves on success", async () => {
    app();
    await userEvent.click(screen.getByText("edit"));
    await userEvent.click(screen.getByText("Other module"));
    await userEvent.click(await screen.findByRole("button", { name: "Discard and leave" }));
    expect(await screen.findByText("other page")).toBeInTheDocument();
  });
  it("saves then leaves, but stays when the save fails", async () => {
    const ok = vi.fn().mockResolvedValue(true);
    const { unmount } = app(ok);
    await userEvent.click(screen.getByText("edit")); await userEvent.click(screen.getByText("Other module"));
    await userEvent.click(await screen.findByRole("button", { name: "Save and leave" }));
    expect(ok).toHaveBeenCalled(); expect(await screen.findByText("other page")).toBeInTheDocument();
    unmount();
    app(vi.fn().mockResolvedValue(false));
    await userEvent.click(screen.getByText("edit")); await userEvent.click(screen.getByText("Other module"));
    await userEvent.click(await screen.findByRole("button", { name: "Save and leave" }));
    expect(await screen.findByText("form page")).toBeInTheDocument();
    expect(screen.queryByText("other page")).toBeNull();
  });
});

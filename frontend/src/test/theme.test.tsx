import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import ThemeToggle from "@/components/ThemeToggle";

beforeEach(() => { localStorage.clear(); document.documentElement.classList.remove("dark"); });

describe("Dark mode switch", () => {
  it("toggles the dark class and remembers the choice", async () => {
    const { unmount } = render(<ThemeToggle />);
    const sw = screen.getByRole("switch", { name: "Dark mode" });
    expect(sw).toHaveAttribute("aria-checked", "false");
    await userEvent.click(sw);
    expect(document.documentElement).toHaveClass("dark");
    expect(localStorage.getItem("solid-hire-theme")).toBe("dark");
    unmount();
    render(<ThemeToggle />);  // a later visit restores it
    expect(screen.getByRole("switch", { name: "Dark mode" })).toHaveAttribute("aria-checked", "true");
    await userEvent.click(screen.getByRole("switch", { name: "Dark mode" }));
    expect(document.documentElement).not.toHaveClass("dark");
    expect(localStorage.getItem("solid-hire-theme")).toBe("light");
  });
});

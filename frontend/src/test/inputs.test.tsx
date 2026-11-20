import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import SelectOther from "@/components/SelectOther";
import { joinMobile, mobileProblem, splitMobile } from "@/utils/mobile";

describe("mobile rules", () => {
  it.each(["+91 9876543210", "9876543210", "+91-98765-43210", "+1 415 555 0132", "+971 50 123 4567"])("accepts %s", (v) => expect(mobileProblem(v)).toBeNull());
  it.each(["987654321", "+91 987654321", "+91 98765432101", "+91 1234567890", "+91 9999999999", "+1 12345", "+0 12345678", "98765abcde"])("refuses %s", (v) => expect(mobileProblem(v)).not.toBeNull());
  it("splits and joins stored numbers", () => {
    expect(splitMobile("+91 9876543210")).toEqual({ code: "+91", other: false, number: "9876543210" });
    expect(splitMobile("+44 7911 123456")).toEqual({ code: "+44", other: false, number: "7911123456" });
    expect(splitMobile("+358 401234567")).toEqual({ code: "+358", other: true, number: "401234567" });
    expect(splitMobile("9876543210").code).toBe("+91");
    expect(joinMobile("+91", "")).toBe("");
  });
});

function Harness({ initial }: { initial: string }) {
  const [v, setV] = useState(initial);
  return <><SelectOther id="q" value={v} onChange={setV} options={["B.E.", "B.Tech"]} /><output data-testid="out">{v}</output></>;
}

describe("SelectOther", () => {
  it("picks a preset, and Other reveals a text box whose text becomes the value", async () => {
    render(<Harness initial="" />);
    expect(screen.queryByRole("textbox")).toBeNull();
    await userEvent.selectOptions(screen.getByRole("combobox"), "B.Tech");
    expect(screen.getByTestId("out")).toHaveTextContent("B.Tech");
    await userEvent.selectOptions(screen.getByRole("combobox"), "__other__");
    expect(screen.getByTestId("out")).toHaveTextContent("");
    await userEvent.type(screen.getByRole("textbox"), "B.Arch");
    expect(screen.getByTestId("out")).toHaveTextContent("B.Arch");
  });
  it("opens saved custom values as Other with the text filled in", () => {
    render(<Harness initial="B.Arch" />);
    expect(screen.getByRole("textbox")).toHaveValue("B.Arch");
    expect(screen.getByRole<HTMLSelectElement>("combobox").value).toBe("__other__");
  });
});

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DaysValue } from "@/components/DaysValue";
import { StatusBadge } from "@/components/StatusBadge";

describe("DaysValue", () => {
  it("formatta soltanto la stringa ricevuta dall'API", () => {
    render(<DaysValue value="1234.5678" label="Residuo API" />);

    expect(screen.getByText("1.234,57 gg")).toHaveAttribute("title", "Residuo API: 1234.5678 gg");
  });
});

describe("StatusBadge", () => {
  it("distingue semanticamente il dominio dello stato", () => {
    render(<StatusBadge status="DA_VERIFICARE" domain="billing" />);

    expect(screen.getByText("Da verificare")).toHaveAttribute(
      "title",
      "Fatturazione: Da verificare",
    );
    expect(screen.getByText("Fatturazione:")).toHaveClass("sr-only");
  });
});

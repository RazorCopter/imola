import { describe, expect, it } from "vitest";

import {
  deltaTone,
  formatCount,
  formatDays,
  formatDelta,
  formatPercent,
  parseDays,
} from "@/lib/format";

describe("le giornate arrivano come stringhe dall'API", () => {
  it("formatta i valori a 4 decimali che il backend serializza come stringa", () => {
    // Granularità PPM: 1/16 di giornata, arrotondata a due decimali solo per la vista.
    expect(formatDays("8.6875")).toBe("8,69 gg");
    // Consuntivato del canone S2 nel seed reale.
    expect(formatDays("100.2700")).toBe("100,27 gg");
  });

  it("non altera il valore di origine, che resta una stringa", () => {
    const fromApi = "8.6875";
    expect(formatDays(fromApi)).toBe("8,69 gg");
    expect(fromApi).toBe("8.6875");
  });

  it("documenta perché nel client non si sommano giornate", () => {
    // Questa è la ragione della regola: in JavaScript la somma di due giornate
    // introdurrebbe un errore di rappresentazione. I totali arrivano dal backend.
    expect(Number("0.1") + Number("0.2")).not.toBe(0.3);
    expect(formatDays("0.3")).toBe("0,30 gg");
  });
});

describe("formatDays", () => {
  it("usa i separatori italiani e due decimali", () => {
    expect(formatDays("1234.56")).toBe("1.234,56 gg");
    expect(formatDays("130.8900")).toBe("130,89 gg");
    expect(formatDays("10.1000")).toBe("10,10 gg");
  });

  it("arrotonda a due decimali in visualizzazione", () => {
    expect(formatDays("102.3450")).toBe("102,35 gg");
    expect(formatDays("0.0625")).toBe("0,06 gg");
  });

  it("gestisce i valori assenti", () => {
    expect(formatDays(null)).toBe("–");
    expect(formatDays(undefined)).toBe("–");
    expect(formatDays("")).toBe("–");
  });

  it("puo omettere l'unità per le celle di tabella", () => {
    expect(formatDays("8.6875", { suffix: false })).toBe("8,69");
  });
});

describe("formatDelta", () => {
  it("mostra sempre il segno", () => {
    expect(formatDelta("2.08")).toBe("+2,08 gg");
    expect(formatDelta("-1.5")).toBe("-1,50 gg");
    expect(formatDelta("0")).toBe("0,00 gg");
  });

  it("il delta positivo del canone è a favore di BMED", () => {
    expect(deltaTone("2.08")).toBe("ok");
    expect(deltaTone("-1.5")).toBe("warn");
    expect(deltaTone(null)).toBe("neutral");
  });
});

describe("parseDays", () => {
  it("accetta stringhe e numeri", () => {
    expect(parseDays("8.6875")).toBe(8.6875);
    expect(parseDays(3)).toBe(3);
    expect(parseDays("non un numero")).toBeNull();
  });
});

describe("formattazioni accessorie", () => {
  it("formatta conteggi e percentuali", () => {
    expect(formatCount(1234)).toBe("1.234");
    expect(formatCount(null)).toBe("–");
    expect(formatPercent("72.4")).toBe("72,4%");
  });
});

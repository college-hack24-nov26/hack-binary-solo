import { fireEvent, render, screen } from "@testing-library/react";
import { ChainSeal, HashLink } from "./AuditChain";
import { Tile } from "./Tile";
import { TokenSlip } from "./TokenSlip";
import { IconButton, ToggleButton } from "./Button";
import { Keypad, MultiTiles } from "../kiosk/inputs";
import type { TokenSlip as Slip } from "../api/client";
import { Bell } from "lucide-react";

describe("audit chain", () => {
  it("says Chain verified with an icon and the count", () => {
    render(<ChainSeal ok entries={12} />);
    expect(screen.getByRole("status")).toHaveTextContent("Chain verified");
    expect(screen.getByRole("status")).toHaveTextContent("12 entries");
  });
  it("says Chain broken and names the first bad line, with no fix control", () => {
    render(<ChainSeal ok={false} entries={12} firstBad={4} />);
    expect(screen.getByRole("status")).toHaveTextContent("Chain broken");
    expect(screen.getByRole("status")).toHaveTextContent("line 5");
    expect(screen.queryByRole("button")).toBeNull();
  });
  it("links each hash to the previous one", () => {
    render(<HashLink hash="abcdef123" prev="0123456" />);
    expect(screen.getByLabelText("linked to")).toBeInTheDocument();
    expect(screen.getByText("abcdef")).toBeInTheDocument();
  });
});

describe("kiosk inputs", () => {
  it("a selected tile says so in words, not only colour", () => {
    render(<Tile selected selectedLabel="चुना गया">आज</Tile>);
    expect(screen.getByRole("button", { pressed: true })).toHaveTextContent("चुना गया");
  });
  it("none is exclusive in multi-choice", () => {
    const sent: string[][] = [];
    render(<MultiTiles options={[{ id: "a", label: "A" }, { id: "b", label: "B" }, { id: "none", label: "None" }]} value={null} lang="en" busy={false} onSubmit={(v) => sent.push(v)} />);
    fireEvent.click(screen.getByText("A"));
    fireEvent.click(screen.getByText("B"));
    fireEvent.click(screen.getByText("None"));
    fireEvent.click(screen.getByTestId("continue"));
    fireEvent.click(screen.getByText("A"));
    fireEvent.click(screen.getByTestId("continue"));
    expect(sent).toEqual([["none"], ["a"]]);
  });
  it("keypad shows the range and blocks values outside it", () => {
    const sent: number[] = [];
    render(<Keypad min={1} max={250} value={null} lang="en" busy={false} onSubmit={(n) => sent.push(n)} />);
    expect(screen.getByText("Between 1 and 250")).toBeInTheDocument();
    for (const k of ["9", "9", "9"]) fireEvent.click(screen.getByTestId(`key-${k}`));
    expect(screen.getByText("Enter a number between 1 and 250.")).toBeInTheDocument();
    expect(screen.getByTestId("continue")).toBeDisabled();
    fireEvent.click(screen.getByTestId("key-del"));
    fireEvent.click(screen.getByTestId("continue"));
    expect(sent).toEqual([99]);
  });
});

describe("buttons", () => {
  it("icon-only buttons carry their label and toggles expose aria-pressed", () => {
    render(
      <>
        <IconButton icon={Bell} label="Mute alert sound" />
        <ToggleButton pressed onPressedChange={() => undefined}>Sound on</ToggleButton>
      </>,
    );
    expect(screen.getByRole("button", { name: "Mute alert sound" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sound on" })).toHaveAttribute("aria-pressed", "true");
  });
});

describe("token slip", () => {
  const slip: Slip = {
    queueNumber: 27, queueDate: "2026-11-04", token: "PT-7KQ2MD", room: "12", floor: { en: "Ground floor", hi: "भूतल", mr: "तळमजला" },
    guidance: "follow_line", estimatedWaitMinutes: 20, patientsAhead: 2, estimateLabel: "estimate", papersAdded: 0, identifierMasked: null,
    doctor: { id: "dr_general", name: "Dr. Asha Kulkarni", specialty: { en: "General Physician", hi: "सामान्य चिकित्सक", mr: "सामान्य वैद्य" }, room: "12",
      floor: { en: "Ground floor", hi: "भूतल", mr: "तळमजला" }, lineColor: "#1E7B45", lineName: { en: "green", hi: "हरी", mr: "हिरव्या" }, lineTextColor: "#FFFFFF" },
  };
  it("shows queue number, token, doctor, room and the floor line in the patient's language", () => {
    render(<TokenSlip slip={slip} lang="mr" />);
    const s = screen.getByTestId("token-slip");
    expect(s).toHaveTextContent("27");
    expect(s).toHaveTextContent("PT-7KQ2MD");
    expect(s).toHaveTextContent("Dr. Asha Kulkarni");
    expect(s).toHaveTextContent("हिरव्या रेषेने खोली 12 कडे जा");
    expect(s).toHaveTextContent("(अंदाज)");
    expect(screen.queryByTestId("stamp")).toBeNull();
  });
  it("without a doctor it sends the patient to reception", () => {
    render(<TokenSlip slip={{ ...slip, doctor: null, room: null, floor: null, guidance: "reception" }} lang="en" stamped />);
    expect(screen.getByTestId("token-slip")).toHaveTextContent("Reception will guide you");
    expect(screen.getByTestId("stamp")).toHaveTextContent("Registered");
  });
});

import { describe, expect, it } from "vitest";
import { checkIdentifier, digitsOf, GROUPS, LENGTH, PIN_START, pinConfirmed, pinStep, popDigit, pushDigit, pushPin, slots, stripMobilePrefix } from "./validation";

describe("identifier entry", () => {
  it("keeps digits only and strips the Indian prefixes", () => {
    expect(digitsOf("91-1234-5678-9012")).toBe("91123456789012");
    expect(stripMobilePrefix(digitsOf("+91 98765 43210"))).toBe("9876543210");
    expect(stripMobilePrefix("09876543210")).toBe("9876543210");
  });
  it("refuses a mobile number that starts below 6 and caps the length", () => {
    expect(pushDigit("mobile", "", "5")).toBe("");
    expect(pushDigit("mobile", "", "9")).toBe("9");
    let d = "";
    for (const c of "98765432109999") d = pushDigit("mobile", d, c);
    expect(d).toBe("9876543210");
    expect(pushDigit("abha", "", "1")).toBe("1");
    expect(pushDigit("abha", "", "x")).toBe("");
  });
  it("delete removes the last digit", () => {
    expect(popDigit("987")).toBe("98");
    expect(popDigit("")).toBe("");
  });
  it("gives live feedback: empty, partial with digits left, ok", () => {
    expect(checkIdentifier("mobile", "").state).toBe("empty");
    expect(checkIdentifier("mobile", "98765")).toEqual({ state: "partial", remaining: 5, reason: null });
    expect(checkIdentifier("mobile", "9876543210").state).toBe("ok");
    expect(checkIdentifier("mobile", "5876543210")).toMatchObject({ state: "bad", reason: "mobile" });
    expect(checkIdentifier("abha", "9112345678901").remaining).toBe(1);
    expect(checkIdentifier("abha", "91123456789012").state).toBe("ok");
  });
  it("lays digits into fixed groups", () => {
    expect(GROUPS.mobile.reduce((a, b) => a + b)).toBe(LENGTH.mobile);
    expect(GROUPS.abha.reduce((a, b) => a + b)).toBe(LENGTH.abha);
    expect(slots("mobile", "98765")).toEqual([["9", "8", "7", "6", "5"], ["", "", "", "", ""]]);
    expect(slots("abha", "9112")).toEqual([["9", "1"], ["1", "2", "", ""], ["", "", "", ""], ["", "", "", ""]]);
  });
});

describe("PIN", () => {
  it("accepts only four digits", () => {
    expect(pushPin("123", "4")).toBe("1234");
    expect(pushPin("1234", "5")).toBe("1234");
    expect(pushPin("12", "a")).toBe("12");
  });
  it("choose then again: a match confirms, a mismatch starts over with a message", () => {
    let s = PIN_START;
    for (const c of "4821") s = pinStep(s, { digit: c });
    expect(s).toMatchObject({ phase: "again", first: "4821", entry: "" });
    for (const c of "4821") s = pinStep(s, { digit: c });
    expect(pinConfirmed(s)).toBe(true);
    let t = PIN_START;
    for (const c of "4821") t = pinStep(t, { digit: c });
    for (const c of "4822") t = pinStep(t, { digit: c });
    expect(t).toMatchObject({ phase: "choose", first: "", entry: "", mismatch: true });
    expect(pinConfirmed(t)).toBe(false);
  });
  it("delete steps back inside the current entry only", () => {
    let s = pinStep(PIN_START, { digit: "1" });
    s = pinStep(s, { delete: true });
    expect(s.entry).toBe("");
    expect(pinStep(s, { delete: true }).phase).toBe("choose");
  });
});

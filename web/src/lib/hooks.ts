import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { get, type BodyRegions, type DoctorOut, type SystemConfig } from "../api/client";

export function useConfig() {
  return useQuery({ queryKey: ["config"], queryFn: () => get<SystemConfig>("/api/system/config"), staleTime: 60_000 });
}

export function useBodyRegions() {
  return useQuery({ queryKey: ["body-regions"], queryFn: () => get<BodyRegions>("/api/intake/body-regions"), staleTime: Infinity });
}

export function useDoctors() {
  return useQuery({ queryKey: ["doctors"], queryFn: () => get<DoctorOut[]>("/api/doctors"), staleTime: Infinity });
}

export type LiveEvent = { type: "patient.updated" | "redflag.triggered" | "help.requested" | "queue.changed"; data: Record<string, unknown> };

/**
 * Live updates for staff and doctor screens: Server-Sent Events, and while the stream is down, a 10 s poll of the same queries.
 * Every event invalidates the board, the patient it names and the help list; `onEvent` gets each one (sound, banner).
 */
export function useLiveEvents(onEvent?: (e: LiveEvent) => void): { live: boolean } {
  const qc = useQueryClient();
  const [live, setLive] = useState(false);
  const cb = useRef(onEvent);
  cb.current = onEvent;
  useEffect(() => {
    let es: EventSource | null = null;
    let poll: number | undefined;
    let retry: number | undefined;
    let closed = false;
    const refresh = (token?: unknown) => {
      qc.invalidateQueries({ queryKey: ["board"] });
      qc.invalidateQueries({ queryKey: ["help"] });
      if (typeof token === "string") qc.invalidateQueries({ queryKey: ["patient", token] });
    };
    const startPoll = () => {
      if (poll === undefined) poll = window.setInterval(() => refresh(), 10_000);
    };
    const stopPoll = () => {
      window.clearInterval(poll);
      poll = undefined;
    };
    const connect = () => {
      if (closed) return;
      es = new EventSource("/api/events");
      es.onopen = () => {
        setLive(true);
        stopPoll();
        refresh();
      };
      es.onerror = () => {
        setLive(false);
        startPoll();
        es?.close();
        retry = window.setTimeout(connect, 5_000);
      };
      for (const type of ["patient.updated", "redflag.triggered", "help.requested", "queue.changed"] as const) {
        es.addEventListener(type, (m) => {
          let data: Record<string, unknown> = {};
          try {
            data = JSON.parse((m as MessageEvent).data);
          } catch {
            /* ignore malformed */
          }
          refresh(data.token);
          cb.current?.({ type, data });
        });
      }
    };
    startPoll();
    connect();
    return () => {
      closed = true;
      es?.close();
      stopPoll();
      window.clearTimeout(retry);
    };
  }, [qc]);
  return { live };
}

export function useDebounced<T>(value: T, ms = 200): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(id);
  }, [value, ms]);
  return v;
}

export function ageSex(age: number | null | undefined, sex: string | null | undefined): string {
  const a = age === null || age === undefined ? "age ?" : age < 1 ? `${Math.round(age * 12)} mo` : `${age} y`;
  const s = sex === "female" ? "female" : sex === "male" ? "male" : sex === "other" ? "other" : "sex not given";
  return `${a}, ${s}`;
}

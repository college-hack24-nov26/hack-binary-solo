import { useEffect, useState } from "react";
import { Route, Routes, useNavigate } from "react-router";
import { FlaskConical, ListOrdered, ScrollText, UserRound } from "lucide-react";
import { RequireRole } from "../shell/auth";
import { DashboardShell, type NavItem } from "../shell/DashboardShell";
import { useConfig, useLiveEvents } from "../lib/hooks";
import { ShortcutsOverlay } from "../shell/Shortcuts";
import { Queue } from "./Queue";
import { Workspace } from "./Workspace";
import { AuditLog } from "./AuditLog";
import { DemoLoader } from "./DemoLoader";

function lastPatient(): string | null {
  try {
    return sessionStorage.getItem("mk.doctor.last");
  } catch {
    return null;
  }
}

function Doctor() {
  const cfg = useConfig();
  const nav = useNavigate();
  const [last, setLast] = useState(lastPatient());
  useLiveEvents();
  useEffect(() => {
    const on = () => setLast(lastPatient());
    window.addEventListener("mk-last-patient", on);
    return () => window.removeEventListener("mk-last-patient", on);
  }, []);
  const items: NavItem[] = [
    { to: "/doctor", label: "My queue", icon: ListOrdered, end: true },
    { to: last ? `/doctor/p/${last}` : "/doctor", label: "Patient", icon: UserRound },
    { to: "/doctor/audit", label: "Audit log", icon: ScrollText },
  ];
  if (cfg.data?.demoMode) items.push({ to: "/doctor/demo", label: "Load demo patient", icon: FlaskConical });
  return (
    <RequireRole roles={["doctor"]} loginRole="doctor">
      {(me) => (
        <DashboardShell area="doctor" title="Doctor workstation" nav={items} me={me}>
          <ShortcutsOverlay
            items={[
              ["g then q", "My queue"],
              ["g then a", "Audit log"],
              ["n", "Next patient in my queue"],
              ["/", "Search the queue"],
              ["Ctrl+Enter", "Run dosage check"],
              ["?", "Show these shortcuts"],
            ]}
            go={{ q: () => nav("/doctor"), a: () => nav("/doctor/audit") }}
          />
          <Routes>
            <Route index element={<Queue me={me} />} />
            <Route path="p/:token/:section?" element={<Workspace />} />
            <Route path="audit" element={<AuditLog />} />
            <Route path="demo" element={<DemoLoader />} />
          </Routes>
        </DashboardShell>
      )}
    </RequireRole>
  );
}

export default function DoctorApp() {
  return <Doctor />;
}

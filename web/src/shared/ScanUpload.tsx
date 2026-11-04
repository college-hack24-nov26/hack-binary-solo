import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Camera, Upload } from "lucide-react";
import { api, type PendingScan } from "../api/client";
import { Button } from "../components/Button";
import { Checkbox, Notice } from "../components/ui";
import { useConfig } from "../lib/hooks";

/**
 * Attach a photo of an old prescription or lab report to this patient's token. Runs the local vision model (30-60 s) and
 * leaves a draft that a doctor confirms. Uses the camera through a file input, which works over plain HTTP on the LAN.
 */
export function ScanUpload({ token, role }: { token: string; role: "staff" | "doctor" }) {
  const qc = useQueryClient();
  const cfg = useConfig();
  const [file, setFile] = useState<File | null>(null);
  const [consent, setConsent] = useState(false);
  const up = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.set("image", file!);
      fd.set("consent", String(consent));
      return api<PendingScan>(`/api/patients/${token}/scans`, { form: fd });
    },
    onSuccess: () => {
      setFile(null);
      setConsent(false);
      qc.invalidateQueries({ queryKey: ["patient", token] });
      qc.invalidateQueries({ queryKey: ["timeline", token] });
    },
  });
  return (
    <div className="flex flex-col gap-3">
      {cfg.data && !cfg.data.ocrAvailable && (
        <Notice tone="warn" title="Scanning is unavailable right now">
          The local model server (Ollama) is not running on this computer. Everything else keeps working; type details into the notes instead.
        </Notice>
      )}
      <label className="flex min-h-24 cursor-pointer flex-col items-center justify-center gap-1 rounded-panel border-2 border-dashed border-line-strong bg-surface px-4 py-4 text-center hover:border-teal hover:bg-tint">
        <Camera size={24} aria-hidden className="text-teal" />
        <span className="font-semibold">{file ? file.name : "Take a photo or choose an image"}</span>
        <span className="text-xs text-muted">Printed or typed text only. The image is deleted after review.</span>
        <input type="file" accept="image/*" capture="environment" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} data-testid="scan-file" />
      </label>
      <Checkbox label="The patient agreed to this document being scanned" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="primary" icon={Upload} disabled={!file || !consent} loading={up.isPending} onClick={() => up.mutate()}>
          {role === "doctor" ? "Read document" : "Read and send to doctor"}
        </Button>
        {up.isPending && <span className="text-sm text-muted">Reading with the local model, this takes about a minute…</span>}
      </div>
      {up.isSuccess && (
        <Notice tone="ok" title="Draft ready">
          {role === "doctor" ? "Check it under Timeline and confirm it." : "Sent to the doctor, who confirms each scan before it is used."}
        </Notice>
      )}
      {up.isError && <Notice tone="stop" title="The document was not read">{(up.error as Error).message}</Notice>}
    </div>
  );
}

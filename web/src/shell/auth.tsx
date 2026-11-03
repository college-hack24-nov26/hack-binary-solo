import { useActionState, useEffect, useRef, type ReactNode } from "react";
import { useFormStatus } from "react-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { LogIn } from "lucide-react";
import { ApiError, get, post, type Me } from "../api/client";
import { Button } from "../components/Button";
import { Notice, Skeleton, TextField } from "../components/ui";

export function useMe() {
  return useQuery<Me | null>({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await get<Me>("/api/auth/me");
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 60_000,
    retry: false,
  });
}

const loginSchema = z.object({
  username: z.string().trim().min(1, "Enter your username."),
  password: z.string().min(1, "Enter your password."),
});
type LoginState = { error?: string; fields?: Partial<Record<"username" | "password", string>>; username?: string };

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" variant="primary" icon={LogIn} loading={pending} block>
      Sign in
    </Button>
  );
}

export function LoginPage({ role, notice }: { role: "staff" | "doctor"; notice?: string }) {
  const qc = useQueryClient();
  const userRef = useRef<HTMLInputElement>(null);
  const passRef = useRef<HTMLInputElement>(null);
  const [state, action] = useActionState<LoginState, FormData>(async (_prev, fd) => {
    const parsed = loginSchema.safeParse({ username: fd.get("username"), password: fd.get("password") });
    const username = String(fd.get("username") ?? "");
    if (!parsed.success) {
      const f: LoginState["fields"] = {};
      for (const i of parsed.error.issues) f[i.path[0] as "username" | "password"] ??= i.message;
      return { fields: f, username };
    }
    try {
      const me = await post<Me>("/api/auth/login", parsed.data);
      qc.setQueryData(["me"], me);
      return {};
    } catch (e) {
      return { error: e instanceof ApiError ? e.message : "Sign in failed.", username };
    }
  }, {});
  useEffect(() => {
    if (state.fields?.username) userRef.current?.focus();
    else if (state.fields?.password || state.error) passRef.current?.focus();
  }, [state]);
  return (
    <main className="grid min-h-dvh place-items-center bg-paper px-4">
      <div className="w-full max-w-sm">
        <p className="mb-1 text-sm font-semibold text-teal">MediKiosk OPD</p>
        <h1 className="mb-6 text-2xl font-bold">{role === "doctor" ? "Doctor sign in" : "Staff desk sign in"}</h1>
        {notice && <Notice className="mb-4">{notice}</Notice>}
        <form action={action} noValidate className="flex flex-col gap-4 rounded-panel border border-line bg-surface p-5">
          <TextField ref={userRef} label="Username" name="username" autoComplete="username" defaultValue={state.username} error={state.fields?.username} autoFocus />
          <TextField ref={passRef} label="Password" name="password" type="password" autoComplete="current-password" error={state.fields?.password} />
          <p aria-live="assertive" className="min-h-5 text-sm font-semibold text-red">
            {state.error}
          </p>
          <SubmitButton />
        </form>
        <p className="mt-4 text-xs text-muted">Signed-in sessions end after 15 minutes without activity.</p>
      </div>
    </main>
  );
}

/** Shows the sign-in page until a login with one of `roles` exists. */
export function RequireRole({ roles, loginRole, children }: { roles: ("staff" | "doctor")[]; loginRole: "staff" | "doctor"; children: (me: Me) => ReactNode }) {
  const me = useMe();
  if (me.isPending)
    return (
      <div className="p-6" aria-busy>
        <Skeleton className="h-8 w-64" />
      </div>
    );
  if (!me.data) return <LoginPage role={loginRole} />;
  if (!roles.includes(me.data.role))
    return (
      <main className="grid min-h-dvh place-items-center p-6">
        <Notice tone="stop" title="This screen is for doctors">
          You are signed in as {me.data.username} ({me.data.role}). Use the staff desk, or sign out and sign in as a doctor.
          <div className="mt-3">
            <Button
              size="sm"
              onClick={async () => {
                await post("/api/auth/logout");
                location.reload();
              }}
            >
              Sign out
            </Button>
          </div>
        </Notice>
      </main>
    );
  return <>{children(me.data)}</>;
}

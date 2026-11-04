import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router";
import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError } from "./api/client";
import "./styles/app.css";
import { Chooser } from "./Chooser";

function on401(e: unknown) {
  // a staff/doctor login that expired: show the sign-in page (kiosk calls never use the login)
  if (e instanceof ApiError && e.status === 401 && !location.pathname.startsWith("/kiosk")) {
    try {
      if (e.message.includes("inactivity")) sessionStorage.setItem("mk.login.notice", e.message);
    } catch {
      /* ignore */
    }
    qc.setQueryData(["me"], null);
  }
}

const qc = new QueryClient({
  queryCache: new QueryCache({ onError: on401 }),
  mutationCache: new MutationCache({ onError: on401 }),
  defaultOptions: {
    queries: { retry: (n, e) => !(e instanceof ApiError && e.status >= 400 && e.status < 500) && n < 2, refetchOnWindowFocus: false, staleTime: 5_000 },
  },
});

const KioskApp = lazy(() => import("./kiosk/KioskApp"));
const StaffApp = lazy(() => import("./staff/StaffApp"));
const DoctorApp = lazy(() => import("./doctor/DoctorApp"));
const Gallery = lazy(() => import("./gallery/Gallery"));

function Loading() {
  return <div className="min-h-dvh bg-paper" aria-busy="true" />;
}

const router = createBrowserRouter([
  { path: "/", element: <Chooser /> },
  { path: "/kiosk/*", element: <Suspense fallback={<Loading />}><KioskApp /></Suspense> },
  { path: "/staff/*", element: <Suspense fallback={<Loading />}><StaffApp /></Suspense> },
  { path: "/doctor/*", element: <Suspense fallback={<Loading />}><DoctorApp /></Suspense> },
  { path: "/gallery", element: <Suspense fallback={<Loading />}><Gallery /></Suspense> },
  { path: "*", element: <Chooser notFound /> },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);

import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle2,
  LoaderCircle,
  MapPin,
  Navigation,
  Truck,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import { cityState } from "../utils";

type ShareState =
  | "idle"
  | "requesting"
  | "success"
  | "denied"
  | "unsupported"
  | "error";

export default function Tracking() {
  const { token = "" } = useParams();
  const [shareState, setShareState] = useState<ShareState>("idle");
  const [errorText, setErrorText] = useState("");
  const watchId = useRef<number | null>(null);
  const lastSentAt = useRef(0);
  const summary = useQuery({
    queryKey: ["tracking", token],
    queryFn: () => api.trackingSummary(token),
    retry: false,
  });

  useEffect(
    () => () => {
      if (watchId.current !== null && navigator.geolocation) {
        navigator.geolocation.clearWatch(watchId.current);
      }
    },
    [],
  );

  async function sendLocation(position: GeolocationPosition) {
    const { latitude, longitude, accuracy } = position.coords;
    await api.trackingPing(token, {
      lat: latitude,
      lng: longitude,
      accuracy_m: accuracy,
    });
    lastSentAt.current = Date.now();
    setShareState("success");
  }

  function shareLocation() {
    if (!navigator.geolocation) {
      setShareState("unsupported");
      return;
    }
    setShareState("requesting");
    setErrorText("");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        void sendLocation(position)
          .then(() => {
            watchId.current = navigator.geolocation.watchPosition(
              (nextPosition) => {
                if (Date.now() - lastSentAt.current >= 5 * 60_000) {
                  void sendLocation(nextPosition).catch((error: Error) =>
                    setErrorText(error.message),
                  );
                }
              },
              (error) => setErrorText(error.message),
              { enableHighAccuracy: true, maximumAge: 30_000 },
            );
          })
          .catch((error: Error) => {
            setErrorText(error.message);
            setShareState("error");
          });
      },
      (error) => {
        setShareState(
          error.code === 1 ? "denied" : "error",
        );
        setErrorText(error.message);
      },
      { enableHighAccuracy: true, timeout: 20_000, maximumAge: 0 },
    );
  }

  if (summary.isPending) {
    return (
      <main className="grid min-h-screen place-items-center bg-canvas px-5">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-500">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          Opening tracking link…
        </div>
      </main>
    );
  }
  if (summary.isError) {
    return (
      <main className="grid min-h-screen place-items-center bg-canvas px-5">
        <section className="w-full max-w-sm rounded-3xl border border-slate-200 bg-white p-7 text-center shadow-card">
          <span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-slate-100 text-slate-500">
            <MapPin className="h-6 w-6" />
          </span>
          <h1 className="mt-5 text-xl font-extrabold text-slate-900">
            This link is no longer active
          </h1>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            Please contact your broker for an updated tracking link.
          </p>
        </section>
      </main>
    );
  }
  const load = summary.data;
  const lane = `${cityState(load.pickup_city, load.pickup_state)} → ${cityState(load.delivery_city, load.delivery_state)}`;
  return (
    <main className="min-h-screen bg-canvas px-4 py-8 sm:grid sm:place-items-center sm:px-6 sm:py-12">
      <section className="mx-auto w-full max-w-md overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-card">
        <header className="bg-brand-950 px-6 pb-7 pt-6 text-white">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-600 text-white">
              <Truck className="h-4 w-4" />
            </span>
            {load.broker_company}
          </div>
          <p className="mt-6 text-[11px] font-bold uppercase tracking-[0.16em] text-brand-300">
            Driver location
          </p>
          <h1 className="mt-1 text-2xl font-extrabold tracking-tight">
            Load {load.reference}
          </h1>
          <p className="mt-2 text-sm text-slate-300">{lane}</p>
        </header>
        <div className="px-6 py-7">
          <div className="mx-auto grid h-28 w-28 place-items-center rounded-full bg-brand-50">
            <span className="grid h-20 w-20 place-items-center rounded-full bg-brand-100 text-brand-700">
              {shareState === "success" ? (
                <CheckCircle2 className="h-9 w-9" />
              ) : shareState === "requesting" ? (
                <LoaderCircle className="h-9 w-9 animate-spin" />
              ) : (
                <Navigation className="h-9 w-9" />
              )}
            </span>
          </div>
          {shareState === "success" ? (
            <div className="mt-5 text-center">
              <h2 className="text-lg font-extrabold text-slate-900">Location shared</h2>
              <p className="mt-1 text-sm leading-6 text-slate-500">
                Thanks! Location shared. You can close this page.
              </p>
            </div>
          ) : (
            <div className="mt-5 text-center">
              <h2 className="text-lg font-extrabold text-slate-900">Keep your team in the loop</h2>
              <p className="mt-1 text-sm leading-6 text-slate-500">
                Share your current location with the broker. Your location stays internal.
              </p>
            </div>
          )}
          <button
            onClick={shareLocation}
            disabled={shareState === "requesting"}
            className="mt-6 flex min-h-14 w-full items-center justify-center gap-2 rounded-2xl bg-brand-600 px-5 text-base font-bold text-white shadow-sm shadow-brand-200 transition hover:bg-brand-700 disabled:cursor-wait disabled:opacity-70"
          >
            {shareState === "requesting" ? (
              <LoaderCircle className="h-5 w-5 animate-spin" />
            ) : (
              <MapPin className="h-5 w-5" />
            )}
            {shareState === "requesting" ? "Finding your location…" : "Share my location"}
          </button>
          {shareState === "denied" && (
            <p className="mt-3 rounded-xl bg-amber-50 px-3 py-2.5 text-xs leading-5 text-amber-900">
              Location access was denied. Enable location permissions in your browser settings, then try again.
            </p>
          )}
          {shareState === "unsupported" && (
            <p className="mt-3 rounded-xl bg-amber-50 px-3 py-2.5 text-xs leading-5 text-amber-900">
              This browser does not support location sharing.
            </p>
          )}
          {(shareState === "error" || errorText) && (
            <p className="mt-3 rounded-xl bg-rose-50 px-3 py-2.5 text-xs leading-5 text-rose-800">
              {errorText || "Unable to share your location. Please try again."}
            </p>
          )}
          <p className="mt-5 text-center text-[11px] text-slate-400">
            Location updates are sent no more than once every 5 minutes.
          </p>
        </div>
      </section>
    </main>
  );
}

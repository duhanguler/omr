import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Camera,
  CameraOff,
  CheckCircle2,
  Crosshair,
  QrCode,
  Radio,
  ScanLine,
} from "lucide-react";
import { scanFiles } from "../api/client";
import type { Dictionary } from "../i18n";
import type { SheetResult, Template } from "../types";

interface CameraScannerProps {
  t: Dictionary;
  activeTemplate: Template | null;
  onSheetCaptured: (
    sheet: SheetResult,
    overlayUrl?: string,
    crops?: Record<string, string>,
    dims?: [number, number]
  ) => void;
  onGoToReview: () => void;
}

function playSuccessTone() {
  try {
    const AudioCtx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    const ctx = new AudioCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(1320, ctx.currentTime + 0.09);
    gain.gain.setValueAtTime(0.08, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.16);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.onended = () => {
      void ctx.close().catch(() => {});
    };
    osc.start();
    osc.stop(ctx.currentTime + 0.17);
  } catch {
    // Ignore autoplay restriction
  }
}

export function CameraScanner({
  t,
  activeTemplate,
  onSheetCaptured,
  onGoToReview,
}: CameraScannerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const busyRef = useRef(false);
  const mountedRef = useRef(true);
  const captureSeqRef = useRef(0);
  const flashTimerRef = useRef<number | null>(null);

  const [cameraActive, setCameraActive] = useState(false);
  const [resolution, setResolution] = useState<string | null>(null);
  const [autoLock, setAutoLock] = useState(false);
  const [useQrAuto, setUseQrAuto] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [flashOk, setFlashOk] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [captured, setCaptured] = useState<{ sheet: SheetResult; overlay?: string }[]>([]);

  const stopCamera = useCallback(() => {
    setAutoLock(false);
    setCameraActive(false);
    setResolution(null);
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((tr) => tr.stop());
      streamRef.current = null;
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (flashTimerRef.current !== null) {
        window.clearTimeout(flashTimerRef.current);
      }
      stopCamera();
    };
  }, [stopCamera]);

  async function startCamera() {
    setError(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("Camera access requires an HTTPS or localhost browser context.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1920 },
          height: { ideal: 1080 },
        },
        audio: false,
      });
      if (!mountedRef.current) {
        stream.getTracks().forEach((tr) => tr.stop());
        return;
      }
      streamRef.current = stream;
      const settings = stream.getVideoTracks()[0]?.getSettings();
      if (settings?.width && settings?.height) {
        setResolution(`${settings.width}×${settings.height}`);
      }
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setCameraActive(true);
    } catch (err) {
      if (mountedRef.current) {
        setError(
          err instanceof Error
            ? `Could not open camera: ${err.message}`
            : "Camera permission denied or no camera detected."
        );
      }
    }
  }

  const captureFrameAndScan = useCallback(
    async (silentIfNoLock = false) => {
      if (busyRef.current || !videoRef.current || !canvasRef.current) return;
      const video = videoRef.current;
      if (video.videoWidth === 0 || video.videoHeight === 0) return;

      busyRef.current = true;
      setScanning(true);
      try {
        const canvas = canvasRef.current;
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext("2d");
        if (!ctx) return;
        ctx.drawImage(video, 0, 0);

        const blob = await new Promise<Blob | null>((resolve) =>
          canvas.toBlob(resolve, "image/jpeg", 0.9)
        );
        if (!blob || !mountedRef.current) return;

        captureSeqRef.current += 1;
        const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(11, 23);
        const frameFile = new File([blob], `camera_${stamp}_${captureSeqRef.current}.jpg`, {
          type: "image/jpeg",
        });
        const targetTemplate = useQrAuto || !activeTemplate ? "auto" : activeTemplate;
        const res = await scanFiles([frameFile], targetTemplate);
        if (!mountedRef.current) return;
        const sheet = res.sheets[0];

        if (sheet && !sheet.error) {
          const overlayUrl = res.overlays[sheet.sheet_id];
          const crops = res.review_crops?.[sheet.sheet_id];
          const dims = res.sheet_dimensions?.[sheet.sheet_id];
          setCaptured((prev) => [{ sheet, overlay: overlayUrl }, ...prev]);
          onSheetCaptured(sheet, overlayUrl, crops, dims);
          playSuccessTone();
          setFlashOk(true);
          if (flashTimerRef.current !== null) {
            window.clearTimeout(flashTimerRef.current);
          }
          flashTimerRef.current = window.setTimeout(() => {
            if (mountedRef.current) setFlashOk(false);
          }, 600);
          setError(null);
        } else if (!silentIfNoLock && sheet?.error) {
          setError(sheet.error);
        }
      } catch (err) {
        if (!silentIfNoLock && mountedRef.current) {
          setError(err instanceof Error ? err.message : "Frame scan failed.");
        }
      } finally {
        busyRef.current = false;
        if (mountedRef.current) {
          setScanning(false);
        }
      }
    },
    [activeTemplate, onSheetCaptured, useQrAuto]
  );

  useEffect(() => {
    if (!cameraActive || !autoLock) return;
    const timer = window.setInterval(() => {
      void captureFrameAndScan(true);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [cameraActive, autoLock, captureFrameAndScan]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
      {/* Left Optical Viewfinder */}
      <section className="lg:col-span-7 paper-card overflow-hidden">
        <div className="px-4 py-3 border-b border-[var(--border-hairline)] flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold">{t.cameraTitle}</h2>
            <p className="text-xs text-[var(--ink-muted)]">{t.cameraSub}</p>
          </div>
          <div className="flex items-center gap-2">
            {resolution && (
              <span className="text-[11px] font-mono text-[var(--ink-muted)] px-2 py-0.5 rounded-[4px] bg-[var(--surface-subtle)] border border-[var(--border-hairline)]">
                {resolution}
              </span>
            )}
            {!cameraActive ? (
              <button type="button" onClick={() => void startCamera()} className="btn-accent text-xs">
                <Camera className="w-3.5 h-3.5" /> {t.startCamera}
              </button>
            ) : (
              <button type="button" onClick={stopCamera} className="btn-secondary text-xs">
                <CameraOff className="w-3.5 h-3.5" /> {t.stopCamera}
              </button>
            )}
          </div>
        </div>

        <div className="p-4 space-y-3">
          <div
            className={`relative rounded-[5px] overflow-hidden bg-[#111317] aspect-video flex items-center justify-center border-2 transition-colors ${
              flashOk ? "border-[var(--signal-ok)]" : "border-[var(--border-hairline)]"
            }`}
          >
            <video
              ref={videoRef}
              playsInline
              muted
              className={`w-full h-full object-contain ${cameraActive ? "block" : "hidden"}`}
            />
            <canvas ref={canvasRef} className="hidden" />

            {/* Precision Optical Corner Reticle */}
            {cameraActive && (
              <div className="pointer-events-none absolute inset-6 border border-white/20">
                <div className="absolute -top-0.5 -left-0.5 w-6 h-6 border-t-2 border-l-2 border-white" />
                <div className="absolute -top-0.5 -right-0.5 w-6 h-6 border-t-2 border-r-2 border-white" />
                <div className="absolute -bottom-0.5 -left-0.5 w-6 h-6 border-b-2 border-l-2 border-white" />
                <div className="absolute -bottom-0.5 -right-0.5 w-6 h-6 border-b-2 border-r-2 border-white" />
                <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-5 h-5 border border-white/30 rounded-full" />
              </div>
            )}

            {!cameraActive && (
              <div className="text-center text-white/75 space-y-2 p-6">
                <Crosshair className="w-8 h-8 mx-auto opacity-60" />
                <p className="text-xs font-mono uppercase tracking-wider text-white">
                  {t.cameraOffline}
                </p>
                <p className="text-xs text-white/60 max-w-sm">{t.cameraOfflineSub}</p>
              </div>
            )}

            {flashOk && (
              <div className="absolute top-3 left-3 px-2.5 py-1 rounded-[4px] bg-[var(--signal-ok)] text-white text-xs font-mono inline-flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5" /> {t.cameraLocked}
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
            <label className="inline-flex items-center gap-2 text-xs text-[var(--ink-primary)] cursor-pointer">
              <input
                type="checkbox"
                checked={useQrAuto}
                onChange={(e) => setUseQrAuto(e.target.checked)}
              />
              <QrCode className="w-3.5 h-3.5 text-[var(--ink-secondary)]" />
              <span>{t.cameraQrToggle}</span>
            </label>

            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={!cameraActive}
                onClick={() => setAutoLock((v) => !v)}
                className={`text-xs ${autoLock ? "btn-primary" : "btn-secondary"}`}
              >
                <Radio className="w-3.5 h-3.5" />
                {autoLock ? t.autoLockOn : t.autoLockOff}
              </button>
              <button
                type="button"
                disabled={!cameraActive || scanning}
                onClick={() => void captureFrameAndScan(false)}
                className="btn-accent text-xs"
              >
                <ScanLine className="w-3.5 h-3.5" />
                {scanning ? t.scanning : t.captureScan}
              </button>
            </div>
          </div>

          {error && (
            <div className="text-xs p-2.5 rounded-[4px] bg-[var(--signal-err-bg)] text-[var(--signal-err)] border border-red-200 font-mono">
              {error}
            </div>
          )}
        </div>
      </section>

      {/* Right Capture Ledger */}
      <aside className="lg:col-span-5 paper-card overflow-hidden">
        <div className="px-4 py-3 border-b border-[var(--border-hairline)] flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold">
              {t.capturedSession} ({captured.length})
            </h3>
            <p className="text-[11px] text-[var(--ink-muted)] font-mono">{t.capturedSessionSub}</p>
          </div>
          {captured.length > 0 && (
            <button type="button" onClick={onGoToReview} className="btn-primary text-xs">
              {t.reviewBatch} <ArrowRight className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        <div className="p-3.5 space-y-2.5 max-h-[68vh] overflow-y-auto">
          {captured.length === 0 ? (
            <div className="py-12 text-center space-y-2 text-[var(--ink-muted)]">
              <Crosshair className="w-6 h-6 mx-auto opacity-45" />
              <p className="text-xs max-w-xs mx-auto">{t.capturedEmpty}</p>
            </div>
          ) : (
            captured.map(({ sheet, overlay }) => (
              <div
                key={sheet.sheet_id}
                className="p-2.5 rounded-[5px] border border-[var(--border-hairline)] bg-[var(--surface-paper)] flex gap-3 items-start"
              >
                {overlay && (
                  <img
                    src={overlay}
                    alt={sheet.sheet_id}
                    className="w-18 h-24 object-cover rounded-[3px] border border-[var(--border-strong)] shrink-0 bg-white"
                  />
                )}
                <div className="flex-1 min-w-0 space-y-1 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono font-semibold truncate">{sheet.sheet_id}</span>
                    <span className="font-mono text-[var(--signal-ok)]">
                      {(sheet.overall_confidence * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="text-[11px] font-mono text-[var(--ink-muted)]">
                    {sheet.template_name} · {sheet.registration_method} · flags:{sheet.review_items.length}
                  </div>
                  {Object.keys(sheet.grouped_values).length > 0 && (
                    <div className="text-[11px] font-mono text-[var(--ink-primary)] pt-0.5">
                      {Object.entries(sheet.grouped_values)
                        .map(([k, v]) => `${k}: ${v}`)
                        .join(" | ")}
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </aside>
    </div>
  );
}

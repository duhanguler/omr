import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Camera,
  CameraOff,
  CheckCircle2,
  QrCode,
  Radio,
  ScanLine,
  Sparkles,
} from "lucide-react";
import { scanFiles } from "../api/client";
import type { SheetResult, Template } from "../types";

interface CameraScannerProps {
  activeTemplate: Template | null;
  onSheetCaptured: (sheet: SheetResult, overlayUrl?: string) => void;
  onGoToReview: () => void;
}

function playSuccessTone() {
  try {
    const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
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
  const [autoLock, setAutoLock] = useState(false);
  const [useQrAuto, setUseQrAuto] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [flashOk, setFlashOk] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [captured, setCaptured] = useState<{ sheet: SheetResult; overlay?: string }[]>([]);

  const stopCamera = useCallback(() => {
    setAutoLock(false);
    setCameraActive(false);
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
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
      setError("Camera access is not available in this browser context (HTTPS or localhost required).");
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
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      streamRef.current = stream;
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
        const frameFile = new File(
          [blob],
          `camera_${stamp}_${captureSeqRef.current}.jpg`,
          { type: "image/jpeg" }
        );
        const targetTemplate = useQrAuto || !activeTemplate ? "auto" : activeTemplate;
        const res = await scanFiles([frameFile], targetTemplate);
        if (!mountedRef.current) return;
        const sheet = res.sheets[0];

        if (sheet && !sheet.error) {
          const overlayUrl = res.overlays[sheet.sheet_id];
          setCaptured((prev) => [{ sheet, overlay: overlayUrl }, ...prev]);
          onSheetCaptured(sheet, overlayUrl);
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
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
      {/* Left Live Viewfinder */}
      <section className="lg:col-span-7 paper-card overflow-hidden">
        <div className="px-4 py-3 border-b border-[var(--border-hairline)] flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold">Live Webcam / Mobile Camera Scanner</h2>
            <p className="text-xs text-[var(--ink-muted)]">
              Point your camera at any ArUco or marker optical sheet — auto-lock captures when all 4 corners align.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {!cameraActive ? (
              <button type="button" onClick={() => void startCamera()} className="btn-accent text-xs">
                <Camera className="w-3.5 h-3.5" /> Start Camera
              </button>
            ) : (
              <button type="button" onClick={stopCamera} className="btn-secondary text-xs">
                <CameraOff className="w-3.5 h-3.5" /> Stop
              </button>
            )}
          </div>
        </div>

        <div className="p-4 space-y-3">
          <div
            className={`relative rounded-lg overflow-hidden bg-[#14181F] aspect-video flex items-center justify-center border-2 transition-colors ${
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

            {/* Optical corner alignment guide brackets */}
            {cameraActive && (
              <div className="pointer-events-none absolute inset-6 border border-white/25 rounded">
                <div className="absolute -top-0.5 -left-0.5 w-6 h-6 border-t-2 border-l-2 border-white" />
                <div className="absolute -top-0.5 -right-0.5 w-6 h-6 border-t-2 border-r-2 border-white" />
                <div className="absolute -bottom-0.5 -left-0.5 w-6 h-6 border-b-2 border-l-2 border-white" />
                <div className="absolute -bottom-0.5 -right-0.5 w-6 h-6 border-b-2 border-r-2 border-white" />
              </div>
            )}

            {!cameraActive && (
              <div className="text-center text-white/75 space-y-2 p-6">
                <Camera className="w-9 h-9 mx-auto opacity-70" />
                <p className="text-sm font-medium text-white">Camera viewfinder offline</p>
                <p className="text-xs text-white/60 max-w-sm">
                  Click <strong>Start Camera</strong> to scan printed ArUco sheets in real time from a webcam or mobile phone browser.
                </p>
              </div>
            )}

            {flashOk && (
              <div className="absolute top-3 left-3 px-2.5 py-1 rounded bg-[var(--signal-ok)] text-white text-xs font-mono inline-flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5" /> Sheet Locked & Captured
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
              <span>Auto-detect template via sheet QR code</span>
            </label>

            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={!cameraActive}
                onClick={() => setAutoLock((v) => !v)}
                className={`text-xs ${autoLock ? "btn-primary" : "btn-secondary"}`}
              >
                <Radio className={`w-3.5 h-3.5 ${autoLock ? "animate-pulse text-emerald-400" : ""}`} />
                {autoLock ? "Auto-Lock ON" : "Auto-Lock OFF"}
              </button>
              <button
                type="button"
                disabled={!cameraActive || scanning}
                onClick={() => void captureFrameAndScan(false)}
                className="btn-accent text-xs"
              >
                <ScanLine className="w-3.5 h-3.5" />
                {scanning ? "Scanning..." : "Capture & Scan"}
              </button>
            </div>
          </div>

          {error && (
            <div className="text-xs p-2.5 rounded bg-[var(--signal-err-bg)] text-[var(--signal-err)] border border-red-200 font-mono">
              {error}
            </div>
          )}
        </div>
      </section>

      {/* Right Session Feed */}
      <aside className="lg:col-span-5 paper-card overflow-hidden">
        <div className="px-4 py-3 border-b border-[var(--border-hairline)] flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold">Captured Session ({captured.length})</h3>
            <p className="text-xs text-[var(--ink-muted)] font-mono">
              Every captured sheet joins your main batch for HITL review & grading
            </p>
          </div>
          {captured.length > 0 && (
            <button type="button" onClick={onGoToReview} className="btn-primary text-xs">
              Review Batch <ArrowRight className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        <div className="p-4 space-y-3 max-h-[68vh] overflow-y-auto">
          {captured.length === 0 ? (
            <div className="py-12 text-center space-y-2 text-[var(--ink-muted)]">
              <Sparkles className="w-7 h-7 mx-auto opacity-50" />
              <p className="text-xs max-w-xs mx-auto">
                Captured sheets will stream here with their live confidence score, detected template, and verification overlay.
              </p>
            </div>
          ) : (
            captured.map(({ sheet, overlay }) => (
              <div
                key={sheet.sheet_id}
                className="p-3 rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-paper)] flex gap-3 items-start"
              >
                {overlay && (
                  <img
                    src={overlay}
                    alt={sheet.sheet_id}
                    className="w-20 h-28 object-cover rounded border border-[var(--border-hairline)] shrink-0 bg-white"
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
                    Template: {sheet.template_name} · Flags: {sheet.review_items.length}
                  </div>
                  {Object.keys(sheet.grouped_values).length > 0 && (
                    <div className="text-[11px] font-mono text-[var(--ink-primary)] pt-1">
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

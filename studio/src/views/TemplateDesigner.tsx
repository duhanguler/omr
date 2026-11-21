import { useCallback, useEffect, useRef, useState } from "react";
import {
  Check,
  Crosshair,
  Download,
  FileCode2,
  Plus,
  Redo2,
  Trash2,
  Undo2,
  Upload,
} from "lucide-react";
import {
  autoDetectTemplateLayout,
  migrateLegacyTemplate,
  previewUploadedDocument,
  triggerBlobDownload,
  validateTemplate,
} from "../api/client";
import type { Dictionary } from "../i18n";
import type { FieldBlock, RegistrationMode, Template } from "../types";

interface TemplateDesignerProps {
  t: Dictionary;
  activeTemplate: Template | null;
  onUseTemplate: (template: Template) => void;
}

interface DragRect {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

interface MoveState {
  blockIdx: number;
  startCanvasX: number;
  startCanvasY: number;
  origX: number;
  origY: number;
  snapshot: Template;
}

interface BlockBounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

const MAX_HISTORY = 40;

function expandLabelsPreview(labels: string[]): string[] {
  const MAX_PREVIEW = 500;
  const out: string[] = [];
  for (const token of labels) {
    if (out.length >= MAX_PREVIEW) break;
    const m = /^(.*[^.\d])(\d+)\.{2,3}(\d+)$/.exec(token.trim());
    if (m) {
      const [, prefix, s, e] = m;
      const start = Number(s);
      const end = Number(e);
      if (end >= start) {
        const limit = Math.min(end, start + (MAX_PREVIEW - out.length) - 1);
        for (let i = start; i <= limit; i += 1) {
          out.push(`${prefix}${i}`);
        }
      }
    } else if (token.trim()) {
      out.push(token.trim());
    }
  }
  return out;
}

function computeBlockBounds(blk: FieldBlock, scale: number): BlockBounds | null {
  const expanded = expandLabelsPreview(blk.labels);
  if (expanded.length === 0 || blk.options.length === 0) return null;

  const ox = blk.origin[0] + (blk.origin_mode === "top_left" ? blk.bubble_radius : 0);
  const oy = blk.origin[1] + (blk.origin_mode === "top_left" ? blk.bubble_radius : 0);
  const sr = Math.max(2.5, blk.bubble_radius * scale);

  const maxFi = expanded.length - 1;
  const maxOi = blk.options.length - 1;
  const endX = blk.direction === "horizontal" ? ox + maxOi * blk.bubbles_gap : ox + maxFi * blk.labels_gap;
  const endY = blk.direction === "horizontal" ? oy + maxFi * blk.labels_gap : oy + maxOi * blk.bubbles_gap;

  const sx0 = Math.min(ox, endX) * scale;
  const sy0 = Math.min(oy, endY) * scale;
  const sx1 = Math.max(ox, endX) * scale;
  const sy1 = Math.max(oy, endY) * scale;

  return {
    minX: sx0 - sr - 5,
    minY: sy0 - sr - 5,
    maxX: sx1 + sr + 5,
    maxY: sy1 + sr + 5,
  };
}

export function TemplateDesigner({ t, activeTemplate, onUseTemplate }: TemplateDesignerProps) {
  const [template, setTemplate] = useState<Template>(
    () =>
      activeTemplate ?? {
        version: "2.0",
        name: "custom_sheet",
        description: "Designed in OMRKit Studio",
        page_width: 1654,
        page_height: 2339,
        registration: { mode: "none" },
        detection: {
          fill_threshold: 0.26,
          blank_floor: 0.14,
          min_separation: 0.09,
          review_confidence_threshold: 0.72,
          normalize_illumination: true,
        },
        blocks: [
          {
            name: "MCQ_1",
            field_type: "mcq",
            direction: "horizontal",
            origin: [240, 420],
            origin_mode: "center",
            bubble_radius: 16,
            bubbles_gap: 48,
            labels_gap: 50,
            options: ["A", "B", "C", "D", "E"],
            labels: ["q1..10"],
          },
        ],
      }
  );
  const [past, setPast] = useState<Template[]>([]);
  const [future, setFuture] = useState<Template[]>([]);
  const [bgImageUrl, setBgImageUrl] = useState<string | null>(null);
  const [selectedIdx, setSelectedIdx] = useState<number>(0);
  const [optionsDraft, setOptionsDraft] = useState<string>("");
  const [labelsDraft, setLabelsDraft] = useState<string>("");
  const [dragRect, setDragRect] = useState<DragRect | null>(null);
  const [moveState, setMoveState] = useState<MoveState | null>(null);
  const [hoverBlockIdx, setHoverBlockIdx] = useState<number | null>(null);
  const [cursorPx, setCursorPx] = useState<{ x: number; y: number } | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [detecting, setDetecting] = useState(false);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const autoDetectRef = useRef<HTMLInputElement>(null);
  const legacyRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (activeTemplate) {
      setTemplate(activeTemplate);
      setPast([]);
      setFuture([]);
      setSelectedIdx(0);
    }
  }, [activeTemplate]);

  const commitChange = useCallback((updater: (prev: Template) => Template) => {
    setTemplate((prev) => {
      const next = updater(prev);
      setPast((h) => [...h.slice(-(MAX_HISTORY - 1)), prev]);
      setFuture([]);
      return next;
    });
  }, []);

  const handleUndo = useCallback(() => {
    setPast((prevPast) => {
      if (prevPast.length === 0) return prevPast;
      const previous = prevPast[prevPast.length - 1];
      setTemplate((curr) => {
        setFuture((f) => [curr, ...f.slice(0, MAX_HISTORY - 1)]);
        return previous;
      });
      setSelectedIdx((idx) => Math.min(idx, Math.max(0, previous.blocks.length - 1)));
      return prevPast.slice(0, -1);
    });
  }, []);

  const handleRedo = useCallback(() => {
    setFuture((prevFuture) => {
      if (prevFuture.length === 0) return prevFuture;
      const next = prevFuture[0];
      setTemplate((curr) => {
        setPast((p) => [...p.slice(-(MAX_HISTORY - 1)), curr]);
        return next;
      });
      setSelectedIdx((idx) => Math.min(idx, Math.max(0, next.blocks.length - 1)));
      return prevFuture.slice(1);
    });
  }, []);

  // Keyboard shortcuts: Arrow micro-nudge (1px / Shift 10px) + Ctrl/Cmd Undo/Redo
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT")
      ) {
        return;
      }

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) {
          handleRedo();
        } else {
          handleUndo();
        }
        return;
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "y") {
        e.preventDefault();
        handleRedo();
        return;
      }

      const step = e.shiftKey ? 10 : 1;
      let dx = 0;
      let dy = 0;
      if (e.key === "ArrowLeft") dx = -step;
      else if (e.key === "ArrowRight") dx = step;
      else if (e.key === "ArrowUp") dy = -step;
      else if (e.key === "ArrowDown") dy = step;
      else return;

      e.preventDefault();
      commitChange((prev) => {
        if (!prev.blocks[selectedIdx]) return prev;
        return {
          ...prev,
          blocks: prev.blocks.map((b, i) =>
            i === selectedIdx
              ? {
                  ...b,
                  origin: [
                    Math.max(0, Math.round(b.origin[0] + dx)),
                    Math.max(0, Math.round(b.origin[1] + dy)),
                  ],
                }
              : b
          ),
        };
      });
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [selectedIdx, commitChange, handleUndo, handleRedo]);

  const activeBlockForDraft = template.blocks[selectedIdx];
  useEffect(() => {
    if (activeBlockForDraft) {
      setOptionsDraft(activeBlockForDraft.options.join(", "));
      setLabelsDraft(activeBlockForDraft.labels.join(", "));
    }
    // Sync drafts whenever the user switches blocks or loads a new template
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedIdx, template.name, template.blocks.length]);

  useEffect(() => {
    if (!bgImageUrl) {
      imgRef.current = null;
      drawCanvas();
      return;
    }
    const img = new Image();
    img.onload = () => {
      imgRef.current = img;
      drawCanvas();
    };
    img.src = bgImageUrl;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bgImageUrl]);

  useEffect(() => {
    drawCanvas();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [template, selectedIdx, dragRect, hoverBlockIdx]);

  function getCanvasScale(): number {
    const maxDisplayW = 760;
    return Math.min(1, maxDisplayW / Math.max(100, template.page_width));
  }

  function nextUniqueBlockNumber(blocks: FieldBlock[]): number {
    const existingNames = new Set(blocks.map((b) => b.name));
    const existingLabels = new Set(blocks.flatMap((b) => expandLabelsPreview(b.labels)));
    let n = blocks.length + 1;
    while (
      existingNames.has(`BLOCK_${n}`) ||
      existingLabels.has(`b${n}_1`) ||
      existingLabels.has(`f${n * 100 + 1}`)
    ) {
      n += 1;
    }
    return n;
  }

  function drawCanvas() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const scale = getCanvasScale();
    const targetW = Math.round(template.page_width * scale);
    const targetH = Math.round(template.page_height * scale);
    if (canvas.width !== targetW) canvas.width = targetW;
    if (canvas.height !== targetH) canvas.height = targetH;

    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    if (imgRef.current) {
      ctx.drawImage(imgRef.current, 0, 0, canvas.width, canvas.height);
    } else {
      ctx.strokeStyle = "#ece9e0";
      ctx.lineWidth = 1;
      for (let x = 0; x < canvas.width; x += 40) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, canvas.height);
        ctx.stroke();
      }
      for (let y = 0; y < canvas.height; y += 40) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(canvas.width, y);
        ctx.stroke();
      }
    }

    // Draw all FieldBlocks and their bubbles
    template.blocks.forEach((blk, bIdx) => {
      const isSelected = bIdx === selectedIdx;
      const isHovered = bIdx === hoverBlockIdx && !isSelected;
      const expanded = expandLabelsPreview(blk.labels);
      const ox = blk.origin[0] + (blk.origin_mode === "top_left" ? blk.bubble_radius : 0);
      const oy = blk.origin[1] + (blk.origin_mode === "top_left" ? blk.bubble_radius : 0);

      let minX = Infinity;
      let minY = Infinity;
      let maxX = -Infinity;
      let maxY = -Infinity;

      expanded.forEach((_, fi) => {
        blk.options.forEach((opt, oi) => {
          const cx =
            blk.direction === "horizontal" ? ox + oi * blk.bubbles_gap : ox + fi * blk.labels_gap;
          const cy =
            blk.direction === "horizontal" ? oy + fi * blk.labels_gap : oy + oi * blk.bubbles_gap;
          const sx = cx * scale;
          const sy = cy * scale;
          const sr = Math.max(2.5, blk.bubble_radius * scale);

          minX = Math.min(minX, sx - sr);
          minY = Math.min(minY, sy - sr);
          maxX = Math.max(maxX, sx + sr);
          maxY = Math.max(maxY, sy + sr);

          ctx.beginPath();
          ctx.arc(sx, sy, sr, 0, Math.PI * 2);
          ctx.fillStyle = isSelected
            ? "rgba(24, 73, 198, 0.14)"
            : isHovered
              ? "rgba(13, 122, 82, 0.16)"
              : "rgba(13, 122, 82, 0.09)";
          ctx.fill();
          ctx.lineWidth = isSelected ? 1.6 : 1.1;
          ctx.strokeStyle = isSelected ? "#1849c6" : "#0d7a52";
          ctx.stroke();

          if (sr >= 6) {
            ctx.fillStyle = isSelected ? "#133ba3" : "#065f46";
            ctx.font = `${Math.max(8, Math.round(sr * 0.9))}px "IBM Plex Mono", monospace`;
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText(opt, sx, sy);
          }
        });
      });

      if (Number.isFinite(minX)) {
        const bx = minX - 5;
        const by = minY - 5;
        const bw = maxX - minX + 10;
        const bh = maxY - minY + 10;

        ctx.strokeStyle = isSelected
          ? "#1849c6"
          : isHovered
            ? "#0d7a52"
            : "rgba(13, 122, 82, 0.55)";
        ctx.lineWidth = isSelected ? 1.5 : 1;
        ctx.setLineDash(isSelected ? [] : [4, 3]);
        ctx.strokeRect(bx, by, bw, bh);
        ctx.setLineDash([]);

        // Corner calibration ticks on selected block
        if (isSelected) {
          ctx.fillStyle = "#1849c6";
          const s = 4;
          ctx.fillRect(bx - 2, by - 2, s, s);
          ctx.fillRect(bx + bw - 2, by - 2, s, s);
          ctx.fillRect(bx - 2, by + bh - 2, s, s);
          ctx.fillRect(bx + bw - 2, by + bh - 2, s, s);
        }

        ctx.fillStyle = isSelected ? "#1849c6" : "#0d7a52";
        ctx.font = '600 10px "IBM Plex Mono", monospace';
        ctx.textAlign = "left";
        ctx.textBaseline = "alphabetic";
        ctx.fillText(blk.name, minX - 4, Math.max(12, minY - 9));
      }
    });

    if (dragRect) {
      const rx = Math.min(dragRect.x0, dragRect.x1);
      const ry = Math.min(dragRect.y0, dragRect.y1);
      const rw = Math.abs(dragRect.x1 - dragRect.x0);
      const rh = Math.abs(dragRect.y1 - dragRect.y0);
      ctx.fillStyle = "rgba(24, 73, 198, 0.09)";
      ctx.fillRect(rx, ry, rw, rh);
      ctx.strokeStyle = "#1849c6";
      ctx.lineWidth = 1.5;
      ctx.setLineDash([5, 3]);
      ctx.strokeRect(rx, ry, rw, rh);
      ctx.setLineDash([]);
    }
  }

  function canvasPoint(e: React.MouseEvent<HTMLCanvasElement>): { x: number; y: number } {
    const rect = e.currentTarget.getBoundingClientRect();
    const scaleX = e.currentTarget.width / rect.width;
    const scaleY = e.currentTarget.height / rect.height;
    return {
      x: (e.clientX - rect.left) * scaleX,
      y: (e.clientY - rect.top) * scaleY,
    };
  }

  function hitTestBlock(px: number, py: number, scale: number): number | null {
    // Check currently selected block first for intuitive dragging
    const order: number[] = [];
    if (selectedIdx >= 0 && selectedIdx < template.blocks.length) {
      order.push(selectedIdx);
    }
    for (let i = template.blocks.length - 1; i >= 0; i -= 1) {
      if (i !== selectedIdx) order.push(i);
    }
    for (const idx of order) {
      const bounds = computeBlockBounds(template.blocks[idx], scale);
      if (
        bounds &&
        px >= bounds.minX &&
        px <= bounds.maxX &&
        py >= bounds.minY &&
        py <= bounds.maxY
      ) {
        return idx;
      }
    }
    return null;
  }

  function finalizeMove(currentMove: MoveState) {
    const movedBlock = template.blocks[currentMove.blockIdx];
    if (
      movedBlock &&
      (movedBlock.origin[0] !== currentMove.origX || movedBlock.origin[1] !== currentMove.origY)
    ) {
      setPast((h) => [...h.slice(-(MAX_HISTORY - 1)), currentMove.snapshot]);
      setFuture([]);
    }
    setMoveState(null);
  }

  function handleMouseDown(e: React.MouseEvent<HTMLCanvasElement>) {
    const p = canvasPoint(e);
    const scale = getCanvasScale();
    const hitIdx = hitTestBlock(p.x, p.y, scale);

    if (hitIdx !== null) {
      const blk = template.blocks[hitIdx];
      setSelectedIdx(hitIdx);
      setMoveState({
        blockIdx: hitIdx,
        startCanvasX: p.x,
        startCanvasY: p.y,
        origX: blk.origin[0],
        origY: blk.origin[1],
        snapshot: template,
      });
    } else {
      setDragRect({ x0: p.x, y0: p.y, x1: p.x, y1: p.y });
    }
  }

  function handleMouseMove(e: React.MouseEvent<HTMLCanvasElement>) {
    const p = canvasPoint(e);
    const scale = getCanvasScale();
    setCursorPx({
      x: Math.max(0, Math.min(template.page_width, Math.round(p.x / scale))),
      y: Math.max(0, Math.min(template.page_height, Math.round(p.y / scale))),
    });

    if (moveState) {
      const dx = Math.round((p.x - moveState.startCanvasX) / scale);
      const dy = Math.round((p.y - moveState.startCanvasY) / scale);
      const nextX = Math.max(0, Math.min(template.page_width, Math.round(moveState.origX + dx)));
      const nextY = Math.max(0, Math.min(template.page_height, Math.round(moveState.origY + dy)));
      setTemplate((prev) => ({
        ...prev,
        blocks: prev.blocks.map((b, i) =>
          i === moveState.blockIdx ? { ...b, origin: [nextX, nextY] } : b
        ),
      }));
      return;
    }

    if (dragRect) {
      setDragRect((prev) => (prev ? { ...prev, x1: p.x, y1: p.y } : null));
      return;
    }

    setHoverBlockIdx(hitTestBlock(p.x, p.y, scale));
  }

  function handleMouseUp() {
    if (moveState) {
      finalizeMove(moveState);
      return;
    }

    if (!dragRect || !canvasRef.current) return;
    const w = Math.abs(dragRect.x1 - dragRect.x0);
    const h = Math.abs(dragRect.y1 - dragRect.y0);
    const scale = canvasRef.current.width / template.page_width;
    setDragRect(null);
    if (w < 20 || h < 20) return;

    const x0 = Math.min(dragRect.x0, dragRect.x1) / scale;
    const y0 = Math.min(dragRect.y0, dragRect.y1) / scale;
    const bw = w / scale;
    const bh = h / scale;

    const rows = 5;
    const options = ["A", "B", "C", "D", "E"];
    const nextNum = nextUniqueBlockNumber(template.blocks);
    const startQ = nextNum * 100 + 1;
    const bubblesGap = Math.max(16, Math.round(bw / Math.max(1, options.length - 1)));
    const labelsGap = Math.max(16, Math.round(bh / Math.max(1, rows - 1)));
    const radius = Math.max(8, Math.min(24, Math.round(Math.min(bubblesGap, labelsGap) * 0.34)));

    const newBlock: FieldBlock = {
      name: `BLOCK_${nextNum}`,
      field_type: "mcq",
      direction: "horizontal",
      origin: [Math.round(x0), Math.round(y0)],
      origin_mode: "center",
      bubble_radius: radius,
      bubbles_gap: bubblesGap,
      labels_gap: labelsGap,
      options,
      labels: [`f${startQ}..${startQ + rows - 1}`],
    };

    commitChange((prev) => ({ ...prev, blocks: [...prev.blocks, newBlock] }));
    setSelectedIdx(template.blocks.length);
  }

  async function handleUploadBackground(file: File) {
    setErrorMsg(null);
    try {
      const res = await previewUploadedDocument(file);
      setBgImageUrl(res.image_data_url);
      commitChange((prev) => ({
        ...prev,
        page_width: res.width,
        page_height: res.height,
      }));
      setStatusMsg(`${res.filename} · ${res.width}×${res.height}px`);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to decode document.");
    }
  }

  async function handleAutoDetectGrids(file: File) {
    setErrorMsg(null);
    setDetecting(true);
    try {
      const res = await autoDetectTemplateLayout(file);
      setBgImageUrl(res.image_data_url);
      commitChange(() => res.template);
      setSelectedIdx(0);
      setStatusMsg(
        `${res.blocks_count} blocks · ${res.fields_count} fields · ${res.detected_bubbles} bubbles`
      );
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Auto-detect failed.");
    } finally {
      setDetecting(false);
    }
  }

  async function handleMigrateLegacy(file: File) {
    setErrorMsg(null);
    try {
      const legacy = JSON.parse(await file.text()) as Record<string, unknown>;
      const res = await migrateLegacyTemplate(legacy, file.name.replace(/\.json$/i, ""));
      commitChange(() => res.template);
      setSelectedIdx(0);
      setStatusMsg(`Migrated ${file.name} → OMRKit v2.0`);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Migration failed.");
    }
  }

  function updateBlock(patch: Partial<FieldBlock>) {
    commitChange((prev) => ({
      ...prev,
      blocks: prev.blocks.map((b, i) => (i === selectedIdx ? { ...b, ...patch } : b)),
    }));
  }

  async function handleValidateAndApply() {
    setErrorMsg(null);
    setStatusMsg(null);
    try {
      const res = await validateTemplate(template);
      setStatusMsg(`OK · ${res.blocks_count} blocks · ${res.fields_count} fields`);
      onUseTemplate(template);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Validation failed.");
    }
  }

  function handleDownloadJson() {
    const blob = new Blob([JSON.stringify(template, null, 2)], { type: "application/json" });
    triggerBlobDownload(blob, `${template.name || "template"}.json`);
  }

  const selectedBlock = template.blocks[selectedIdx] ?? null;
  const canvasCursor = moveState
    ? "cursor-grabbing"
    : hoverBlockIdx !== null
      ? "cursor-grab"
      : "cursor-crosshair";

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
      {/* Left Interactive Drafting Canvas */}
      <section className="lg:col-span-8 paper-card overflow-hidden">
        <div className="px-4 py-3 border-b border-[var(--border-hairline)] flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold text-[var(--ink-primary)]">{t.designerTitle}</h2>
            <p className="text-xs text-[var(--ink-muted)]">{t.designerSub}</p>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <div className="inline-flex items-center border border-[var(--border-strong)] rounded-[5px] overflow-hidden bg-[var(--surface-card)]">
              <button
                type="button"
                disabled={past.length === 0}
                onClick={handleUndo}
                title={`${t.undoBtn} (Ctrl+Z)`}
                className="px-2 py-1.5 text-xs text-[var(--ink-primary)] hover:bg-[var(--surface-subtle)] disabled:opacity-35 disabled:cursor-not-allowed cursor-pointer inline-flex items-center gap-1"
              >
                <Undo2 className="w-3.5 h-3.5" />
                <span className="hidden xl:inline">{t.undoBtn}</span>
              </button>
              <button
                type="button"
                disabled={future.length === 0}
                onClick={handleRedo}
                title={`${t.redoBtn} (Ctrl+Shift+Z)`}
                className="px-2 py-1.5 text-xs text-[var(--ink-primary)] border-l border-[var(--border-hairline)] hover:bg-[var(--surface-subtle)] disabled:opacity-35 disabled:cursor-not-allowed cursor-pointer inline-flex items-center gap-1"
              >
                <Redo2 className="w-3.5 h-3.5" />
                <span className="hidden xl:inline">{t.redoBtn}</span>
              </button>
            </div>

            <button
              type="button"
              disabled={detecting}
              onClick={() => autoDetectRef.current?.click()}
              className="btn-primary text-xs"
            >
              <Crosshair className="w-3.5 h-3.5" />{" "}
              {detecting ? t.detecting : t.autoDetectGrids}
            </button>
            <input
              ref={autoDetectRef}
              type="file"
              accept="image/*,.pdf"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void handleAutoDetectGrids(f);
                e.target.value = "";
              }}
            />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="btn-secondary text-xs"
            >
              <Upload className="w-3.5 h-3.5" /> {t.blankImage}
            </button>
            <input
              ref={fileRef}
              type="file"
              accept="image/*,.pdf"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void handleUploadBackground(f);
                e.target.value = "";
              }}
            />
            <button
              type="button"
              onClick={() => legacyRef.current?.click()}
              className="btn-secondary text-xs"
              title={t.migrateV1}
            >
              <FileCode2 className="w-3.5 h-3.5" /> {t.migrateV1}
            </button>
            <input
              ref={legacyRef}
              type="file"
              accept=".json"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void handleMigrateLegacy(f);
                e.target.value = "";
              }}
            />
            <button type="button" onClick={handleDownloadJson} className="btn-secondary text-xs">
              <Download className="w-3.5 h-3.5" /> JSON
            </button>
            <button
              type="button"
              onClick={() => void handleValidateAndApply()}
              className="btn-accent text-xs"
            >
              <Check className="w-3.5 h-3.5" /> {t.activate}
            </button>
          </div>
        </div>

        {(statusMsg || errorMsg) && (
          <div
            className={`px-4 py-2 text-xs font-mono border-b border-[var(--border-hairline)] ${
              errorMsg
                ? "bg-[var(--signal-err-bg)] text-[var(--signal-err)]"
                : "bg-[var(--signal-ok-bg)] text-[var(--signal-ok)]"
            }`}
          >
            {errorMsg ?? statusMsg}
          </div>
        )}

        <div className="p-4 optical-stage flex justify-center overflow-auto max-h-[72vh]">
          <canvas
            ref={canvasRef}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={() => {
              setCursorPx(null);
              setHoverBlockIdx(null);
              if (dragRect) setDragRect(null);
              if (moveState) finalizeMove(moveState);
            }}
            className={`border border-[var(--border-strong)] bg-white max-w-full ${canvasCursor}`}
          />
        </div>

        {/* Precision Coordinate Telemetry Footer */}
        <div className="px-4 py-2 border-t border-[var(--border-hairline)] bg-[var(--surface-card)] flex flex-wrap items-center justify-between gap-2 text-[11px] font-mono text-[var(--ink-muted)]">
          <div className="flex items-center gap-3">
            <span className="text-[var(--ink-primary)] tabular-nums">
              {cursorPx ? `X:${String(cursorPx.x).padStart(4, " ")}  Y:${String(cursorPx.y).padStart(4, " ")} px` : "X:  --  Y:  -- px"}
            </span>
            <span className="text-[var(--border-strong)]">|</span>
            <span>
              {template.page_width}×{template.page_height} px
            </span>
            {selectedBlock && (
              <>
                <span className="text-[var(--border-strong)]">|</span>
                <span className="text-[var(--accent-cobalt)]">
                  {selectedBlock.name} @ ({Math.round(selectedBlock.origin[0])},{" "}
                  {Math.round(selectedBlock.origin[1])})
                </span>
              </>
            )}
          </div>
          <span className="truncate">{t.designerCanvasHint}</span>
        </div>
      </section>

      {/* Right Block Properties Inspector */}
      <aside className="lg:col-span-4 space-y-4">
        <section className="paper-card p-4 space-y-3">
          <h3 className="section-label">{t.sheetSettings}</h3>
          <div className="grid grid-cols-2 gap-2.5 text-xs">
            <label className="col-span-2 space-y-1">
              <span className="text-[var(--ink-secondary)]">{t.templateName}</span>
              <input
                type="text"
                className="workbench-input w-full font-mono"
                value={template.name}
                onChange={(e) => commitChange((p) => ({ ...p, name: e.target.value }))}
              />
            </label>
            <label className="space-y-1">
              <span className="text-[var(--ink-secondary)]">{t.widthPx}</span>
              <input
                type="number"
                className="workbench-input w-full font-mono"
                value={template.page_width}
                onChange={(e) =>
                  commitChange((p) => ({ ...p, page_width: Number(e.target.value) || 100 }))
                }
              />
            </label>
            <label className="space-y-1">
              <span className="text-[var(--ink-secondary)]">{t.heightPx}</span>
              <input
                type="number"
                className="workbench-input w-full font-mono"
                value={template.page_height}
                onChange={(e) =>
                  commitChange((p) => ({ ...p, page_height: Number(e.target.value) || 100 }))
                }
              />
            </label>
            <label className="col-span-2 space-y-1">
              <span className="text-[var(--ink-secondary)]">{t.registrationMode}</span>
              <select
                className="workbench-input w-full"
                value={template.registration.mode}
                onChange={(e) =>
                  commitChange((p) => ({
                    ...p,
                    registration: {
                      ...p.registration,
                      mode: e.target.value as RegistrationMode,
                    },
                  }))
                }
              >
                <option value="aruco">ArUco (0/90/180/270° + 3-corner recovery)</option>
                <option value="markers">Concentric / Custom Corner Markers</option>
                <option value="page_quad">Page Boundary Quad</option>
                <option value="homography">ORB Feature Homography</option>
                <option value="none">Direct / Flatbed (None)</option>
              </select>
            </label>
          </div>
        </section>

        <section className="paper-card p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="section-label">
              {t.fieldBlocks} ({template.blocks.length})
            </h3>
            <button
              type="button"
              onClick={() => {
                const idx = nextUniqueBlockNumber(template.blocks);
                const b: FieldBlock = {
                  name: `BLOCK_${idx}`,
                  field_type: "mcq",
                  direction: "horizontal",
                  origin: [200, 200],
                  origin_mode: "center",
                  bubble_radius: 15,
                  bubbles_gap: 45,
                  labels_gap: 48,
                  options: ["A", "B", "C", "D", "E"],
                  labels: [`b${idx}_1..5`],
                };
                commitChange((p) => ({ ...p, blocks: [...p.blocks, b] }));
                setSelectedIdx(template.blocks.length);
              }}
              className="text-xs font-mono font-medium text-[var(--accent-cobalt)] hover:underline inline-flex items-center gap-1 cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" /> {t.addBlock}
            </button>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {template.blocks.map((b, i) => (
              <button
                key={`${b.name}-${i}`}
                type="button"
                onClick={() => setSelectedIdx(i)}
                className={`px-2 py-1 rounded-[4px] text-xs font-mono border cursor-pointer transition-colors ${
                  i === selectedIdx
                    ? "bg-[var(--ink-primary)] text-white border-[var(--ink-primary)]"
                    : "bg-white text-[var(--ink-primary)] border-[var(--border-strong)] hover:bg-[var(--surface-subtle)]"
                }`}
              >
                {b.name}
              </button>
            ))}
          </div>

          {selectedBlock && (
            <div className="grid grid-cols-2 gap-2.5 text-xs pt-2.5 border-t border-[var(--border-hairline)]">
              <label className="col-span-2 space-y-1">
                <span className="text-[var(--ink-secondary)]">{t.blockName}</span>
                <input
                  type="text"
                  className="workbench-input w-full font-mono"
                  value={selectedBlock.name}
                  onChange={(e) => updateBlock({ name: e.target.value })}
                />
              </label>
              <label className="space-y-1">
                <span className="text-[var(--ink-secondary)]">Origin X</span>
                <input
                  type="number"
                  className="workbench-input w-full font-mono"
                  value={Math.round(selectedBlock.origin[0])}
                  onChange={(e) =>
                    updateBlock({ origin: [Number(e.target.value), selectedBlock.origin[1]] })
                  }
                />
              </label>
              <label className="space-y-1">
                <span className="text-[var(--ink-secondary)]">Origin Y</span>
                <input
                  type="number"
                  className="workbench-input w-full font-mono"
                  value={Math.round(selectedBlock.origin[1])}
                  onChange={(e) =>
                    updateBlock({ origin: [selectedBlock.origin[0], Number(e.target.value)] })
                  }
                />
              </label>
              <label className="space-y-1">
                <span className="text-[var(--ink-secondary)]">{t.optionsGap}</span>
                <input
                  type="number"
                  step="0.5"
                  className="workbench-input w-full font-mono"
                  value={selectedBlock.bubbles_gap}
                  onChange={(e) => updateBlock({ bubbles_gap: Number(e.target.value) || 10 })}
                />
              </label>
              <label className="space-y-1">
                <span className="text-[var(--ink-secondary)]">{t.fieldsGap}</span>
                <input
                  type="number"
                  step="0.5"
                  className="workbench-input w-full font-mono"
                  value={selectedBlock.labels_gap}
                  onChange={(e) => updateBlock({ labels_gap: Number(e.target.value) || 10 })}
                />
              </label>
              <label className="space-y-1">
                <span className="text-[var(--ink-secondary)]">{t.bubbleRadius}</span>
                <input
                  type="number"
                  step="0.5"
                  className="workbench-input w-full font-mono"
                  value={selectedBlock.bubble_radius}
                  onChange={(e) => updateBlock({ bubble_radius: Number(e.target.value) || 6 })}
                />
              </label>
              <label className="space-y-1">
                <span className="text-[var(--ink-secondary)]">{t.direction}</span>
                <select
                  className="workbench-input w-full"
                  value={selectedBlock.direction}
                  onChange={(e) =>
                    updateBlock({ direction: e.target.value as "horizontal" | "vertical" })
                  }
                >
                  <option value="horizontal">Horizontal (MCQ)</option>
                  <option value="vertical">Vertical (ID Grid)</option>
                </select>
              </label>
              <label className="col-span-2 space-y-1">
                <span className="text-[var(--ink-secondary)]">{t.optionsLabel}</span>
                <input
                  type="text"
                  className="workbench-input w-full font-mono"
                  value={optionsDraft}
                  onChange={(e) => {
                    const raw = e.target.value;
                    setOptionsDraft(raw);
                    const parsed = raw
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean);
                    if (parsed.length > 0) {
                      updateBlock({ options: parsed });
                    }
                  }}
                  onBlur={() => setOptionsDraft(selectedBlock.options.join(", "))}
                />
              </label>
              <label className="col-span-2 space-y-1">
                <span className="text-[var(--ink-secondary)]">{t.labelsRangeLabel}</span>
                <input
                  type="text"
                  className="workbench-input w-full font-mono"
                  value={labelsDraft}
                  onChange={(e) => {
                    const raw = e.target.value;
                    setLabelsDraft(raw);
                    const parsed = raw
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean);
                    if (parsed.length > 0) {
                      updateBlock({ labels: parsed });
                    }
                  }}
                  onBlur={() => setLabelsDraft(selectedBlock.labels.join(", "))}
                />
              </label>

              {template.blocks.length > 1 && (
                <button
                  type="button"
                  onClick={() => {
                    commitChange((p) => ({
                      ...p,
                      blocks: p.blocks.filter((_, idx) => idx !== selectedIdx),
                    }));
                    setSelectedIdx(Math.max(0, selectedIdx - 1));
                  }}
                  className="col-span-2 btn-secondary justify-center text-[var(--signal-err)] text-xs"
                >
                  <Trash2 className="w-3.5 h-3.5" /> {t.removeBlock}
                </button>
              )}
            </div>
          )}
        </section>
      </aside>
    </div>
  );
}

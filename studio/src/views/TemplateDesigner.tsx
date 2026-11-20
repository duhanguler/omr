import { useEffect, useRef, useState } from "react";
import { Check, Download, Plus, Trash2, Upload } from "lucide-react";
import {
  previewUploadedDocument,
  triggerBlobDownload,
  validateTemplate,
} from "../api/client";
import type { FieldBlock, RegistrationMode, Template } from "../types";

interface TemplateDesignerProps {
  activeTemplate: Template | null;
  onUseTemplate: (template: Template) => void;
}

interface DragRect {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

function expandLabelsPreview(labels: string[]): string[] {
  const out: string[] = [];
  for (const token of labels) {
    const m = /^([^.\d]+)(\d+)\.{2,3}(\d+)$/.exec(token.trim());
    if (m) {
      const [, prefix, s, e] = m;
      const start = Number(s);
      const end = Number(e);
      for (let i = start; i <= end; i += 1) {
        out.push(`${prefix}${i}`);
      }
    } else if (token.trim()) {
      out.push(token.trim());
    }
  }
  return out;
}

export function TemplateDesigner({ activeTemplate, onUseTemplate }: TemplateDesignerProps) {
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
  const [bgImageUrl, setBgImageUrl] = useState<string | null>(null);
  const [selectedIdx, setSelectedIdx] = useState<number>(0);
  const [dragRect, setDragRect] = useState<DragRect | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (activeTemplate) setTemplate(activeTemplate);
  }, [activeTemplate]);

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
  }, [template, selectedIdx, dragRect]);

  function drawCanvas() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const maxDisplayW = 760;
    const scale = Math.min(1, maxDisplayW / template.page_width);
    canvas.width = Math.round(template.page_width * scale);
    canvas.height = Math.round(template.page_height * scale);

    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    if (imgRef.current) {
      ctx.drawImage(imgRef.current, 0, 0, canvas.width, canvas.height);
    } else {
      ctx.strokeStyle = "#eceae3";
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
      const expanded = expandLabelsPreview(blk.labels);
      const ox = blk.origin[0] + (blk.origin_mode === "top_left" ? blk.bubble_radius : 0);
      const oy = blk.origin[1] + (blk.origin_mode === "top_left" ? blk.bubble_radius : 0);

      let minX = Infinity;
      let minY = Infinity;
      let maxX = -Infinity;
      let maxY = -Infinity;

      expanded.forEach((_, fi) => {
        blk.options.forEach((opt, oi) => {
          const cx = blk.direction === "horizontal" ? ox + oi * blk.bubbles_gap : ox + fi * blk.labels_gap;
          const cy = blk.direction === "horizontal" ? oy + fi * blk.labels_gap : oy + oi * blk.bubbles_gap;
          const sx = cx * scale;
          const sy = cy * scale;
          const sr = Math.max(2.5, blk.bubble_radius * scale);

          minX = Math.min(minX, sx - sr);
          minY = Math.min(minY, sy - sr);
          maxX = Math.max(maxX, sx + sr);
          maxY = Math.max(maxY, sy + sr);

          ctx.beginPath();
          ctx.arc(sx, sy, sr, 0, Math.PI * 2);
          ctx.fillStyle = isSelected ? "rgba(29, 78, 216, 0.14)" : "rgba(15, 138, 95, 0.10)";
          ctx.fill();
          ctx.lineWidth = isSelected ? 1.6 : 1.1;
          ctx.strokeStyle = isSelected ? "#1d4ed8" : "#0f8a5f";
          ctx.stroke();

          if (sr >= 6) {
            ctx.fillStyle = isSelected ? "#1e3a8a" : "#065f46";
            ctx.font = `${Math.max(8, Math.round(sr * 0.9))}px JetBrains Mono, monospace`;
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText(opt, sx, sy);
          }
        });
      });

      if (Number.isFinite(minX)) {
        ctx.strokeStyle = isSelected ? "#1d4ed8" : "rgba(15, 138, 95, 0.55)";
        ctx.lineWidth = isSelected ? 1.5 : 1;
        ctx.setLineDash(isSelected ? [] : [4, 3]);
        ctx.strokeRect(minX - 5, minY - 5, maxX - minX + 10, maxY - minY + 10);
        ctx.setLineDash([]);
        ctx.fillStyle = isSelected ? "#1d4ed8" : "#0f8a5f";
        ctx.font = "600 10px JetBrains Mono, monospace";
        ctx.textAlign = "left";
        ctx.fillText(blk.name, minX - 4, Math.max(12, minY - 9));
      }
    });

    if (dragRect) {
      const rx = Math.min(dragRect.x0, dragRect.x1);
      const ry = Math.min(dragRect.y0, dragRect.y1);
      const rw = Math.abs(dragRect.x1 - dragRect.x0);
      const rh = Math.abs(dragRect.y1 - dragRect.y0);
      ctx.fillStyle = "rgba(29, 78, 216, 0.10)";
      ctx.fillRect(rx, ry, rw, rh);
      ctx.strokeStyle = "#1d4ed8";
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

  function handleMouseUp() {
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
    const nextNum = template.blocks.length + 1;
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

    setTemplate((prev) => ({ ...prev, blocks: [...prev.blocks, newBlock] }));
    setSelectedIdx(template.blocks.length);
  }

  async function handleUploadBackground(file: File) {
    setErrorMsg(null);
    try {
      const res = await previewUploadedDocument(file);
      setBgImageUrl(res.image_data_url);
      setTemplate((prev) => ({
        ...prev,
        page_width: res.width,
        page_height: res.height,
      }));
      setStatusMsg(`Loaded ${res.filename} (${res.width}×${res.height}px)`);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to decode document.");
    }
  }

  function updateBlock(patch: Partial<FieldBlock>) {
    setTemplate((prev) => ({
      ...prev,
      blocks: prev.blocks.map((b, i) => (i === selectedIdx ? { ...b, ...patch } : b)),
    }));
  }

  async function handleValidateAndApply() {
    setErrorMsg(null);
    setStatusMsg(null);
    try {
      const res = await validateTemplate(template);
      setStatusMsg(`Valid template: ${res.blocks_count} blocks, ${res.fields_count} fields.`);
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

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
      {/* Left Interactive Canvas */}
      <section className="lg:col-span-8 paper-card overflow-hidden">
        <div className="px-4 py-3 border-b border-[var(--border-hairline)] flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold">Interactive Visual Template Designer</h2>
            <p className="text-xs text-[var(--ink-muted)]">
              Upload any blank sheet image/PDF, then click and drag on the canvas to place a new bubble grid.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="btn-secondary text-xs"
            >
              <Upload className="w-3.5 h-3.5" /> Load Blank Sheet
            </button>
            <input
              ref={fileRef}
              type="file"
              accept="image/*,.pdf"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void handleUploadBackground(f);
              }}
            />
            <button type="button" onClick={handleDownloadJson} className="btn-secondary text-xs">
              <Download className="w-3.5 h-3.5" /> Export JSON
            </button>
            <button
              type="button"
              onClick={() => void handleValidateAndApply()}
              className="btn-accent text-xs"
            >
              <Check className="w-3.5 h-3.5" /> Validate & Activate
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

        <div className="p-4 bg-[var(--surface-subtle)] flex justify-center overflow-auto max-h-[75vh]">
          <canvas
            ref={canvasRef}
            onMouseDown={(e) => {
              const p = canvasPoint(e);
              setDragRect({ x0: p.x, y0: p.y, x1: p.x, y1: p.y });
            }}
            onMouseMove={(e) => {
              if (!dragRect) return;
              const p = canvasPoint(e);
              setDragRect((prev) => (prev ? { ...prev, x1: p.x, y1: p.y } : null));
            }}
            onMouseUp={handleMouseUp}
            className="border border-[var(--border-strong)] rounded bg-white shadow-sm cursor-crosshair max-w-full"
          />
        </div>
      </section>

      {/* Right Block Properties Inspector */}
      <aside className="lg:col-span-4 space-y-4">
        <section className="paper-card p-4 space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--ink-secondary)]">
            Sheet Settings
          </h3>
          <div className="grid grid-cols-2 gap-2.5 text-xs">
            <label className="col-span-2 space-y-1">
              <span className="text-[var(--ink-secondary)]">Template Name</span>
              <input
                type="text"
                className="workbench-input w-full font-mono"
                value={template.name}
                onChange={(e) => setTemplate((p) => ({ ...p, name: e.target.value }))}
              />
            </label>
            <label className="space-y-1">
              <span className="text-[var(--ink-secondary)]">Width (px)</span>
              <input
                type="number"
                className="workbench-input w-full font-mono"
                value={template.page_width}
                onChange={(e) => setTemplate((p) => ({ ...p, page_width: Number(e.target.value) || 100 }))}
              />
            </label>
            <label className="space-y-1">
              <span className="text-[var(--ink-secondary)]">Height (px)</span>
              <input
                type="number"
                className="workbench-input w-full font-mono"
                value={template.page_height}
                onChange={(e) => setTemplate((p) => ({ ...p, page_height: Number(e.target.value) || 100 }))}
              />
            </label>
            <label className="col-span-2 space-y-1">
              <span className="text-[var(--ink-secondary)]">Registration Mode</span>
              <select
                className="workbench-input w-full"
                value={template.registration.mode}
                onChange={(e) =>
                  setTemplate((p) => ({
                    ...p,
                    registration: { ...p.registration, mode: e.target.value as RegistrationMode },
                  }))
                }
              >
                <option value="aruco">ArUco Markers (Auto 0/90/180/270°)</option>
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
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--ink-secondary)]">
              Field Blocks ({template.blocks.length})
            </h3>
            <button
              type="button"
              onClick={() => {
                const idx = template.blocks.length + 1;
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
                setTemplate((p) => ({ ...p, blocks: [...p.blocks, b] }));
                setSelectedIdx(template.blocks.length);
              }}
              className="text-xs font-medium text-[var(--accent-cobalt)] inline-flex items-center gap-1 cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" /> Add Block
            </button>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {template.blocks.map((b, i) => (
              <button
                key={`${b.name}-${i}`}
                type="button"
                onClick={() => setSelectedIdx(i)}
                className={`px-2.5 py-1 rounded text-xs font-mono border cursor-pointer ${
                  i === selectedIdx
                    ? "bg-[var(--ink-primary)] text-white border-[var(--ink-primary)]"
                    : "bg-white border-[var(--border-strong)] hover:bg-[var(--surface-subtle)]"
                }`}
              >
                {b.name}
              </button>
            ))}
          </div>

          {selectedBlock && (
            <div className="grid grid-cols-2 gap-2.5 text-xs pt-2 border-t border-[var(--border-hairline)]">
              <label className="col-span-2 space-y-1">
                <span className="text-[var(--ink-secondary)]">Block Name</span>
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
                <span className="text-[var(--ink-secondary)]">Options Gap (px)</span>
                <input
                  type="number"
                  step="0.5"
                  className="workbench-input w-full font-mono"
                  value={selectedBlock.bubbles_gap}
                  onChange={(e) => updateBlock({ bubbles_gap: Number(e.target.value) || 10 })}
                />
              </label>
              <label className="space-y-1">
                <span className="text-[var(--ink-secondary)]">Fields Gap (px)</span>
                <input
                  type="number"
                  step="0.5"
                  className="workbench-input w-full font-mono"
                  value={selectedBlock.labels_gap}
                  onChange={(e) => updateBlock({ labels_gap: Number(e.target.value) || 10 })}
                />
              </label>
              <label className="space-y-1">
                <span className="text-[var(--ink-secondary)]">Bubble Radius</span>
                <input
                  type="number"
                  step="0.5"
                  className="workbench-input w-full font-mono"
                  value={selectedBlock.bubble_radius}
                  onChange={(e) => updateBlock({ bubble_radius: Number(e.target.value) || 6 })}
                />
              </label>
              <label className="space-y-1">
                <span className="text-[var(--ink-secondary)]">Direction</span>
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
                <span className="text-[var(--ink-secondary)]">Options (comma separated)</span>
                <input
                  type="text"
                  className="workbench-input w-full font-mono"
                  value={selectedBlock.options.join(",")}
                  onChange={(e) =>
                    updateBlock({
                      options: e.target.value
                        .split(",")
                        .map((s) => s.trim())
                        .filter(Boolean),
                    })
                  }
                />
              </label>
              <label className="col-span-2 space-y-1">
                <span className="text-[var(--ink-secondary)]">Labels (supports range q1..25)</span>
                <input
                  type="text"
                  className="workbench-input w-full font-mono"
                  value={selectedBlock.labels.join(",")}
                  onChange={(e) =>
                    updateBlock({
                      labels: e.target.value
                        .split(",")
                        .map((s) => s.trim())
                        .filter(Boolean),
                    })
                  }
                />
              </label>

              {template.blocks.length > 1 && (
                <button
                  type="button"
                  onClick={() => {
                    setTemplate((p) => ({
                      ...p,
                      blocks: p.blocks.filter((_, idx) => idx !== selectedIdx),
                    }));
                    setSelectedIdx(Math.max(0, selectedIdx - 1));
                  }}
                  className="col-span-2 btn-secondary justify-center text-[var(--signal-err)] text-xs"
                >
                  <Trash2 className="w-3.5 h-3.5" /> Remove Selected Block
                </button>
              )}
            </div>
          )}
        </section>
      </aside>
    </div>
  );
}

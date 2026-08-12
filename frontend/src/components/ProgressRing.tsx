import { useEffect, useRef } from "react";

interface ProgressRingProps {
  /** 0..1 */
  percent: number;
  size?: number;
  trackColor?: string;
}

// HomeScreen hero's circular take on ProgressBar.tsx's growth-level track —
// kept as its own component rather than a ProgressBar variant because it's
// canvas-drawn (an animated conic-ish stroke isn't practical as a plain div
// arc) and because ProgressBar's other two callers (ProfileScreen's own
// growth bar, ProjectWorkspace's completion bar) are genuinely better as a
// flat bar in their own layouts — this isn't a wholesale replacement.
export function ProgressRing({ percent, size = 92, trackColor }: ProgressRingProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    canvas.style.width = `${size}px`;
    canvas.style.height = `${size}px`;
    ctx.scale(dpr, dpr);

    const cx = size / 2;
    const cy = size / 2;
    const r = size / 2 - 8;
    const track = trackColor ?? "rgba(255,255,255,0.16)";

    function frame(p: number) {
      if (!ctx) return;
      ctx.clearRect(0, 0, size, size);
      ctx.lineCap = "round";
      ctx.lineWidth = 8;

      ctx.strokeStyle = track;
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.stroke();

      const gradient = ctx.createLinearGradient(0, 0, size, size);
      gradient.addColorStop(0, "#f5b942");
      gradient.addColorStop(0.5, "#e52b24");
      gradient.addColorStop(1, "#be268f");
      ctx.strokeStyle = gradient;
      const start = -Math.PI / 2;
      const end = start + Math.PI * 2 * p;
      ctx.beginPath();
      ctx.arc(cx, cy, r, start, end);
      ctx.stroke();
    }

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      frame(percent);
      return;
    }

    let raf: number;
    let start: number | null = null;
    const duration = 900;
    function ease(t: number) {
      return 1 - Math.pow(1 - t, 3);
    }
    function step(ts: number) {
      if (start === null) start = ts;
      const p = Math.min(1, (ts - start) / duration);
      frame(ease(p) * percent);
      if (p < 1) raf = requestAnimationFrame(step);
    }
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [percent, size, trackColor]);

  return <canvas ref={canvasRef} aria-hidden="true" />;
}

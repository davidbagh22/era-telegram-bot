import { useEffect, useRef } from "react";

const animatedKeys = new Set<string>();

interface ProgressRingProps {
  /** 0..1 */
  percent: number;
  size?: number;
  trackColor?: string;
  /** Animate from 0 only once per mounted app session for this key. */
  animationKey?: string;
}

export function ProgressRing({ percent, size = 92, trackColor, animationKey = "status-orbit" }: ProgressRingProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    const ctx: CanvasRenderingContext2D = context;

    const normalized = Math.max(0, Math.min(1, percent));
    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    canvas.style.width = `${size}px`;
    canvas.style.height = `${size}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const cx = size / 2;
    const cy = size / 2;
    const r = size / 2 - 8;
    const cssTrack = getComputedStyle(document.documentElement).getPropertyValue("--era-ring-track").trim();
    const track = trackColor ?? (cssTrack || "rgba(255,255,255,0.10)");

    function frame(p: number) {
      ctx.clearRect(0, 0, size, size);
      ctx.lineCap = "round";
      ctx.lineWidth = 8;
      ctx.strokeStyle = track;
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.stroke();

      const gradient = ctx.createLinearGradient(0, 0, size, size);
      gradient.addColorStop(0, "#c5a264");
      gradient.addColorStop(0.42, "#e32636");
      gradient.addColorStop(1, "#981b28");
      ctx.strokeStyle = gradient;
      const start = -Math.PI / 2;
      const end = start + Math.PI * 2 * p;
      ctx.beginPath();
      ctx.arc(cx, cy, r, start, end);
      ctx.stroke();
    }

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const alreadyAnimated = animatedKeys.has(animationKey);
    if (reduced || alreadyAnimated) {
      frame(normalized);
      return;
    }

    animatedKeys.add(animationKey);
    let raf: number;
    let start: number | null = null;
    const duration = 820;
    function ease(t: number) {
      return 1 - Math.pow(1 - t, 3);
    }
    function step(ts: number) {
      if (start === null) start = ts;
      const p = Math.min(1, (ts - start) / duration);
      frame(ease(p) * normalized);
      if (p < 1) raf = requestAnimationFrame(step);
    }
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [animationKey, percent, size, trackColor]);

  return <canvas ref={canvasRef} aria-hidden="true" />;
}

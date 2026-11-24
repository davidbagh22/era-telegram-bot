import { useMotionPreference } from "../motion/MotionPreference";

/**
 * Shared orbital background mounted once in AppShell.
 * CSS-only motion; pauses on reduced motion / hidden tab / user preference.
 */
export function OrbitAmbient() {
  const { motionAllowed, liveBackground } = useMotionPreference();
  const paused = !motionAllowed;
  const reduced = !liveBackground;

  return (
    <div
      className="era-orbit-ambient"
      aria-hidden="true"
      data-paused={paused ? "true" : "false"}
      data-reduced={reduced ? "true" : "false"}
    >
      <div className="era-orbit-ambient__blob era-orbit-ambient__blob--a" />
      <div className="era-orbit-ambient__blob era-orbit-ambient__blob--b" />
      <div className="era-orbit-ambient__blob era-orbit-ambient__blob--c" />
      <div className="era-orbit-ambient__arc" />
    </div>
  );
}

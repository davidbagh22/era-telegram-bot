import { useMotionPreference } from "../motion/MotionPreference";
import { selectionHaptic } from "../telegram/webApp";
import { OpportunitiesIcon, EventIcon, IdeaIcon, ProjectsIcon } from "./icons";

export type OrbitNodeKey = "vector" | "events" | "ideas" | "teams";

const NODES: { key: OrbitNodeKey; label: string; hint: string; className: string }[] = [
  { key: "vector", label: "Мой вектор", hint: "Психологические тесты", className: "era-orbit-node--people" },
  { key: "events", label: "События", hint: "Афиша", className: "era-orbit-node--events" },
  { key: "ideas", label: "Идеи", hint: "Предложить", className: "era-orbit-node--ideas" },
  { key: "teams", label: "Команды", hint: "Проекты", className: "era-orbit-node--teams" },
];

interface OrbitNavigatorProps {
  onSelect: (node: OrbitNodeKey) => void;
}

/** Interactive home orbit: centre ЭРА + four stable glass nodes. */
export function OrbitNavigator({ onSelect }: OrbitNavigatorProps) {
  const { motionAllowed } = useMotionPreference();

  return (
    <div className="era-orbit-navigator" role="navigation" aria-label="Твоя орбита">
      <svg className="era-orbit-connections" viewBox="0 0 100 100" fill="none" aria-hidden="true">
        <defs><linearGradient id="orbit-light"><stop stopColor="#ffa5ea" stopOpacity=".15" /><stop offset=".5" stopColor="#ffa5ea" /><stop offset="1" stopColor="#bc2184" stopOpacity=".25" /></linearGradient></defs>
        <circle cx="50" cy="50" r="37" />
        <path d="M23 23Q50 28 50 50Q50 28 77 23M23 77Q50 72 50 50Q50 72 77 77" />
      </svg>
      <div className="era-orbit-navigator__center" aria-hidden="true">
        ЭРА
      </div>
      {NODES.map((node) => (
        <button
          key={node.key}
          type="button"
          className={`era-orbit-node ${node.className}`}
          data-paused={motionAllowed ? "false" : "true"}
          aria-label={`${node.label}: ${node.hint}`}
          onClick={() => {
            selectionHaptic();
            onSelect(node.key);
          }}
        >
          <span className="era-orbit-node__shell" aria-hidden="true" />
          <span className="era-orbit-node__icon" aria-hidden="true">
            {node.key === "vector" ? <OpportunitiesIcon /> : node.key === "events" ? <EventIcon /> : node.key === "ideas" ? <IdeaIcon /> : <ProjectsIcon />}
          </span>
          <span className="era-orbit-node__label">{node.label}</span>
          <span className="era-orbit-node__hint">{node.hint}</span>
        </button>
      ))}
    </div>
  );
}

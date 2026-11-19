import { useMotionPreference } from "../motion/MotionPreference";
import { selectionHaptic } from "../telegram/webApp";

export type OrbitNodeKey = "people" | "events" | "ideas" | "teams";

const NODES: { key: OrbitNodeKey; label: string; hint: string; className: string }[] = [
  { key: "people", label: "Люди", hint: "Свои рядом", className: "era-orbit-node--people" },
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
          <span className="era-orbit-node__label">{node.label}</span>
          <span className="era-orbit-node__hint">{node.hint}</span>
        </button>
      ))}
    </div>
  );
}

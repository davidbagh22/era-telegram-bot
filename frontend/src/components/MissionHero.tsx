import { EditorialHero } from "./EditorialHero";
import { MonoLabel } from "./MonoLabel";

interface MissionHeroProps {
  index: number | string;
  title: string;
  progressCurrent: number;
  progressTotal: number;
  deadline?: string;
  team?: string;
  owner?: string;
  nextCheckpoint?: string;
}

/** Tasks/Missions main screen shouldn't read as a checklist app (ToR §16):
 * a mission-framed hero up top, the checklist itself lives below it. */
export function MissionHero({ index, title, progressCurrent, progressTotal, deadline, team, owner, nextCheckpoint }: MissionHeroProps) {
  const percent = progressTotal <= 0 ? 0 : Math.max(0, Math.min(1, progressCurrent / progressTotal));

  return (
    <EditorialHero
      eyebrow={`MISSION / ${String(index).padStart(2, "0")}`}
      title={title}
      glow="hot"
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <span style={{ fontFamily: "var(--era-font-display)", fontSize: "1.35rem", fontWeight: 800 }}>
            {progressCurrent} / {progressTotal}
          </span>
        </div>
        <div style={{ height: "0.5rem", borderRadius: "999px", background: "var(--era-border)", overflow: "hidden" }}>
          <div style={{ height: "100%", width: `${percent * 100}%`, background: "var(--era-gradient-signal)", transition: "width 400ms ease" }} />
        </div>
      </div>

      {(deadline || team || owner || nextCheckpoint) && (
        <dl style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.85rem 1rem", margin: "0.35rem 0 0" }}>
          {deadline && <MetaItem label="Дедлайн" value={deadline} />}
          {team && <MetaItem label="Команда" value={team} />}
          {owner && <MetaItem label="Ответственный" value={owner} />}
          {nextCheckpoint && <MetaItem label="Следующий этап" value={nextCheckpoint} />}
        </dl>
      )}
    </EditorialHero>
  );
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ minWidth: 0 }}>
      <dt><MonoLabel>{label}</MonoLabel></dt>
      <dd style={{ margin: "0.2rem 0 0", fontWeight: 700, fontSize: "var(--era-text-sm)" }}>{value}</dd>
    </div>
  );
}

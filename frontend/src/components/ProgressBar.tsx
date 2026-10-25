interface ProgressBarProps {
  currentIndex: number;
  totalSteps: number;
  labels: string[];
}

export function ProgressBar({ currentIndex, totalSteps, labels }: ProgressBarProps) {
  const percent = totalSteps <= 1 ? 100 : (currentIndex / (totalSteps - 1)) * 100;
  return (
    <div>
      <div
        style={{
          height: "0.5rem",
          borderRadius: "999px",
          background: "var(--era-border)",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${percent}%`,
            background: "var(--era-gradient)",
            transition: "width 0.3s ease",
          }}
        />
      </div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginTop: "0.375rem",
          fontSize: "0.75rem",
          color: "var(--era-text-muted)",
        }}
      >
        {labels.map((label, index) => (
          <span
            key={label}
            style={{
              fontWeight: index === currentIndex ? 700 : 400,
              color: index === currentIndex ? "var(--era-text)" : "var(--era-text-muted)",
            }}
          >
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}

import { useEffect, useState } from "react";
import { fetchProjectCoverObjectUrl } from "../../api/client";

export function ProjectCover({
  coverUrl,
  compact = false,
}: {
  coverUrl: string;
  compact?: boolean;
}) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    void fetchProjectCoverObjectUrl(coverUrl)
      .then((next) => {
        if (!active) {
          URL.revokeObjectURL(next);
          return;
        }
        objectUrl = next;
        setSrc(next);
      })
      .catch(() => {
        if (active) setSrc(null);
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [coverUrl]);

  return (
    <div
      style={{
        width: "100%",
        minHeight: compact ? 120 : 180,
        borderRadius: "var(--era-radius-control)",
        background: "var(--era-surface-2)",
        display: "grid",
        placeItems: "center",
        overflow: "hidden",
      }}
    >
      {src ? (
        <img
          src={src}
          alt="Обложка проекта"
          style={{
            width: "100%",
            maxHeight: compact ? 160 : 240,
            objectFit: "contain",
            display: "block",
          }}
        />
      ) : (
        <span style={{ color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>Обложка…</span>
      )}
    </div>
  );
}

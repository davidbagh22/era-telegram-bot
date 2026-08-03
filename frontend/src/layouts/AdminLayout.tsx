import type { ReactNode } from "react";

interface AdminLayoutProps {
  children: ReactNode;
}

export function AdminLayout({ children }: AdminLayoutProps) {
  return (
    <div style={{ minHeight: "100vh" }}>
      <div
        style={{
          padding: "0.5rem 1rem",
          fontSize: "0.75rem",
          fontFamily: "var(--era-font-display)",
          letterSpacing: "0.05em",
          background: "var(--era-gradient)",
          color: "#fff",
        }}
      >
        ЭРА / ADMIN
      </div>
      {children}
    </div>
  );
}

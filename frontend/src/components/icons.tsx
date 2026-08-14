// Outline-only icon set for the bottom navigation (no emoji), per the
// platform design brief. Deliberately minimal hand-drawn SVGs so the
// design system has no icon-library dependency yet.
import type { SVGProps } from "react";

function baseProps(props: SVGProps<SVGSVGElement>): SVGProps<SVGSVGElement> {
  return {
    width: 24,
    height: 24,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    ...props,
  };
}

export function HomeIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseProps(props)}>
      <path d="M4 11.5 12 4l8 7.5" />
      <path d="M6 10v9a1 1 0 0 0 1 1h3v-5h4v5h3a1 1 0 0 0 1-1v-9" />
    </svg>
  );
}

export function ActivityIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseProps(props)}>
      <rect x="4" y="5" width="16" height="15" rx="2" />
      <path d="M4 9.5h16" />
      <path d="M8 3v3M16 3v3" />
    </svg>
  );
}

export function ProjectsIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseProps(props)}>
      <path d="M3.5 7.5A1.5 1.5 0 0 1 5 6h4l2 2h8a1.5 1.5 0 0 1 1.5 1.5v8A1.5 1.5 0 0 1 19 19H5a1.5 1.5 0 0 1-1.5-1.5Z" />
    </svg>
  );
}

export function OpportunitiesIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseProps(props)}>
      <path d="m12 4 2.36 4.79 5.29.77-3.83 3.73.9 5.27L12 16.9l-4.72 2.66.9-5.27-3.83-3.73 5.29-.77Z" />
    </svg>
  );
}

export function ProfileIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseProps(props)}>
      <circle cx="12" cy="8.5" r="3.25" />
      <path d="M5 20c1.2-3.5 4-5.25 7-5.25S17.8 16.5 19 20" />
    </svg>
  );
}

// Used by HomeScreen's hero card chips (Card gradient), not by the bottom
// navigation — kept here alongside the tab icons since it's the same
// hand-drawn stroke style and there's no reason to start a second file.
export function TaskIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseProps(props)}>
      <path d="M9 11.5 11.5 14 20 5" />
      <path d="M19 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h9.5" />
    </svg>
  );
}

export function EventIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseProps(props)}>
      <rect x="3.5" y="5" width="17" height="16" rx="2" />
      <path d="M16 3v4M8 3v4M3.5 10h17" />
    </svg>
  );
}

// ActivityScreen's action-card landing (2026-08 redesign brief section
// 16) -- Calendar/History cards, same hand-drawn stroke style.
export function CalendarIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseProps(props)}>
      <rect x="3.5" y="5" width="17" height="16" rx="2" />
      <path d="M16 3v4M8 3v4M3.5 10h17" />
      <path d="M8 14h.01M12 14h.01M16 14h.01M8 17h.01M12 17h.01" />
    </svg>
  );
}

export function HistoryIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseProps(props)}>
      <path d="M3 12a9 9 0 1 0 2.64-6.36" />
      <path d="M3 4v5h5" />
      <path d="M12 8v4l3 2" />
    </svg>
  );
}

// Auction hero card cover glyph (AuctionsPanel.tsx) — a gavel, no fake
// lot photo, same hand-drawn stroke style as the rest of this file.
export function AuctionIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseProps(props)}>
      <path d="m14.5 4.5 5 5-2 2-5-5Z" />
      <path d="m9 10 5 5-6 6-5-5Z" />
      <path d="M4 21h8" />
      <path d="m11.5 7 2-2M16.5 12l2-2" />
    </svg>
  );
}

// AdminBottomNav.tsx's 5 groups (Обзор/Люди/Работа/Связь/Аналитика) —
// same hand-drawn stroke style as the rest of this file.
export function OverviewIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseProps(props)}>
      <rect x="3.5" y="3.5" width="7.5" height="7.5" rx="1.5" />
      <rect x="13" y="3.5" width="7.5" height="7.5" rx="1.5" />
      <rect x="3.5" y="13" width="7.5" height="7.5" rx="1.5" />
      <rect x="13" y="13" width="7.5" height="7.5" rx="1.5" />
    </svg>
  );
}

export function PeopleIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseProps(props)}>
      <circle cx="9" cy="8" r="3" />
      <path d="M3.5 19c.9-3.2 3-5 5.5-5s4.6 1.8 5.5 5" />
      <circle cx="17" cy="7.5" r="2.25" />
      <path d="M15.5 10.7c1.8.3 3.1 1.7 3.7 3.8" />
    </svg>
  );
}

export function WorkIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseProps(props)}>
      <rect x="3.5" y="8" width="17" height="11" rx="2" />
      <path d="M8.5 8V6a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v2" />
      <path d="M3.5 13h17" />
    </svg>
  );
}

export function CommsIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseProps(props)}>
      <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4h13A1.5 1.5 0 0 1 20 5.5v9a1.5 1.5 0 0 1-1.5 1.5H9l-4.5 4v-4H5.5A1.5 1.5 0 0 1 4 14.5Z" />
    </svg>
  );
}

export function AnalyticsIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseProps(props)}>
      <path d="M4 20V10M11 20V4M18 20v-7" />
      <path d="M2.5 20h19" />
    </svg>
  );
}

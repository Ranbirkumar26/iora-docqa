"use client";

// Inline stroke icons (lucide-style). currentColor so they inherit text color.

type P = { className?: string };

function Svg({
  className = "h-5 w-5",
  children,
}: P & { children: React.ReactNode }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

export function IconX({ className = "h-4 w-4" }: P) {
  return (
    <Svg className={className}>
      <path d="M18 6 6 18M6 6l12 12" />
    </Svg>
  );
}

export function IconUpload({ className }: P) {
  return (
    <Svg className={className}>
      <path d="M12 16V4M6 10l6-6 6 6" />
      <path d="M4 20h16" />
    </Svg>
  );
}

export function IconTrash({ className }: P) {
  return (
    <Svg className={className}>
      <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2" />
      <path d="M19 6l-1 14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1L5 6" />
      <path d="M10 11v6M14 11v6" />
    </Svg>
  );
}

export function IconFileText({ className }: P) {
  return (
    <Svg className={className}>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" />
      <path d="M14 2v6h6M16 13H8M16 17H8" />
    </Svg>
  );
}

export function IconTable({ className }: P) {
  return (
    <Svg className={className}>
      <rect x="3" y="5" width="18" height="14" rx="1.5" />
      <path d="M3 10h18M9 5v14" />
    </Svg>
  );
}

export function IconGrid({ className }: P) {
  return (
    <Svg className={className}>
      <rect x="3" y="5" width="18" height="14" rx="1.5" />
      <path d="M3 10h18M3 15h18M9 5v14M15 5v14" />
    </Svg>
  );
}

export function IconChat({ className }: P) {
  return (
    <Svg className={className}>
      <path d="M21 11.5a8.4 8.4 0 0 1-8.5 8.4 8.5 8.5 0 0 1-3.6-.8L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8A8.5 8.5 0 0 1 12.5 3a8.4 8.4 0 0 1 8.5 8.5z" />
    </Svg>
  );
}

export function IconSearch({ className }: P) {
  return (
    <Svg className={className}>
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
    </Svg>
  );
}

export function IconEye({ className }: P) {
  return (
    <Svg className={className}>
      <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z" />
      <circle cx="12" cy="12" r="3" />
    </Svg>
  );
}

export function IconEyeOff({ className }: P) {
  return (
    <Svg className={className}>
      <path d="M3 3l18 18" />
      <path d="M10.6 10.6A3 3 0 0 0 13.4 13.4" />
      <path d="M9.9 5.3A10.5 10.5 0 0 1 12 5c6.5 0 10 7 10 7a18.5 18.5 0 0 1-3.2 4.1" />
      <path d="M6.6 6.9C3.7 8.8 2 12 2 12s3.5 7 10 7a10 10 0 0 0 4.1-.9" />
    </Svg>
  );
}

export function IconSun({ className }: P) {
  return (
    <Svg className={className}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </Svg>
  );
}

export function IconMoon({ className }: P) {
  return (
    <Svg className={className}>
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </Svg>
  );
}

export function IconCopy({ className }: P) {
  return (
    <Svg className={className}>
      <rect x="9" y="9" width="12" height="12" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </Svg>
  );
}

export function IconCheck({ className }: P) {
  return (
    <Svg className={className}>
      <path d="M20 6 9 17l-5-5" />
    </Svg>
  );
}

export function IconDownload({ className }: P) {
  return (
    <Svg className={className}>
      <path d="M12 4v12M6 10l6 6 6-6" />
      <path d="M4 20h16" />
    </Svg>
  );
}

export function IconClipboard({ className }: P) {
  return (
    <Svg className={className}>
      <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
      <rect x="9" y="2" width="6" height="4" rx="1" />
      <path d="M9 12h6M9 16h4" />
    </Svg>
  );
}

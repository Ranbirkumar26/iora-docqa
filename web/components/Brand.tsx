"use client";

// iORA brand: serif wordmark with the lilac eight-petal flower dotting the i.

export function Flower({ className = "h-4 w-4" }: { className?: string }) {
  const petals = Array.from({ length: 8 }, (_, i) => i * 45);
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <g>
        {petals.map((deg) => (
          <ellipse
            key={deg}
            cx="12"
            cy="6.2"
            rx="2.5"
            ry="5.4"
            fill="#C39BD3"
            transform={`rotate(${deg} 12 12)`}
          />
        ))}
        <circle cx="12" cy="12" r="2.6" fill="#7E57A8" />
      </g>
    </svg>
  );
}

export function Wordmark({
  className = "text-2xl",
}: {
  className?: string;
}) {
  return (
    <span
      className={`font-brand relative inline-block font-medium leading-none tracking-tight ${className}`}
      aria-label="iORA"
    >
      <Flower className="absolute -top-[0.30em] left-[0.01em] h-[0.42em] w-[0.42em]" />
      <span aria-hidden="true">&#305;ORA</span>
    </span>
  );
}

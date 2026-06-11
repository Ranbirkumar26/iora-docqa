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
      className={`font-brand inline-block font-medium leading-none tracking-tight ${className}`}
      aria-label="iORA"
    >
      {/* the dotless i gets its own box so the flower self-centers on the stem */}
      <span aria-hidden="true" className="relative inline-block">
        <Flower className="absolute -top-[0.08em] left-1/2 h-[0.38em] w-[0.38em] -translate-x-1/2" />
        &#305;
      </span>
      <span aria-hidden="true">ORA</span>
    </span>
  );
}

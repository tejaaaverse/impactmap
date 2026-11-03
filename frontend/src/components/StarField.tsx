import { useMemo } from "react";

function seeded(seed: number): () => number {
  let state = seed % 2147483647;
  if (state <= 0) state += 2147483646;
  return () => {
    state = (state * 16807) % 2147483647;
    return (state - 1) / 2147483646;
  };
}

interface Star {
  id: number;
  left: number;
  top: number;
  size: number;
  duration: number;
  delay: number;
  opacity: number;
}

/** Fixed, non-interactive starfield + occasional shooting star. */
export function StarField() {
  const stars = useMemo<Star[]>(() => {
    const random = seeded(20261102);
    return Array.from({ length: 84 }, (_, id) => ({
      id,
      left: random() * 100,
      top: random() * 100,
      size: random() > 0.86 ? 3 : random() > 0.55 ? 2 : 1,
      duration: 2.6 + random() * 5.4,
      delay: random() * 6,
      opacity: 0.25 + random() * 0.65,
    }));
  }, []);

  return (
    <div className="starfield" aria-hidden="true" data-mascot-avoid>
      {stars.map((star) => (
        <span
          key={star.id}
          className="star"
          style={{
            left: `${star.left}%`,
            top: `${star.top}%`,
            width: star.size,
            height: star.size,
            opacity: star.opacity,
            ["--twinkle-duration" as string]: `${star.duration}s`,
            ["--twinkle-delay" as string]: `${star.delay}s`,
          }}
        />
      ))}
      <span
        className="shooting-star"
        style={{ top: "16%", left: "-8%", animationDelay: "3.5s" }}
      />
      <span
        className="shooting-star"
        style={{ top: "48%", left: "-18%", animationDelay: "11s" }}
      />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_10%,transparent_0%,rgba(16,8,18,0.62)_100%)]" />
    </div>
  );
}

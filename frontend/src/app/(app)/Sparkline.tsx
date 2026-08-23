import type { HealthTrend } from "@/lib/api/types";

// A dependency-free sparkline. The overview shows four of these over at most a
// month of daily values, which is well inside what plain SVG handles - the
// charting library the deep-dive pages need arrives with them in H5.

type Point = HealthTrend["points"][number];

const WIDTH = 320;
const HEIGHT = 48;

/**
 * Builds a path from [index, value] pairs.
 *
 * The index is carried explicitly rather than inferred from position, because
 * the moving-average series is shorter than the raw one - it is null until its
 * window fills. Re-deriving x from its own array would stretch a 24-point
 * average across the same width as a 30-point series and misalign the two
 * lines by six days.
 */
function path(pairs: [number, number][], total: number, min: number, span: number): string {
  return pairs
    .map(([index, value], position) => {
      const x = total === 1 ? WIDTH / 2 : (index / (total - 1)) * WIDTH;
      const y = HEIGHT - ((value - min) / span) * HEIGHT;
      return `${position === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

export function Sparkline({ points }: { points: Point[] }) {
  if (points.length === 0) return null;

  const values = points.map((p) => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  // A flat series would divide by zero and collapse onto the top edge.
  const span = max - min || 1;

  const raw: [number, number][] = values.map((value, index) => [index, value]);
  const averages: [number, number][] = points.flatMap((point, index) =>
    point.average === null || point.average === undefined
      ? []
      : [[index, point.average] as [number, number]],
  );

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      className="h-12 w-full"
      preserveAspectRatio="none"
      role="img"
      aria-label={`${points.length} daily values ranging from ${min} to ${max}`}
    >
      <path
        d={path(raw, points.length, min, span)}
        fill="none"
        stroke="currentColor"
        strokeWidth={1}
        className="text-slate-300 dark:text-slate-600"
        vectorEffect="non-scaling-stroke"
      />
      {averages.length > 1 && (
        <path
          d={path(averages, points.length, min, span)}
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          className="text-slate-900 dark:text-slate-100"
          vectorEffect="non-scaling-stroke"
        />
      )}
    </svg>
  );
}

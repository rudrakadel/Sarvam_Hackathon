/**
 * SeverityDonut — Recharts donut summarising contradictions by severity.
 *
 * Renders a compact donut with a centred total + a colour legend on the
 * right. Honors prefers-reduced-motion by disabling the entry animation.
 */

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { useReducedMotion } from "@/hooks/useReducedMotion";

interface SeverityDonutProps {
  by_severity: Record<string, number> | undefined;
  total: number;
}

const SLICE_COLORS: Record<string, string> = {
  CRITICAL: "#DC2626",   // red-600
  HIGH:     "#EA580C",   // orange-600
  MEDIUM:   "#D97706",   // amber-600
  LOW:      "#2563EB",   // blue-600
};

const SLICE_LABELS: Record<string, string> = {
  CRITICAL: "Critical",
  HIGH:     "High",
  MEDIUM:   "Medium",
  LOW:      "Low",
};

const SLICE_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const;

export function SeverityDonut({ by_severity, total }: SeverityDonutProps) {
  const reduce = useReducedMotion();

  // Build chart data in CRITICAL → LOW order so the colour ramp reads correctly.
  const data = SLICE_ORDER
    .map((k) => ({ name: k, value: by_severity?.[k] ?? 0, fill: SLICE_COLORS[k] }))
    .filter((d) => d.value > 0);

  if (data.length === 0) {
    return (
      <div className="flex items-center gap-3 text-sm text-gray-400 dark:text-gray-500">
        <div className="w-20 h-20 rounded-full border-4 border-dashed border-gray-200 dark:border-navy-700" />
        <span>No contradictions to chart yet</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-5">
      {/* Donut */}
      <div className="relative w-28 h-28 flex-shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              innerRadius="62%"
              outerRadius="100%"
              startAngle={90}
              endAngle={-270}
              paddingAngle={2}
              stroke="none"
              isAnimationActive={!reduce}
              animationDuration={reduce ? 0 : 700}
            >
              {data.map((entry) => (
                <Cell key={entry.name} fill={entry.fill} />
              ))}
            </Pie>
            <Tooltip
              formatter={(value: number, name: string) => [
                `${value}`,
                SLICE_LABELS[name] ?? name,
              ]}
              contentStyle={{
                background: "rgba(11,20,55,0.92)",
                border: "none",
                borderRadius: 8,
                fontSize: 12,
                color: "white",
              }}
              cursor={{ fill: "transparent" }}
            />
          </PieChart>
        </ResponsiveContainer>
        {/* Centre label */}
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <span className="text-2xl font-bold text-gray-900 dark:text-gray-100 leading-none">{total}</span>
          <span className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400 mt-0.5">total</span>
        </div>
      </div>

      {/* Legend */}
      <ul className="flex flex-col gap-1.5 text-xs">
        {data.map((d) => (
          <li key={d.name} className="flex items-center gap-2">
            <span
              className="w-2.5 h-2.5 rounded-full flex-shrink-0"
              style={{ background: d.fill }}
            />
            <span className="font-medium text-gray-700 dark:text-gray-200 min-w-[3.5rem]">
              {SLICE_LABELS[d.name] ?? d.name}
            </span>
            <span className="text-gray-500 dark:text-gray-400 tabular-nums">{d.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

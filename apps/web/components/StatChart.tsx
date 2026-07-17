"use client";

// Client component for Recharts only. Receives data via props from a server component;
// it never touches the database.
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export function StatChart({ data }: { data: { date: string; cum: number }[] }) {
  if (!data.length) return <p className="text-sm text-gray-500">No games yet.</p>;
  const latest = data[data.length - 1];
  const low = Math.min(...data.map((point) => point.cum));
  const high = Math.max(...data.map((point) => point.cum));
  return (
    <div>
      <p className="sr-only">
        Cumulative point differential after {data.length} games is {latest.cum}. Range {low} to {high}.
      </p>
      <div aria-hidden="true" className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={24} />
            <YAxis tick={{ fontSize: 11 }} width={36} />
            <ReferenceLine y={0} stroke="#999" />
            <Tooltip />
            <Line type="monotone" dataKey="cum" stroke="#111" dot={false} strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

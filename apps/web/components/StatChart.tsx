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
  return (
    <div className="h-64 w-full">
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
  );
}

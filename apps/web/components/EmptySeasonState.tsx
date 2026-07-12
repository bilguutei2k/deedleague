export function EmptySeasonState() {
  return (
    <div role="status" className="py-12 text-center">
      <h1 className="text-xl font-semibold">No season data is available</h1>
      <p className="mt-2 text-sm text-gray-600">
        The analytics database has not been initialized for a supported season.
      </p>
    </div>
  );
}

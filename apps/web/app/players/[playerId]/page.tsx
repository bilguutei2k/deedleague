type PlayerPageProps = {
  params: Promise<{
    playerId: string;
  }>;
};

export default async function PlayerPage({ params }: PlayerPageProps) {
  const { playerId } = await params;

  return <h1>Player {playerId}</h1>;
}

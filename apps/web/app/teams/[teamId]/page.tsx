type TeamPageProps = {
  params: Promise<{
    teamId: string;
  }>;
};

export default async function TeamPage({ params }: TeamPageProps) {
  const { teamId } = await params;

  return <h1>Team {teamId}</h1>;
}

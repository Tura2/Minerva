import TicketClient from "./_client";

type Props = { params: Promise<{ id: string }> };

export default async function ResearchTicketPage({ params }: Props) {
  const { id } = await params;
  return <TicketClient id={id} />;
}

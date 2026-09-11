import { DeviationWorkspace } from "@/components/operations/DeviationWorkspace";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <DeviationWorkspace id={id} />;
}

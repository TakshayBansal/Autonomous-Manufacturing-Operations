import { DeviationWorkspace } from "@/components/operations/DeviationWorkspace";
export default async function Page({ params }: { params: Promise<{ deviationId: string }> }) { const { deviationId } = await params; return <DeviationWorkspace id={deviationId}/>; }

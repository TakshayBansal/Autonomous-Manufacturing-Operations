import { LineWorkspace } from "@/components/operations/LineWorkspace";
export default async function Page({ params }: { params: Promise<{ lineId: string }> }) { const { lineId } = await params; return <LineWorkspace lineId={lineId}/>; }

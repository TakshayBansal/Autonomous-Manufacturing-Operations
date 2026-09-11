import { MaintenanceAssetWorkspace } from "@/components/operations/MaintenanceAssetWorkspace";

export default async function Page({ params }: { params: Promise<{ assetId: string }> }) {
  const { assetId } = await params;
  return <MaintenanceAssetWorkspace assetId={assetId} />;
}

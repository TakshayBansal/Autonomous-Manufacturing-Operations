import { SCMMaterialDetail } from "@/components/scm/SCMMaterialDetail";
export default async function Page({params}:{params:Promise<{materialId:string}>}){const{materialId}=await params;return <SCMMaterialDetail id={materialId}/>}


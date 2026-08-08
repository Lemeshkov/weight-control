import type {FuelQualityForm,FuelQualityItem} from "./types";

const request=async<T>(url:string,init?:RequestInit):Promise<T>=>{const response=await fetch(url,init);const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==="string"?data.detail:"Ошибка запроса лаборатории");return data;};
export const fuelQualityApi={
 list:(query:string)=>request<{items:FuelQualityItem[];total:number}>(`/api/v1/laboratory/fuel-quality?${query}`),
 calculate:(body:Record<string,string>)=>request<Record<string,string>>("/api/v1/laboratory/fuel-quality/calculate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}),
 create:(body:FuelQualityForm)=>request<FuelQualityItem>("/api/v1/laboratory/fuel-quality",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}),
 update:(id:number,body:FuelQualityForm,updatedAt:string)=>request<FuelQualityItem>(`/api/v1/laboratory/fuel-quality/${id}`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({...body,expected_updated_at:updatedAt})}),
 complete:(id:number)=>request<FuelQualityItem>(`/api/v1/laboratory/fuel-quality/${id}/complete`,{method:"POST"}),
 archive:(id:number)=>request<FuelQualityItem>(`/api/v1/laboratory/fuel-quality/${id}/archive`,{method:"POST"}),
 exportUrl:(year:number,month:number)=>`/api/v1/laboratory/fuel-quality/export.xlsx?year=${year}&month=${month}`,
};

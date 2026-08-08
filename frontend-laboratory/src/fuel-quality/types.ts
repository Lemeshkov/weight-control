export type FuelQualityStatus="DRAFT"|"COMPLETED"|"ARCHIVED";
export type FuelQualityForm=Record<string,string>;
export type FuelQualityItem={id:number;sample_date:string;sample_name:string;calorimeter:string;status:FuelQualityStatus;updated_at:string;wr_percent:string;wa_percent:string;aa_percent:string;sa_percent:string;va_percent:string;calculated:Record<string,string>};

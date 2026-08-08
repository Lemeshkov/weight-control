export type FuelQualityStatus="DRAFT"|"COMPLETED"|"ARCHIVED";
export type FuelQualityForm=Record<string,string>;
export type FuelQualitySource="MANUAL"|"LEGACY_EXCEL";
export type FuelQualityItem={id:number;sample_date:string;sample_name:string;calorimeter:string|null;status:FuelQualityStatus;source:FuelQualitySource;source_file:string|null;source_sheet:string|null;updated_at:string;wr_percent:string;wa_percent:string;aa_percent:string;sa_percent:string;va_percent:string;calculated:Record<string,string>};

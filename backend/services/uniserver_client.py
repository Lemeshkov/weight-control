
# # uniserver_client = UniServerClient()
# import httpx
# from typing import Dict, Optional, List
# from datetime import datetime
# import logging
# from config import settings

# logger = logging.getLogger(__name__)

# class UniServerClient:
#     def __init__(self):
#         self.base_url = settings.UNISERVER_URL
#         self.auth_params = {
#             "auth_user": settings.UNISERVER_USER,
#             "auth_password": settings.UNISERVER_PASSWORD
#         }
    
#     async def get_scale_params(self) -> Optional[Dict]:
#         """Получить параметры весов"""
#         try:
#             async with httpx.AsyncClient(timeout=settings.UNISERVER_TIMEOUT) as client:
#                 url = f"{self.base_url}/core/plugins/AutoScale1/Parameters"
#                 response = await client.get(url, params=self.auth_params)
#                 response.raise_for_status()
#                 data = response.json()
                
#                 logger.info(f"✅ Successfully fetched scale data: {data.get('StateName')}")
#                 return data
                
#         except httpx.TimeoutException:
#             logger.error("❌ UniServer API timeout")
#             return None
#         except httpx.HTTPStatusError as e:
#             logger.error(f"❌ UniServer HTTP error: {e}")
#             return None
#         except Exception as e:
#             logger.error(f"❌ UniServer error: {e}")
#             return None
    
#     def parse_weighing_result(self, data: Dict) -> Dict:
#         """Извлечь ключевую информацию из ответа UniServer"""
#         # ✅ Данные могут быть как в корне, так и в WeighingResult
#         weighing = data.get("WeighingResult", {})
        
#         # ✅ Берем данные из WeighingResult если есть, иначе из корня
#         plate_number = weighing.get("FULL_NUMB_TS") or data.get("FULL_NUMB_TS", "")
#         weight = weighing.get("MASSA") or data.get("Massa", 0)
#         weight_type = weighing.get("TypMassaCaption") or data.get("TypMassaCaption", "")
#         weight_type_code = weighing.get("TypMassa") or data.get("TypMassa", "")
#         doc_id = weighing.get("DocID") or data.get("DocID", "")
        
#         # ✅ Состояние весов берем из корня
#         state = data.get("StateName", "Unknown")
#         state_desc = data.get("StState", "")
#         is_stable = data.get("Stabil", False)
        
#         result = {
#             "doc_id": doc_id,
#             "plate_number": plate_number,
#             "weight": float(weight) if weight else 0,
#             "weight_type": weight_type,  # "БРУТТО" или "ТАРА"
#             "weight_type_code": weight_type_code,  # "BRUTTO" или "TARE"
#             "state": state,
#             "state_desc": state_desc,
#             "is_stable": is_stable,
#             "weighing_time": weighing.get("Weighing_DateTime") or data.get("Weighing_DateTime"),
#             "start_time": weighing.get("WeighingStart_DateTime") or data.get("WeighingStart_DateTime"),
#             "stop_time": weighing.get("WeighingStop_DateTime") or data.get("WeighingStop_DateTime"),
#             "brutto": weighing.get("BRUTTO") or data.get("BRUTTO", 0),
#             "tare": weighing.get("TARA") or data.get("TARA", 0),
#             "netto": weighing.get("NETTO") or data.get("NETTO", 0),
#             "driver_name": weighing.get("TruckDriver") or data.get("TruckDriver"),
#             "carrier_name": weighing.get("CARRIER_NAME") or data.get("CARRIER_NAME"),
#             "full_response": data
#         }
        
#         logger.info(f" Parsed: type={result['weight_type']}, weight={result['weight']}кг, plate={result['plate_number']}, stable={result['is_stable']}")
        
#         return result
    
#     async def get_current_weighting(self) -> Optional[Dict]:
#         """Получить текущее взвешивание"""
#         data = await self.get_scale_params()
#         if data:
#             return self.parse_weighing_result(data)
#         return None
    
#     async def get_history(self, date: str) -> Optional[List[Dict]]:
#         """
#         Получить историю взвешиваний из UniServer за день
#         """
#         try:
#             params = {
#                 "auth_user": self.username,
#                 "auth_password": self.password,
#                 "date": date  # формат: "2026-06-18"
#             }
        
#             async with httpx.AsyncClient(timeout=10.0) as client:
#                # Нужно уточнить правильный эндпоинт у поставщика
#                # Обычно это что-то вроде /core/plugins/AutoScale1/History
#                 url = f"{self.base_url}/core/plugins/AutoScale1/History"
#                 response = await client.get(url, params=params)
            
#                 if response.status_code != 200:
#                     logger.error(f"UniServer history error: {response.status_code}")
#                     return None
            
#                 data = response.json()
            
#             # Парсим историю
#                 history = []
#                 for record in data.get("records", []):
#                     history.append({
#                         "id": record.get("DocID"),
#                         "plate_number": record.get("FULL_NUMB_TS"),
#                         "entry_time": record.get("WeighingStart_DateTime"),
#                         "exit_time": record.get("WeighingStop_DateTime"),
#                         "weight_brutto": record.get("BRUTTO"),
#                         "weight_tare": record.get("TARA"),
#                         "netto": record.get("NETTO")
#                     })
            
#                 logger.info(f"✅ Получено {len(history)} записей из UniServer")
#                 return history
            
#         except Exception as e:
#             logger.error(f"Error fetching UniServer history: {e}")
#             return None


# uniserver_client = UniServerClient()

# backend/services/uniserver_client.py
import httpx
from typing import Dict, Optional, List, Any
from datetime import datetime, timedelta
import logging
from config import settings

logger = logging.getLogger(__name__)


class UniServerClient:
    def __init__(self):
        self.base_url = settings.UNISERVER_URL
        self.username = settings.UNISERVER_USER
        self.password = settings.UNISERVER_PASSWORD
        self.auth_params = {
            "auth_user": self.username,
            "auth_password": self.password
        }
    
    async def _send_command(self, name: str, value: dict = None) -> Optional[Any]:
        """Универсальный метод для отправки команд в UniServer"""
        try:
            params = {**self.auth_params, "Name": name}
            if value:
                params["Value"] = value
            
            async with httpx.AsyncClient(timeout=settings.UNISERVER_TIMEOUT) as client:
                url = f"{self.base_url}/core/SendMsg"
                response = await client.get(url, params=params)
                response.raise_for_status()
                
                if response.headers.get("content-type") == "application/json":
                    return response.json()
                else:
                    return response.text
                
        except httpx.TimeoutException:
            logger.error(f"❌ UniServer timeout: {name}")
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ UniServer HTTP error: {name} - {e}")
            return None
        except Exception as e:
            logger.error(f"❌ UniServer error: {name} - {e}")
            return None
    
    async def get_scale_params(self) -> Optional[Dict]:
        """Получить параметры весов"""
        try:
            async with httpx.AsyncClient(timeout=settings.UNISERVER_TIMEOUT) as client:
                url = f"{self.base_url}/core/plugins/AutoScale1/Parameters"
                response = await client.get(url, params=self.auth_params)
                response.raise_for_status()
                data = response.json()
                
                logger.info(f"✅ Successfully fetched scale data: {data.get('StateName')}")
                return data
                
        except Exception as e:
            logger.error(f"❌ UniServer error: {e}")
            return None
    
    def parse_weighing_result(self, data: Dict) -> Dict:
        """Извлечь ключевую информацию из ответа UniServer"""
        weighing = data.get("WeighingResult", {})
        
        plate_number = weighing.get("FULL_NUMB_TS") or data.get("FULL_NUMB_TS", "")
        weight = weighing.get("MASSA") or data.get("Massa", 0)
        weight_type = weighing.get("TypMassaCaption") or data.get("TypMassaCaption", "")
        weight_type_code = weighing.get("TypMassa") or data.get("TypMassa", "")
        doc_id = weighing.get("DocID") or data.get("DocID", "")
        
        state = data.get("StateName", "Unknown")
        state_desc = data.get("StState", "")
        is_stable = data.get("Stabil", False)
        
        return {
            "doc_id": doc_id,
            "plate_number": plate_number,
            "weight": float(weight) if weight else 0,
            "weight_type": weight_type,
            "weight_type_code": weight_type_code,
            "state": state,
            "state_desc": state_desc,
            "is_stable": is_stable,
            "weighing_time": weighing.get("Weighing_DateTime") or data.get("Weighing_DateTime"),
            "start_time": weighing.get("WeighingStart_DateTime") or data.get("WeighingStart_DateTime"),
            "stop_time": weighing.get("WeighingStop_DateTime") or data.get("WeighingStop_DateTime"),
            "brutto": weighing.get("BRUTTO") or data.get("BRUTTO", 0),
            "tare": weighing.get("TARA") or data.get("TARA", 0),
            "netto": weighing.get("NETTO") or data.get("NETTO", 0),
            "driver_name": weighing.get("TruckDriver") or data.get("TruckDriver"),
            "carrier_name": weighing.get("CARRIER_NAME") or data.get("CARRIER_NAME"),
            "full_response": data
        }
    
    async def get_current_weighting(self) -> Optional[Dict]:
        """Получить текущее взвешивание"""
        data = await self.get_scale_params()
        if data:
            return self.parse_weighing_result(data)
        return None
    
    # ========== НОВЫЕ МЕТОДЫ ДЛЯ РАБОТЫ С ЖУРНАЛОМ ==========
    
    async def get_journal_records(
        self, 
        date_from: str = None, 
        date_to: str = None,
        max_rows: int = 100,
        sort_desc: bool = True
    ) -> Optional[List[Dict]]:
        """
        Получить записи из журнала взвешиваний AutoScaleJournal1 через SendMsg
        """
        try:
            import json
        
        # Формируем фильтр
            filter_dict = {}
            if date_from and date_to:
                filter_dict["DateTime_Create"] = {
                    "Range": [date_from, date_to]
                }
        
        # Формируем Value параметр как JSON строку
            value_obj = {
                "Filter": filter_dict,
                "MaxRows": max_rows,
                "SortDesc": 1 if sort_desc else 0
            }
            value_str = json.dumps(value_obj, ensure_ascii=False)
        
        # Отправляем через SendMsg
            async with httpx.AsyncClient(timeout=30.0) as client:
                url = f"{self.base_url}/core/SendMsg"
                params = {
                    **self.auth_params,
                    "Name": "AutoScaleJournal1_GetRecords",
                    "Value": value_str
                }
            
                logger.info(f"📡 Запрос к журналу через SendMsg")
                logger.info(f"   Value: {value_str}")
            
                response = await client.get(url, params=params)
            
                if response.status_code != 200:
                    logger.error(f"❌ Ошибка: {response.status_code}")
                    logger.error(f"   Ответ: {response.text}")
                    return []
            
                data = response.json()
            
                if isinstance(data, list):
                    logger.info(f"✅ Получено {len(data)} записей из журнала")
                    return data
                else:
                    logger.warning(f"⚠️ Неожидантный формат ответа: {type(data)}")
                    return []
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения журнала: {e}")
            return []


    def parse_journal_record(self, record: Dict) -> Dict:
        """Парсинг записи из журнала в единый формат"""
        return {
            "code": record.get("CODE"),
            "doc_id": record.get("DocID") or record.get("DOCID"),
            "plate_number": record.get("FULL_NUMB_TS", ""),
            "entry_time": record.get("WEIGHINGSTART_DATETIME") or record.get("WeighingStart_DateTime"),
            "exit_time": record.get("WEIGHINGSTOP_DATETIME") or record.get("WeighingStop_DateTime"),
            "weighing_time": record.get("WEIGHING_DATETIME") or record.get("Weighing_DateTime"),
            "weight_type": record.get("TYPMASSACAPTION") or record.get("TypMassaCaption"),
            "weight_type_code": record.get("TYPMASSA") or record.get("TypMassa"),
            "weight_brutto": float(record.get("MASSA", 0) or record.get("BRUTTO", 0)),
            "weight_tare": float(record.get("TARA", 0)),
            "weight_netto": float(record.get("NETTO", 0)),
            "driver_name": record.get("TruckDriver"),
            "carrier_name": record.get("CARRIER_NAME"),
            "created_at": record.get("DATETIME_CREATE"),
            "updated_at": record.get("DATETIME_UPDATE"),
            "is_deleted": record.get("DELETED", 0) == 1,
            "document_number": record.get("DOCUMENT_NUMBER"),
            "full_record": record
        }
    
    async def get_journal_stats(self) -> Optional[Dict]:
        """Получить статистику журнала"""
        try:
            async with httpx.AsyncClient(timeout=settings.UNISERVER_TIMEOUT) as client:
                url = f"{self.base_url}/core/plugins/AutoScaleJournal1/GetStats"
                response = await client.get(url, params=self.auth_params)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return None
    
    def parse_journal_record(self, record: Dict) -> Dict:
        """Парсинг записи из журнала в единый формат"""
        return {
            "code": record.get("CODE"),
            "doc_id": record.get("DocID"),
            "plate_number": record.get("FULL_NUMB_TS", ""),
            "entry_time": record.get("WeighingStart_DateTime"),
            "exit_time": record.get("WeighingStop_DateTime"),
            "weighing_time": record.get("Weighing_DateTime"),
            "weight_type": record.get("TypMassaCaption"),
            "weight_type_code": record.get("TypMassa"),
            "weight_brutto": record.get("BRUTTO", 0),
            "weight_tare": record.get("TARA", 0),
            "weight_netto": record.get("NETTO", 0),
            "driver_name": record.get("TruckDriver"),
            "carrier_name": record.get("CARRIER_NAME"),
            "created_at": record.get("DATETIME_CREATE"),
            "updated_at": record.get("DATETIME_UPDATE"),
            "is_deleted": record.get("DELETED", False)
        }


# Глобальный экземпляр
uniserver_client = UniServerClient()
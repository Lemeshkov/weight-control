# app/services/uniserver_client.py
import httpx
from typing import Dict, Optional
from datetime import datetime
import logging
from config import settings

logger = logging.getLogger(__name__)

class UniServerClient:
    def __init__(self):
        self.base_url = settings.UNISERVER_URL
        self.auth_params = {
            "auth_user": settings.UNISERVER_USER,
            "auth_password": settings.UNISERVER_PASSWORD
        }
    
    async def get_scale_params(self) -> Optional[Dict]:
        """Получить параметры весов"""
        try:
            async with httpx.AsyncClient(timeout=settings.UNISERVER_TIMEOUT) as client:
                url = f"{self.base_url}/core/plugins/AutoScale1/Parameters"
                response = await client.get(url, params=self.auth_params)
                response.raise_for_status()
                data = response.json()
                
                logger.info(f"Successfully fetched scale data: {data.get('StateName')}")
                return data
                
        except httpx.TimeoutException:
            logger.error("UniServer API timeout")
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"UniServer HTTP error: {e}")
            return None
        except Exception as e:
            logger.error(f"UniServer error: {e}")
            return None
    
    def parse_weighing_result(self, data: Dict) -> Dict:
        """Извлечь ключевую информацию из ответа UniServer"""
        weighing = data.get("WeighingResult", {})
        
        return {
            "doc_id": weighing.get("DocID"),
            "plate_number": weighing.get("FULL_NUMB_TS"),
            "weight": weighing.get("MASSA", 0),
            "weight_type": weighing.get("TypMassaCaption"),  # БРУТТО или ТАРА
            "state": data.get("StateName"),
            "state_desc": data.get("StState"),
            "is_stable": data.get("Stabil", False),
            "weighing_time": weighing.get("Weighing_DateTime"),
            "start_time": weighing.get("WeighingStart_DateTime"),
            "stop_time": weighing.get("WeighingStop_DateTime"),
            "full_response": weighing
        }
    
    async def get_current_weighting(self) -> Optional[Dict]:
        """Получить текущее взвешивание"""
        data = await self.get_scale_params()
        if data and data.get("WeighingResult"):
            return self.parse_weighing_result(data)
        return None

uniserver_client = UniServerClient()
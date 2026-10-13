"""
Cosecha de noticias RCPN vía Google News → Supabase.
Ejecutado por GitHub Actions 2x/día desde servidores de GitHub
(no bloqueados por Google News, a diferencia de Vercel).
"""
import sys
import os
import asyncio
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sources.rcpn_monitor import get_rcpn_noticias
from db.supabase_client import upsert_rcpn_noticias

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    logger.info("=== Harvest RCPN — inicio ===")
    noticias = await get_rcpn_noticias()
    logger.info(f"Noticias encontradas: {len(noticias)}")
    if noticias:
        upsert_rcpn_noticias(noticias)
        logger.info(f"Guardadas en Supabase: {len(noticias)}")
    logger.info("=== Harvest RCPN — completado ===")


if __name__ == "__main__":
    asyncio.run(main())

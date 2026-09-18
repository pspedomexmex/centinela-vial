"""
Monitoreo de cuentas X/Twitter usando la API v2 (Free tier).
Busca tweets recientes de cuentas viales por región.
"""
import httpx
import asyncio
from datetime import datetime, timedelta, timezone


TWITTER_API = "https://api.twitter.com/2/tweets/search/recent"

# Tipos de incidente para clasificar tweets
INCIDENT_PATTERNS = {
    "🚨 Accidente": ["accidente", "choque", "volcadura", "atropello"],
    "🚧 Cierre": ["cierre", "cerrado", "bloqueado", "bloqueo", "corte de circulacion"],
    "👮 Retén/Operativo": ["retén", "reten", "operativo", "revision", "revisión", "inspeccion"],
    "⚠️ Peligro": ["derrumbe", "deslizamiento", "neblina", "niebla", "granizo", "inundacion"],
    "📢 Manifestación": ["manifestacion", "manifestación", "protesta", "marcha", "paro"],
    "🔴 Tráfico": ["trafico", "tráfico", "congestion", "congestionado", "lento"],
}


def _clasificar_tweet(texto: str) -> tuple[str, str]:
    """Devuelve (emoji_tipo, nombre_tipo)."""
    texto_lower = texto.lower()
    for tipo, keywords in INCIDENT_PATTERNS.items():
        if any(k in texto_lower for k in keywords):
            emoji = tipo.split(" ")[0]
            nombre = " ".join(tipo.split(" ")[1:])
            return emoji, nombre
    return "📡", "Aviso vial"


async def search_tweets_for_region(
    region_key: str,
    cuentas: list[str],
    keywords: list[str],
    bearer_token: str,
    max_results: int = 10,
) -> list[dict]:
    if not bearer_token:
        return []

    # Construir query: (from:cuenta1 OR from:cuenta2) keywords
    from_clause = " OR ".join(f"from:{c}" for c in cuentas[:5])
    kw_clause = " OR ".join(f'"{k}"' for k in keywords[:5])
    query = f"({from_clause}) lang:es -is:retweet"

    # Solo tweets de las últimas 2 horas
    since = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")

    params = {
        "query": query,
        "max_results": max_results,
        "start_time": since,
        "tweet.fields": "created_at,text",
        "expansions": "author_id",
        "user.fields": "username",
    }

    headers = {"Authorization": f"Bearer {bearer_token}"}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(TWITTER_API, params=params, headers=headers)
            if resp.status_code == 429:
                return []  # Rate limit
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []

    tweets = []
    users = {u["id"]: u["username"] for u in data.get("includes", {}).get("users", [])}

    for tweet in data.get("data", []):
        texto = tweet.get("text", "")
        autor = users.get(tweet.get("author_id", ""), "desconocido")
        emoji, tipo = _clasificar_tweet(texto)

        tweets.append({
            "tipo": tipo,
            "emoji": emoji,
            "descripcion": texto[:280],
            "autor": f"@{autor}",
            "fecha": tweet.get("created_at", ""),
            "fuente": "X/Twitter",
            "region": region_key,
        })

    return tweets


async def get_tweets_for_regions(
    region_keys: list[str],
    region_data: dict,
    bearer_token: str,
) -> list[dict]:
    if not bearer_token:
        return []

    tasks = []
    for rk in region_keys:
        rinfo = region_data.get(rk, {})
        tasks.append(
            search_tweets_for_region(
                region_key=rk,
                cuentas=rinfo.get("cuentas_x", []),
                keywords=rinfo.get("keywords", []),
                bearer_token=bearer_token,
            )
        )

    results = await asyncio.gather(*tasks)
    combined = []
    for r in results:
        combined.extend(r)
    return combined

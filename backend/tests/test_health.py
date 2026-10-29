import httpx


async def test_health_and_ready(server: str) -> None:
    async with httpx.AsyncClient(base_url=server) as http:
        assert (await http.get("/health")).json() == {"status": "ok"}
        assert (await http.get("/ready")).status_code == 200

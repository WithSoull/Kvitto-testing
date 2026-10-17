from httpx import AsyncClient


async def test_list_tariffs(client: AsyncClient) -> None:
    response = await client.get("/tariffs")

    assert response.status_code == 200
    # Prices are integer kopecks, sorted from cheapest to most expensive.
    assert response.json() == [
        {"id": "basic", "title": "Basic", "price": 990000},
        {"id": "standard", "title": "Standard", "price": 1990000},
        {"id": "premium", "title": "Premium", "price": 2990000},
    ]

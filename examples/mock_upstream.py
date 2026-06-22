"""Stand-in for 'the customer's real API' so we can test the full A2A wrap end-to-end."""
from fastapi import FastAPI

mock_app = FastAPI(title="Mock PetStore Upstream")

ORDERS = {"ord_123": {"orderId": "ord_123", "customerId": "cust_9", "items": ["dog_food_10kg"], "status": "shipped"}}
INVENTORY = {"dog_food_10kg": 42, "cat_litter_5kg": 7}


@mock_app.get("/orders/{order_id}")
def get_order(order_id: str):
    return ORDERS.get(order_id, {"error": "not found"})


@mock_app.post("/orders")
def create_order(customerId: str, items: str):
    new_id = f"ord_{len(ORDERS) + 100}"
    ORDERS[new_id] = {"orderId": new_id, "customerId": customerId, "items": items, "status": "submitted"}
    return ORDERS[new_id]


@mock_app.get("/inventory/{sku}")
def check_inventory(sku: str):
    return {"sku": sku, "quantity": INVENTORY.get(sku, 0)}

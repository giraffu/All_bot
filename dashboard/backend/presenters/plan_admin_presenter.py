def build_order_item_payload(*, order, username: str | None, plan_name: str | None) -> dict:
    order_dict = {column.name: getattr(order, column.name) for column in order.__table__.columns}
    order_dict["username"] = username
    order_dict["plan_name"] = plan_name
    return order_dict

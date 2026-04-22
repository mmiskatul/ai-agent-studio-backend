from uuid import uuid4


def create_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"

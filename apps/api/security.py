from fastapi import Header, HTTPException

ROLE_ORDER = {"intern": 1, "lawyer": 2, "admin": 3}

def require_role(min_role: str, x_role: str | None):
    role = (x_role or "intern").lower()
    if ROLE_ORDER.get(role, 0) < ROLE_ORDER.get(min_role, 999):
        raise HTTPException(status_code=403, detail="insufficient_role")
    return role

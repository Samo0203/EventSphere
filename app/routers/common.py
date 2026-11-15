import base64
import io
import qrcode
from fastapi import HTTPException

STATUS_BY_CODE = {"SOLD_OUT": 409, "NOT_FOUND": 404, "CLASH": 409, "FORBIDDEN": 403}


def respond(reply):
    """Translate an agent reply envelope into an HTTP result."""
    perf, c = reply["performative"], reply["content"]
    if perf in ("AGREE", "INFORM", "PROPOSE"):
        return c
    if perf == "FAILURE":
        raise HTTPException(500, c.get("reason", "Agent failure"))
    raise HTTPException(STATUS_BY_CODE.get(c.get("code"), 400), c.get("reason", "Request refused"))


def qr_data_uri(text: str) -> str:
    img = qrcode.make(text)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

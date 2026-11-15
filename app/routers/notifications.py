from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Notification
from app.security import current_user

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("/mine")
def mine(db: Session = Depends(get_db), u=Depends(current_user)):
    rows = db.query(Notification).filter_by(user_id=u.id).order_by(Notification.id.desc()).limit(50).all()
    return [{"id": n.id, "title": n.title, "message": n.message, "is_read": n.is_read,
             "created_at": n.created_at.isoformat()} for n in rows]


@router.post("/read-all")
def read_all(db: Session = Depends(get_db), u=Depends(current_user)):
    db.query(Notification).filter_by(user_id=u.id, is_read=False).update({Notification.is_read: True})
    db.commit()
    return {"ok": True}

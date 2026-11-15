from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Venue
from app.schemas import VenueIn,VenueOut
from app.security import roles,current_user
router=APIRouter(prefix="/venues",tags=["Venues"])

@router.post("/",response_model=VenueOut,status_code=201)
def create(data:VenueIn,db:Session=Depends(get_db),u=Depends(roles("admin"))):
    v=Venue(**data.model_dump()); db.add(v); db.commit(); db.refresh(v); return v
@router.get("/",response_model=list[VenueOut])
def list_venues(db:Session=Depends(get_db),u=Depends(current_user)):
    return db.query(Venue).order_by(Venue.name).all()
@router.put("/{vid}",response_model=VenueOut)
def update(vid:int,data:VenueIn,db:Session=Depends(get_db),u=Depends(roles("admin"))):
    v=db.query(Venue).filter_by(id=vid).first()
    if not v: raise HTTPException(404,"Venue not found")
    for k,val in data.model_dump().items(): setattr(v,k,val)
    db.commit(); db.refresh(v); return v

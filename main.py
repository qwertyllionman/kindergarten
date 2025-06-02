import asyncio
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from starlette.middleware.cors import CORSMiddleware

import auth
from database import SessionLocal, User, Ingredient, Meal, MealIngredient, MealServing, InventoryTransaction, MonthlyReport, Alert, Role, get_db
from auth import get_current_user, router
from datetime import datetime, timedelta
import json
from celery import Celery
from typing import List, Optional
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel


class IngredientCreate(BaseModel):
    name: str
    quantity_grams: float
    minimum_quantity: float
    delivery_date: Optional[datetime] = None

class IngredientUpdate(BaseModel):
    quantity_grams: Optional[float] = None
    delivery_date: Optional[datetime] = None

class MealIngredientBase(BaseModel):
    ingredient_id: int
    quantity: float

class MealCreate(BaseModel):
    name: str
    ingredients: List[MealIngredientBase]

class MealUpdate(BaseModel):
    name: Optional[str] = None
    ingredients: Optional[List[MealIngredientBase]] = None

class ServeMealRequest(BaseModel):
    portions: int

app = FastAPI()
app.include_router(router)
celery_app = Celery('tasks', broker='redis://localhost:6379/0')
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

active_connections: List[WebSocket] = []
templates = Jinja2Templates(directory="templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)
@app.get("/register", response_class=HTMLResponse)
async def get_register(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/", response_class=HTMLResponse)
async def get_login(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/home", response_class=HTMLResponse)
async def get_home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

@app.get("/ingredients", response_class=HTMLResponse)
async def get_ingredients_page(request: Request):
    return templates.TemplateResponse("ingredients.html", {"request": request})

@app.get("/meals", response_class=HTMLResponse)
async def get_meals_page(request: Request):
    return templates.TemplateResponse("meals.html", {"request": request})

@app.get("/serve-meal", response_class=HTMLResponse)
async def get_serve_meal_page(request: Request):
    return templates.TemplateResponse("serve_meal.html", {"request": request})

@app.get("/reports", response_class=HTMLResponse)
async def get_reports_page(request: Request):
    return templates.TemplateResponse("reports.html", {"request": request})

@app.get("/servings", response_class=HTMLResponse)
async def get_servings_page(request: Request):
    return templates.TemplateResponse("servings.html", {"request": request})

@app.get("/alerts", response_class=HTMLResponse)
async def get_alerts_page(request: Request):
    return templates.TemplateResponse("alerts.html", {"request": request})

@app.get("/trigger-report", response_class=HTMLResponse)
async def get_trigger_report_page(request: Request):
    return templates.TemplateResponse("trigger_report.html", {"request": request})

@app.get("/me")
async def get_user_details(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "full_name": current_user.full_name,
        "email": current_user.email,
        "role": current_user.role
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    print(f"WebSocket client connected. Total connections: {len(active_connections)}")
    try:
        while True:
            message = await websocket.receive_text()
            print(f"Received message from client: {message}")
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        print(f"WebSocket client disconnected. Total connections: {len(active_connections)}")

async def broadcast_update(message: dict):
    json_message = json.dumps(message)
    print(f"Broadcasting message: {json_message}")
    for connection in active_connections:
        try:
            await connection.send_text(json_message)
        except Exception:
            active_connections.remove(connection)

@app.post("/ingredients/")
async def add_ingredient(ingredient: IngredientCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in [Role.ADMIN, Role.MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized: Manager or Admin access required",
        )
    delivery_date = ingredient.delivery_date if ingredient.delivery_date else datetime.now()
    db_ingredient = Ingredient(
        name=ingredient.name,
        quantity_grams=ingredient.quantity_grams,
        minimum_quantity=ingredient.minimum_quantity,
        delivery_date=delivery_date
    )
    db.add(db_ingredient)
    db.commit()
    await broadcast_update({"type": "inventory_update", "ingredient": ingredient.name, "quantity": ingredient.quantity_grams})
    return {"message": "Ingredient added"}

@app.get("/ingredients/")
async def get_ingredients(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in [Role.ADMIN, Role.MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized: Manager or Admin access required",
        )
    ingredients = db.query(Ingredient).all()
    return [{"id": ing.id, "name": ing.name, "quantity_grams": ing.quantity_grams, "minimum_quantity": ing.minimum_quantity, "delivery_date": ing.delivery_date} for ing in ingredients]

@app.get("/ingredients/{ingredient_id}")
async def get_ingredient(ingredient_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in [Role.ADMIN, Role.MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized: Manager or Admin access required",
        )
    ingredient = db.query(Ingredient).filter(Ingredient.id == ingredient_id).first()
    if not ingredient:
        raise HTTPException(status_code=404, detail="Ingredient not found")
    return {
        "id": ingredient.id,
        "name": ingredient.name,
        "quantity_grams": ingredient.quantity_grams,
        "minimum_quantity": ingredient.minimum_quantity,
        "delivery_date": ingredient.delivery_date
    }

@app.put("/ingredients/{ingredient_id}")
async def update_ingredient(ingredient_id: int, update_data: IngredientUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in [Role.ADMIN, Role.MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized: Manager or Admin access required",
        )
    ingredient = db.query(Ingredient).filter(Ingredient.id == ingredient_id).first()
    if not ingredient:
        raise HTTPException(status_code=404, detail="Ingredient not found")
    if update_data.quantity_grams is not None:
        ingredient.quantity_grams = update_data.quantity_grams
    if update_data.delivery_date is not None:
        ingredient.delivery_date = update_data.delivery_date
    ingredient.updated_at = datetime.now()
    db.commit()
    await broadcast_update({"type": "inventory_update", "ingredient": ingredient.name, "quantity": ingredient.quantity_grams})
    return {"message": "Ingredient updated"}

@app.delete("/ingredients/{ingredient_id}")
async def delete_ingredient(ingredient_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in [Role.ADMIN, Role.MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized: Manager or Admin access required",
        )
    ingredient = db.query(Ingredient).filter(Ingredient.id == ingredient_id).first()
    if not ingredient:
        raise HTTPException(status_code=404, detail="Ingredient not found")
    db.delete(ingredient)
    db.commit()
    await broadcast_update({"type": "inventory_delete", "ingredient": ingredient.name})
    return {"message": "Ingredient deleted"}

@app.post("/meals/")
async def add_meal(meal: MealCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in [Role.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized: Admin access required",
        )
    db_meal = Meal(name=meal.name)
    db.add(db_meal)
    db.flush()
    for ing in meal.ingredients:
        meal_ing = MealIngredient(meal_id=db_meal.id, ingredient_id=ing.ingredient_id, quantity=ing.quantity)
        db.add(meal_ing)
    db.commit()
    return {"message": "Meal added"}

@app.get("/meals/")
async def get_meals(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in [Role.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized: Admin access required",
        )
    meals = db.query(Meal).all()
    result = []
    for meal in meals:
        meal_data = {
            "id": meal.id,
            "name": meal.name,
            "ingredients": [
                {"ingredient_id": mi.ingredient_id, "name": mi.ingredient.name, "quantity": mi.quantity}
                for mi in meal.ingredients
            ]
        }
        result.append(meal_data)
    return result

@app.get("/meals/{meal_id}")
async def get_meal(meal_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in [Role.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized: Admin access required",
        )
    meal = db.query(Meal).filter(Meal.id == meal_id).first()
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")
    return {
        "id": meal.id,
        "name": meal.name,
        "ingredients": [
            {"ingredient_id": mi.ingredient_id, "name": mi.ingredient.name, "quantity": mi.quantity}
            for mi in meal.ingredients
        ]
    }

@app.put("/meals/{meal_id}")
async def update_meal(meal_id: int, update_data: MealUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in [Role.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized: Admin access required",
        )
    meal = db.query(Meal).filter(Meal.id == meal_id).first()
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")
    if update_data.name is not None:
        meal.name = update_data.name
    if update_data.ingredients is not None:
        db.query(MealIngredient).filter(MealIngredient.meal_id == meal_id).delete()
        for ing in update_data.ingredients:
            meal_ing = MealIngredient(meal_id=meal_id, ingredient_id=ing.ingredient_id, quantity=ing.quantity)
            db.add(meal_ing)
    meal.updated_at = datetime.now()
    db.commit()
    return {"message": "Meal updated"}

@app.delete("/meals/{meal_id}")
async def delete_meal(meal_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in [Role.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized: Admin access required",
        )
    meal = db.query(Meal).filter(Meal.id == meal_id).first()
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")
    # Delete related MealServing records first
    db.query(MealServing).filter(MealServing.meal_id == meal_id).delete()
    # Delete related MealIngredient records
    db.query(MealIngredient).filter(MealIngredient.meal_id == meal_id).delete()
    # Delete the Meal
    db.delete(meal)
    db.commit()
    return {"message": "Meal deleted"}

@app.post("/serve/{meal_id}")
async def serve_meal(meal_id: int, request: ServeMealRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    portions = request.portions
    print(f"Received request to serve meal_id={meal_id} with portions={portions}")
    if current_user.role not in [Role.ADMIN, Role.COOK]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized: Admin or Cook access required",
        )
    meal = db.query(Meal).filter(Meal.id == meal_id).first()
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")
    insufficient = []
    for meal_ing in meal.ingredients:
        required = meal_ing.quantity * portions
        if meal_ing.ingredient.quantity_grams < required:
            insufficient.append(meal_ing.ingredient.name)
    if insufficient:
        alert = Alert(ingredient_id=meal_ing.ingredient.id, alert_type="LOW_STOCK", message=f"Insufficient {', '.join(insufficient)}")
        db.add(alert)
        db.commit()
        await broadcast_update({"type": "alert", "message": alert.message})
        raise HTTPException(status_code=400, detail=f"Insufficient ingredients: {', '.join(insufficient)}")
    for meal_ing in meal.ingredients:
        required = meal_ing.quantity * portions
        meal_ing.ingredient.quantity_grams -= required
        transaction = InventoryTransaction(
            ingredient_id=meal_ing.ingredient_id,
            quantity_change_grams=-required,
            user_id=current_user.id,
            transaction_type="CONSUMPTION"
        )
        db.add(transaction)
    serving = MealServing(meal_id=meal_id, user_id=current_user.id, portions_served=portions)
    db.add(serving)
    db.commit()
    await broadcast_update({"type": "inventory_update", "meal": meal.name, "portions": portions})
    return {"message": "Meal served"}

@app.get("/portions/estimate")
async def estimate_portions(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in [Role.ADMIN, Role.MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized: Manager or Admin access required",
        )
    estimates = {}
    for meal in db.query(Meal).all():
        min_portions = float('inf')
        for meal_ing in meal.ingredients:
            portions = meal_ing.ingredient.quantity_grams / meal_ing.quantity
            min_portions = min(min_portions, portions)
        estimates[meal.name] = int(min_portions) if min_portions != float('inf') else 0
    return estimates

@app.get("/reports/monthly")
async def get_monthly_reports(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in [Role.ADMIN, Role.MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized: Manager or Admin access required",
        )
    reports = db.query(MonthlyReport).all()
    return [{"month": r.report_month, "served": r.total_portions_served, "possible": r.total_portions_possible, "discrepancy": r.discrepancy_rate} for r in reports]

@celery_app.task
def generate_monthly_report():
    with SessionLocal() as db:
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        servings = db.query(MealServing).filter(MealServing.created_at >= month_start).all()
        total_served = sum(s.portions_served for s in servings)
        total_possible = sum(estimate_portions(db)[meal.name] for meal in db.query(Meal).all()) or 1
        discrepancy = ((total_possible - total_served) / total_possible * 100) if total_possible else 0
        if discrepancy > 15:
            alert = Alert(alert_type="DISCREPANCY", message=f"Discrepancy rate {discrepancy:.2f}% exceeds 15%")
            db.add(alert)
        report = MonthlyReport(report_month=month_start, total_portions_served=total_served, total_portions_possible=total_possible, discrepancy_rate=discrepancy)
        db.add(report)
        db.commit()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(broadcast_update({"type": "report_update", "discrepancy": discrepancy}))
        loop.close()

@app.get("/api/servings")
async def get_served_meals(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        current_user = await auth.get_current_user(token, db)
        if current_user.role not in [Role.ADMIN, Role.MANAGER]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized: Manager or Admin access required",
            )
        servings = db.query(MealServing).all()
        result = []
        for s in servings:
            meal_name = s.meal.name if s.meal else "Unknown Meal"
            user_name = s.user.full_name if s.user else "Unknown User"
            result.append({
                "meal": meal_name,
                "user": user_name,
                "portions": s.portions_served,
                "time": s.created_at.isoformat() if s.created_at else None
            })
        return result
    except auth.credentials_exception as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching servings: {str(e)}"
        )

@app.get("/alerts")
async def get_alerts(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in [Role.ADMIN, Role.MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized: Manager or Admin access required",
        )
    alerts = db.query(Alert).all()
    return [{"id": a.id, "type": a.alert_type, "message": a.message, "time": a.created_at} for a in alerts]

async def check_low_stock(db: Session):
    for ing in db.query(Ingredient).all():
        if ing.quantity_grams < ing.minimum_quantity:
            alert = db.query(Alert).filter(Alert.ingredient_id == ing.id, Alert.alert_type == "LOW_STOCK").first()
            if not alert:
                message = f"{str(ing.name).strip()} below minimum {float(ing.minimum_quantity)}g"
                alert = Alert(ingredient_id=ing.id, alert_type="LOW_STOCK", message=message)
                db.add(alert)
                db.commit()
                await broadcast_update({"type": "alert", "message": message})

@app.post("/trigger-low-stock-check")
async def trigger_low_stock_check(db: Session = Depends(get_db)):
    await check_low_stock(db)
    return {"message": "Low stock check triggered"}

@app.post("/tasks/generate-report")
async def trigger_report(current_user: User = Depends(get_current_user)):
    if current_user.role not in [Role.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized: Admin access required",
        )
    generate_monthly_report.delay()
    return {"message": "Report generation scheduled"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
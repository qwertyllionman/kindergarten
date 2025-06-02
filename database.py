from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Enum
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
import enum

DATABASE_URL = "sqlite:///kindergarten_meal.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Role(enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    COOK = "cook"

class TransactionType(enum.Enum):
    DELIVERY = "delivery"
    CONSUMPTION = "consumption"

class AlertType(enum.Enum):
    LOW_STOCK = "low_stock"
    DISCREPANCY = "discrepancy"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    password = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    role = Column(Enum(Role), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    meal_servings = relationship("MealServing", back_populates="user")
    inventory_transactions = relationship("InventoryTransaction", back_populates="user")

class Ingredient(Base):
    __tablename__ = "ingredients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    quantity_grams = Column(Float, nullable=False)
    minimum_quantity = Column(Float, default=100.0)
    delivery_date = Column(DateTime, default=datetime.now)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    meal_ingredients = relationship("MealIngredient", back_populates="ingredient")
    inventory_transactions = relationship("InventoryTransaction", back_populates="ingredient")
    alerts = relationship("Alert", back_populates="ingredient")

class Meal(Base):
    __tablename__ = "meals"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    ingredients = relationship("MealIngredient", back_populates="meal")
    servings = relationship("MealServing", back_populates="meal")

class MealIngredient(Base):
    __tablename__ = "meal_ingredients"

    id = Column(Integer, primary_key=True, index=True)
    meal_id = Column(Integer, ForeignKey("meals.id"), nullable=False)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)
    quantity = Column(Float, nullable=False)

    meal = relationship("Meal", back_populates="ingredients")
    ingredient = relationship("Ingredient", back_populates="meal_ingredients")

class MealServing(Base):
    __tablename__ = "meal_servings"

    id = Column(Integer, primary_key=True, index=True)
    meal_id = Column(Integer, ForeignKey("meals.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    portions_served = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    meal = relationship("Meal", back_populates="servings")
    user = relationship("User", back_populates="meal_servings")

class InventoryTransaction(Base):
    __tablename__ = "inventory_transactions"

    id = Column(Integer, primary_key=True, index=True)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)
    quantity_change_grams = Column(Float, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    meal_serving_id = Column(Integer, ForeignKey("meal_servings.id"), nullable=True)
    transaction_type = Column(Enum(TransactionType), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    ingredient = relationship("Ingredient", back_populates="inventory_transactions")
    user = relationship("User", back_populates="inventory_transactions")
    meal_serving = relationship("MealServing")

class MonthlyReport(Base):
    __tablename__ = "monthly_reports"

    id = Column(Integer, primary_key=True, index=True)
    report_month = Column(DateTime, nullable=False)
    total_portions_served = Column(Integer, nullable=False)
    total_portions_possible = Column(Integer, nullable=False)
    discrepancy_rate = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)
    alert_type = Column(Enum(AlertType), nullable=False)
    message = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    ingredient = relationship("Ingredient", back_populates="alerts")

def init_db():
    Base.metadata.create_all(bind=engine)

def populate_sample_data():
    db = SessionLocal()
    try:
        users = [
            User(full_name="Admin One", email="admin1@example.com", password="hashed_password", role=Role.ADMIN),
            User(full_name="Manager One", email="manager1@example.com", password="hashed_password", role=Role.MANAGER),
            User(full_name="Cook One", email="cook1@example.com", password="hashed_password", role=Role.COOK),
        ]
        db.add_all(users)

        ingredients = [
            Ingredient(name="Beef", quantity_grams=5000.0, minimum_quantity=1000.0, delivery_date=datetime.now()),
            Ingredient(name="Potato", quantity_grams=10000.0, minimum_quantity=2000.0, delivery_date=datetime.now()),
            Ingredient(name="Salt", quantity_grams=2000.0, minimum_quantity=500.0, delivery_date=datetime.now()),
        ]
        db.add_all(ingredients)
        db.flush()

        meals = [
            Meal(name="Beef Stew"),
            Meal(name="Mashed Potatoes"),
        ]
        db.add_all(meals)
        db.flush()

        meal_ingredients = [
            MealIngredient(meal_id=meals[0].id, ingredient_id=ingredients[0].id, quantity=200.0),  # 200g beef for stew
            MealIngredient(meal_id=meals[0].id, ingredient_id=ingredients[2].id, quantity=5.0),  # 5g salt for stew
            MealIngredient(meal_id=meals[1].id, ingredient_id=ingredients[1].id, quantity=300.0),
            MealIngredient(meal_id=meals[1].id, ingredient_id=ingredients[2].id, quantity=3.0),  # 3g salt for mashed
        ]
        db.add_all(meal_ingredients)

        transactions = [
            InventoryTransaction(
                ingredient_id=ingredients[0].id,
                quantity_change_grams=5000.0,
                user_id=users[1].id,
                transaction_type=TransactionType.DELIVERY,
                created_at=datetime.now()
            ),
        ]
        db.add_all(transactions)

        reports = [
            MonthlyReport(
                report_month=datetime(2025, 5, 1),
                total_portions_served=100,
                total_portions_possible=120,
                discrepancy_rate=16.67  # (120-100)/120 * 100
            ),
        ]
        db.add_all(reports)

        alerts = [
            Alert(
                ingredient_id=ingredients[0].id,
                alert_type=AlertType.DISCREPANCY,
                message="Discrepancy rate exceeds 15% for May 2025",
                created_at=datetime.now()
            ),
        ]
        db.add_all(alerts)

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error populating sample data: {e}")
    finally:
        db.close()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
    populate_sample_data()
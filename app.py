from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, FoodItem, Order, CartItem
from forms import RegistrationForm, LoginForm, CheckoutForm
import json
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите в систему для доступа к этой странице.'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Создание таблиц
with app.app_context():
    db.create_all()
    # Добавляем тестовые блюда, если их нет
    if FoodItem.query.count() == 0:
        test_foods = [
            FoodItem(name='Маргарита', description='Классическая пицца с томатным соусом и моцареллой', price=450, category='Пицца', image_url='margherita.jpg'),
            FoodItem(name='Пепперони', description='Пицца с пикантным пепперони и сыром', price=550, category='Пицца', image_url='pepperoni.jpg'),
            FoodItem(name='Гавайская', description='Пицца с курицей и ананасами', price=500, category='Пицца', image_url='hawaiian.jpg'),
            FoodItem(name='Чизбургер', description='Сочный бургер с говядиной и сыром чеддер', price=350, category='Бургеры', image_url='cheeseburger.jpg'),
            FoodItem(name='Бургер с беконом', description='Бургер с беконом, сыром и соусом BBQ', price=400, category='Бургеры', image_url='baconburger.jpg'),
            FoodItem(name='Филадельфия', description='Роллы с лососем и сливочным сыром', price=600, category='Суши', image_url='philadelphia.jpg'),
            FoodItem(name='Калифорния', description='Роллы с крабом и авокадо', price=550, category='Суши', image_url='california.jpg'),
            FoodItem(name='Цезарь', description='Салат с курицей, пармезаном и сухариками', price=320, category='Салаты', image_url='caesar.jpg'),
            FoodItem(name='Кола', description='Освежающий напиток', price=150, category='Напитки', image_url='cola.jpg'),
            FoodItem(name='Сок апельсиновый', description='Свежевыжатый апельсиновый сок', price=200, category='Напитки', image_url='juice.jpg'),
        ]
        db.session.add_all(test_foods)
        db.session.commit()

@app.route('/')
def index():
    foods = FoodItem.query.all()
    categories = ['Пицца', 'Бургеры', 'Суши', 'Салаты', 'Напитки']
    return render_template('index.html', foods=foods, categories=categories)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data, method='pbkdf2:sha256')
        user = User(
            username=form.username.data,
            email=form.email.data,
            password_hash=hashed_password
        )
        db.session.add(user)
        db.session.commit()
        flash('Регистрация успешна! Теперь вы можете войти.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            next_page = request.args.get('next')
            flash('Вход выполнен успешно!', 'success')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Неверный email или пароль.', 'danger')
    
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы.', 'info')
    return redirect(url_for('index'))

@app.route('/add_to_cart/<int:food_id>')
@login_required
def add_to_cart(food_id):
    food = FoodItem.query.get_or_404(food_id)
    cart_item = CartItem.query.filter_by(user_id=current_user.id, food_id=food_id).first()
    
    if cart_item:
        cart_item.quantity += 1
    else:
        cart_item = CartItem(user_id=current_user.id, food_id=food_id, quantity=1)
        db.session.add(cart_item)
    
    db.session.commit()
    flash(f'{food.name} добавлен в корзину!', 'success')
    return redirect(request.referrer or url_for('index'))

@app.route('/cart')
@login_required
def cart():
    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    total = sum(item.food.price * item.quantity for item in cart_items)
    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route('/update_cart/<int:cart_id>', methods=['POST'])
@login_required
def update_cart(cart_id):
    cart_item = CartItem.query.get_or_404(cart_id)
    if cart_item.user_id != current_user.id:
        return jsonify({'error': 'Доступ запрещен'}), 403
    
    action = request.json.get('action')
    if action == 'increase':
        cart_item.quantity += 1
    elif action == 'decrease':
        cart_item.quantity -= 1
        if cart_item.quantity <= 0:
            db.session.delete(cart_item)
    elif action == 'remove':
        db.session.delete(cart_item)
    
    db.session.commit()
    return jsonify({'success': True})

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    if not cart_items:
        flash('Корзина пуста!', 'warning')
        return redirect(url_for('cart'))
    
    total = sum(item.food.price * item.quantity for item in cart_items)
    form = CheckoutForm()
    
    if form.validate_on_submit():
        # Создаем заказ
        items_data = [{'name': item.food.name, 'price': item.food.price, 'quantity': item.quantity} for item in cart_items]
        order = Order(
            user_id=current_user.id,
            items=json.dumps(items_data, ensure_ascii=False),
            total_price=total,
            address=form.address.data,
            status='Новый'
        )
        db.session.add(order)
        
        # Очищаем корзину
        for item in cart_items:
            db.session.delete(item)
        
        db.session.commit()
        flash('Заказ успешно оформлен! Спасибо за покупку!', 'success')
        return redirect(url_for('profile'))
    
    return render_template('checkout.html', form=form, cart_items=cart_items, total=total)

@app.route('/profile')
@login_required
def profile():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template('profile.html', orders=orders)

@app.route('/category/<category>')
def category(category):
    foods = FoodItem.query.filter_by(category=category).all()
    categories = ['Пицца', 'Бургеры', 'Суши', 'Салаты', 'Напитки']
    return render_template('index.html', foods=foods, categories=categories, selected_category=category)

if __name__ == '__main__':
    app.run(debug=True)
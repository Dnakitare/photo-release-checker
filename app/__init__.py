from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'  # Change this to your preferred database URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'app/uploads'
app.config['KNOWN_FACES_FOLDER'] = 'app/known_faces'

db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = "You must be logged in to access this page."

@login_manager.user_loader
def load_user(user_id):
    from app.models import User
    return User.query.get(int(user_id))

from app import routes, models

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
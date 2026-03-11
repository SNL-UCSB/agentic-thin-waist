from app.telemetry import db, s3, commands, routes
from config import Config

from flask import Flask
from flask_migrate import Migrate

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
migrate = Migrate(app, db)

s3.init_app(app)

app.register_blueprint(routes.routes_bp)
app.register_blueprint(commands.commands_bp)

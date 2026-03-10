from s3.client import S3Client

from flask_sqlalchemy import SQLAlchemy


s3 = S3Client()
db = SQLAlchemy()

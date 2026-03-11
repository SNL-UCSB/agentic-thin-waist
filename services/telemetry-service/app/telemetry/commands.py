import click

from app.telemetry import s3

from flask import Blueprint

commands_bp = Blueprint("cmd", __name__)


@commands_bp.cli.command(
    "create-base-bucket", help="Create S3 base bucket for application."
)
def create_base_bucket():
    s3.create_base_bucket()
    click.echo("created base bucket.")

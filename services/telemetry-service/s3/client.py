import boto3

from config import Config

from botocore.client import Config as BotoConfig


class S3Client:
    def __init__(self):
        self.bucket_name = Config.S3_BUCKET_NAME
        boto_config = BotoConfig(
            retries={
                "max_attempts": Config.S3_CONNECTION_RETRIES,
            },
            connect_timeout=Config.S3_CONNECTION_TIMEOUT_SECONDS,
        )
        self.client = boto3.client(
            "s3",
            endpoint_url=Config.S3_ENDPOINT_URL,
            aws_access_key_id=Config.S3_ACCESS_KEY,
            aws_secret_access_key=Config.S3_SECRET_KEY,
            config=boto_config,
        )

    def create_base_bucket(self):
        resp = self.client.list_buckets()
        for bucket in resp["Buckets"]:
            if bucket["Name"] == self.bucket_name:
                raise Exception(f"bucket '{self.bucket_name}' already exists.")

        self.client.create_bucket(Bucket=self.bucket_name)

    def put_object(self, file, object_key):
        self.client.upload_fileobj(file, self.bucket_name, object_key)

        return object_key

    def get_object(self, object_key):
        resp = self.client.get_object(Bucket=self.bucket_name, Key=object_key)

        return resp["Body"].read()

    def list_object_keys(self):
        resp = self.client.list_objects_v2(Bucket=self.bucket_name)
        objects = resp["Contents", []]

        return [obj["key"] for obj in objects]

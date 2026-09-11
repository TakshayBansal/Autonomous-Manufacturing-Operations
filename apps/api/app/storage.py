from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from app.core.config import get_settings

try:
    import boto3
    from botocore.client import Config
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:  # pragma: no cover - dependency/runtime guard
    boto3 = None
    Config = None
    BotoCoreError = ClientError = Exception


class ObjectStorage:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = None
        if boto3 and self.settings.object_storage_access_key and self.settings.object_storage_secret_key:
            self._client = boto3.client(
                "s3",
                endpoint_url=self.settings.object_storage_endpoint,
                aws_access_key_id=self.settings.object_storage_access_key,
                aws_secret_access_key=self.settings.object_storage_secret_key,
                region_name=self.settings.object_storage_region,
                use_ssl=self.settings.object_storage_secure,
                config=Config(signature_version="s3v4"),
            )

    @property
    def remote_enabled(self) -> bool:
        return self._client is not None

    def ensure_buckets(self) -> None:
        if not self._client:
            return
        for bucket in (self.settings.object_storage_quarantine_bucket, self.settings.object_storage_evidence_bucket):
            try:
                self._client.head_bucket(Bucket=bucket)
            except ClientError:
                self._client.create_bucket(Bucket=bucket)

    def put_file(self, bucket: str, key: str, source: BinaryIO, content_type: str) -> None:
        source.seek(0)
        if self._client:
            self.ensure_buckets()
            self._client.upload_fileobj(source, bucket, key, ExtraArgs={"ContentType": content_type})
            return
        target = Path(self.settings.upload_dir) / bucket / key
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as output:
            while chunk := source.read(1024 * 1024):
                output.write(chunk)

    def get_bytes(self, bucket: str, key: str) -> bytes:
        if self._client:
            return self._client.get_object(Bucket=bucket, Key=key)["Body"].read()
        return (Path(self.settings.upload_dir) / bucket / key).read_bytes()

    def copy(self, source_bucket: str, source_key: str, target_bucket: str, target_key: str) -> None:
        if self._client:
            self.ensure_buckets()
            self._client.copy_object(
                Bucket=target_bucket,
                Key=target_key,
                CopySource={"Bucket": source_bucket, "Key": source_key},
            )
            self._client.delete_object(Bucket=source_bucket, Key=source_key)
            return
        source = Path(self.settings.upload_dir) / source_bucket / source_key
        target = Path(self.settings.upload_dir) / target_bucket / target_key
        target.parent.mkdir(parents=True, exist_ok=True)
        source.replace(target)

    def presigned_get(self, bucket: str, key: str, expires: int) -> str:
        if self._client:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires,
            )
        return f"/documents/local-content/{key}"

    def healthcheck(self) -> bool:
        if not self._client:
            return Path(self.settings.upload_dir).parent.exists()
        try:
            self._client.list_buckets()
            return True
        except (BotoCoreError, ClientError):
            return False


object_storage = ObjectStorage()

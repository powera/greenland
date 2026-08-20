"""Upload wireword data files to the trakaido-wireword CDN bucket.

Files are uploaded with MD5-hash filenames so they can be served as
immutable cache objects from wireword.trakaido.com.
"""

import hashlib
import logging
import os
from pathlib import Path
from types import ModuleType
from typing import Dict, List, Optional, Tuple, Type

boto3: Optional[ModuleType]
ClientError: Type[BaseException]

try:
    import boto3 as _boto3  # type: ignore[no-redef]
    from botocore.exceptions import ClientError as _ClientError

    boto3 = _boto3
    ClientError = _ClientError
except ImportError:
    boto3 = None
    ClientError = Exception

import constants
from clients.keys import assert_credential_reads_enabled

logger = logging.getLogger(__name__)

# Digital Ocean Spaces configuration for the wireword CDN bucket.
DEFAULT_ENDPOINT = "https://sfo3.digitaloceanspaces.com"
WIREWORD_BUCKET = "trakaido-wireword"
WIREWORD_CDN_BASE = "https://wireword.trakaido.com"


def _file_md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


class WirewordCdnUploader:
    """Upload wireword JSON files to the trakaido-wireword S3/Spaces bucket.

    Files are stored at ``{language_code}/{md5}.json`` and served via
    ``https://wireword.trakaido.com/{language_code}/{md5}.json``.
    """

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        bucket_name: Optional[str] = None,
    ) -> None:
        if boto3 is None:
            raise ImportError("boto3 not installed. Install with: pip install boto3")

        # Only when a credential would actually be sourced: a caller that
        # passes both keys explicitly (as tests do) supplies its own fake and
        # reads nothing out of the environment or keys/ .
        if not (access_key and secret_key):
            assert_credential_reads_enabled("digitalocean")

        self.endpoint_url = endpoint_url or os.getenv("DO_SPACES_ENDPOINT", DEFAULT_ENDPOINT)
        self.bucket_name = bucket_name or os.getenv("DO_WIREWORD_BUCKET", WIREWORD_BUCKET)

        self.access_key = access_key or os.getenv("DO_SPACES_KEY")
        self.secret_key = secret_key or os.getenv("DO_SPACES_SECRET")

        if not self.access_key or not self.secret_key:
            self._load_keys_from_file()

        if not self.access_key or not self.secret_key:
            raise ValueError(
                "Digital Ocean Spaces credentials not found. "
                "Set DO_SPACES_KEY and DO_SPACES_SECRET environment variables "
                "or create keys/digitalocean.key with access key on line 1 "
                "and secret on line 2"
            )

        self.s3 = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
        )
        logger.info("Initialized WirewordCdnUploader for bucket: %s", self.bucket_name)

    def _load_keys_from_file(self) -> None:
        key_file = Path(constants.KEY_DIR) / "digitalocean.key"
        if key_file.exists():
            try:
                lines = key_file.read_text().strip().split("\n")
                if len(lines) >= 2:
                    self.access_key = lines[0].strip()
                    self.secret_key = lines[1].strip()
                    logger.info("Loaded credentials from %s", key_file)
            except Exception as e:
                logger.warning("Error reading key file %s: %s", key_file, e)

    def upload_file(
        self,
        local_path: Path,
        language_code: str,
        check_existing: bool = True,
    ) -> Tuple[bool, str, str]:
        """Upload a wireword JSON file to the CDN bucket.

        The file is stored at ``{language_code}/{md5}.{ext}`` where *md5* is
        the hex digest of the file contents and *ext* is preserved from the
        original filename.

        Args:
            local_path: Path to the local file.
            language_code: Language code used as the S3 key prefix.
            check_existing: Skip upload when an object with the same ETag exists.

        Returns:
            ``(success, s3_key, md5_hash)``
        """
        if not local_path.exists():
            logger.error("File not found: %s", local_path)
            return False, "", ""

        md5_hash = _file_md5(local_path)
        ext = local_path.suffix  # e.g. ".json" or ".jsonl"
        s3_key = f"{language_code}/{md5_hash}{ext}"

        content_type = (
            "application/json" if ext in (".json", ".jsonl") else "application/octet-stream"
        )

        if check_existing:
            try:
                resp = self.s3.head_object(Bucket=self.bucket_name, Key=s3_key)
                existing_etag = resp["ETag"].strip('"')
                if existing_etag == md5_hash:
                    logger.info("Already exists in CDN: %s", s3_key)
                    return True, s3_key, md5_hash
            except ClientError as e:
                if hasattr(e, "response") and e.response["Error"]["Code"] != "404":
                    logger.error("Error checking existing file: %s", e)
                    return False, s3_key, md5_hash

        try:
            extra_args = {
                "ContentType": content_type,
                "ACL": "public-read",
                "CacheControl": "public, max-age=31536000, immutable",
            }
            self.s3.upload_file(str(local_path), self.bucket_name, s3_key, ExtraArgs=extra_args)
            logger.info("Uploaded to CDN: %s", s3_key)
            return True, s3_key, md5_hash
        except Exception as e:
            logger.error("Error uploading %s: %s", s3_key, e)
            return False, s3_key, md5_hash

    def upload_wireword_directory(
        self,
        wireword_dir: str,
        language_code: str,
    ) -> Tuple[bool, List[Dict[str, str]]]:
        """Upload all non-manifest wireword files from a directory.

        Uploads every ``wireword_levels_*.json``, ``wireword_sentences.json``,
        and ``wireword_conversations.jsonl`` found in *wireword_dir*.

        The manifest itself (``wireword_manifest_v2.json``) is **not** uploaded
        to the CDN — it is served from the application server.

        Args:
            wireword_dir: Directory containing exported wireword files.
            language_code: Language code prefix for S3 keys.

        Returns:
            ``(all_succeeded, uploaded_files)`` where *uploaded_files* is a list
            of dicts with ``local_path``, ``s3_key``, and ``md5``.
        """
        dir_path = Path(wireword_dir)
        uploadable = (
            list(dir_path.glob("wireword_levels_*.json"))
            + list(dir_path.glob("wireword_sentences.json"))
            + list(dir_path.glob("wireword_conversations.jsonl"))
        )

        if not uploadable:
            logger.warning("No uploadable wireword files found in %s", wireword_dir)
            return True, []

        all_ok = True
        uploaded: List[Dict[str, str]] = []
        for file_path in sorted(uploadable):
            ok, s3_key, md5_hash = self.upload_file(file_path, language_code)
            if ok:
                uploaded.append({"local_path": str(file_path), "s3_key": s3_key, "md5": md5_hash})
            else:
                all_ok = False

        logger.info(
            "CDN upload complete: %d/%d files uploaded for %s",
            len(uploaded),
            len(uploadable),
            language_code,
        )
        return all_ok, uploaded

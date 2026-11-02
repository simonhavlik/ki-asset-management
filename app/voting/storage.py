"""Bounded private R2 attachments; no object requests while listing proposals."""
import codecs
import hashlib
import os
import uuid
import zipfile
from pathlib import PurePath
from urllib.parse import quote
from flask import current_app

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_PROPOSAL_BYTES = 100 * 1024 * 1024
MAX_FILES = 20
TYPES = {
    '.pdf': 'application/pdf', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    '.webp': 'image/webp', '.gif': 'image/gif', '.txt': 'text/plain', '.csv': 'text/csv',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
}
KEYS = ('KIAM_R2_ENDPOINT','KIAM_R2_ACCESS_KEY_ID','KIAM_R2_SECRET_ACCESS_KEY','KIAM_R2_BUCKET')


def setting(name):
    return current_app.config.get(name) or os.environ.get(name)


def configured():
    return all(setting(name) for name in KEYS)


def client():
    if not configured():
        raise RuntimeError('Private attachment storage is not configured')
    import boto3
    from botocore.config import Config
    return boto3.client('s3', endpoint_url=setting('KIAM_R2_ENDPOINT'),
                        aws_access_key_id=setting('KIAM_R2_ACCESS_KEY_ID'),
                        aws_secret_access_key=setting('KIAM_R2_SECRET_ACCESS_KEY'), region_name='auto',
                        config=Config(signature_version='s3v4',connect_timeout=10,read_timeout=30,
                                      retries={'max_attempts':1},s3={'addressing_style':'path'},
                                      request_checksum_calculation='when_required', response_checksum_validation='when_required'))


def validate_upload(file):
    # Keep Czech filenames, strip both Unix and Windows path components.
    name=(file.filename or '').replace('\\','/').rsplit('/',1)[-1]
    name=''.join(c for c in name if c.isprintable()).strip()
    extension=PurePath(name).suffix.lower()
    if not name or len(name)>200 or extension not in TYPES:
        raise ValueError('attachment_type')
    stream=file.stream;stream.seek(0);head=stream.read(1024);stream.seek(0)
    if extension=='.pdf' and not head.startswith(b'%PDF-'): raise ValueError('attachment_type')
    if extension=='.png' and not head.startswith(b'\x89PNG\r\n\x1a\n'): raise ValueError('attachment_type')
    if extension in ('.jpg','.jpeg') and not head.startswith(b'\xff\xd8\xff'): raise ValueError('attachment_type')
    if extension=='.gif' and head[:6] not in (b'GIF87a',b'GIF89a'): raise ValueError('attachment_type')
    if extension=='.webp' and not (head[:4]==b'RIFF' and head[8:12]==b'WEBP'): raise ValueError('attachment_type')
    size=0;digest=hashlib.sha256();decoder=codecs.getincrementaldecoder('utf-8-sig')() if extension in ('.txt','.csv') else None
    while True:
        part=stream.read(1024*1024)
        if not part:break
        size+=len(part)
        if size>MAX_FILE_BYTES:raise ValueError('attachment_size')
        digest.update(part)
        if decoder:
            try:
                if b'\x00' in part:raise UnicodeError()
                decoder.decode(part)
            except UnicodeError:raise ValueError('attachment_type') from None
    if not size:raise ValueError('attachment_type')
    if decoder:
        try:decoder.decode(b'',final=True)
        except UnicodeError:raise ValueError('attachment_type') from None
    stream.seek(0)
    if extension in ('.docx','.xlsx','.pptx'):
        prefix={'.docx':'word/','.xlsx':'xl/','.pptx':'ppt/'}[extension]
        try:
            with zipfile.ZipFile(stream) as package:
                entries=package.infolist();names=[entry.filename for entry in entries]
                if len(entries)>2000 or sum(entry.file_size for entry in entries)>100*1024*1024:
                    raise ValueError('attachment_type')
                if '[Content_Types].xml' not in names or not any(n.startswith(prefix) for n in names):
                    raise ValueError('attachment_type')
                if any('vbaproject' in n.lower() for n in names):raise ValueError('attachment_type')
        except (zipfile.BadZipFile,OSError):raise ValueError('attachment_type') from None
        finally:stream.seek(0)
    return dict(filename=name,content_type=TYPES[extension],size_bytes=size,sha256=digest.hexdigest(),extension=extension)


def upload(file, metadata, proposal_id):
    key=f'purchase-recommendations/{proposal_id}/{uuid.uuid4().hex}{metadata["extension"]}'
    file.stream.seek(0)
    client().put_object(Bucket=setting('KIAM_R2_BUCKET'),Key=key,Body=file.stream,
                        ContentLength=metadata['size_bytes'],ContentType=metadata['content_type'],
                        ContentDisposition='attachment',Metadata={'sha256':metadata['sha256']})
    return key


def delete_uploaded(key):
    client().delete_object(Bucket=setting('KIAM_R2_BUCKET'),Key=key)


def download_url(attachment):
    disposition="attachment; filename*=UTF-8''"+quote(attachment.filename,safe='')
    return client().generate_presigned_url('get_object',Params={
        'Bucket':setting('KIAM_R2_BUCKET'),'Key':attachment.object_key,
        'ResponseContentDisposition':disposition,'ResponseContentType':attachment.content_type},ExpiresIn=60)

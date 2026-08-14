from importlib.resources import files
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonschema import Draft202012Validator

from forge.request_crypto import Aes256GcmRequestCipher, KeyHandle
from forge.sqlite_state import SqliteStateLedger


for schema_name in (
    "controller-command-v1alpha1.schema.json",
    "controller-response-v1alpha1.schema.json",
):
    resource = files("forge").joinpath("resources/schemas", schema_name)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)

key = KeyHandle("key:synthetic", b"K" * 32)
cipher = Aes256GcmRequestCipher()
encrypted = cipher.encrypt(b"synthetic body", b"synthetic aad", key)
assert cipher.decrypt(encrypted, b"synthetic aad", key) == b"synthetic body"

with TemporaryDirectory() as directory:
    path = Path(directory) / "state.db"
    ledger = SqliteStateLedger.open(path, cipher=cipher, key_handle=key)
    ledger.close()
    assert path.is_file()

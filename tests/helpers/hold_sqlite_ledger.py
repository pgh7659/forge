from pathlib import Path
import sys

from forge.request_crypto import Aes256GcmRequestCipher, KeyHandle
from forge.sqlite_state import SqliteStateLedger


ledger = SqliteStateLedger.open(
    Path(sys.argv[1]),
    cipher=Aes256GcmRequestCipher(),
    key_handle=KeyHandle("key:synthetic", b"K" * 32),
)
print("ready", flush=True)
sys.stdin.readline()
ledger.close()

from forge.canonical import canonical_json_bytes, sha256_hex


def test_rfc8785_normalizes_numbers_and_orders_unicode_members() -> None:
    assert canonical_json_bytes({"z": 1.0, "é": 2, "a": 1}) == (
        b'{"a":1,"z":1,"\xc3\xa9":2}'
    )
    assert canonical_json_bytes(1) == canonical_json_bytes(1.0) == b"1"
    assert canonical_json_bytes(-0.0) == b"0"
    assert canonical_json_bytes(1e-6) == b"0.000001"
    assert canonical_json_bytes(1e-7) == b"1e-7"
    assert canonical_json_bytes(1e30) == b"1e+30"


def test_nested_mapping_order_has_one_digest() -> None:
    assert sha256_hex({"b": {"y": 2, "x": 1}, "a": [3]}) == sha256_hex(
        {"a": [3], "b": {"x": 1, "y": 2}}
    )

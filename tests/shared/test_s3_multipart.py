from app.shared.storage import canonical_query_string, complete_multipart_xml


def test_canonical_query_initiate() -> None:
    assert canonical_query_string({"uploads": ""}) == "uploads="


def test_canonical_query_part_order() -> None:
    assert (
        canonical_query_string({"partNumber": "2", "uploadId": "abc+def"})
        == "partNumber=2&uploadId=abc%2Bdef"
    )


def test_complete_multipart_xml_includes_etags() -> None:
    xml = complete_multipart_xml([(1, '"etag-one"'), (2, '"etag-two"')])
    assert xml.startswith("<CompleteMultipartUpload>")
    assert "<PartNumber>1</PartNumber>" in xml
    assert "<ETag>\"etag-one\"</ETag>" in xml
    assert "<PartNumber>2</PartNumber>" in xml

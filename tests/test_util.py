from launchd_audit.util import human_bytes, mask_mapping, redact_args


class TestMasking:
    def test_masks_values_keeps_keys(self):
        masked = mask_mapping({"API_TOKEN": "hunter2", "PATH": "/usr/bin"})
        assert masked == {"API_TOKEN": "***", "PATH": "***"}
        assert "hunter2" not in str(masked)

    def test_empty(self):
        assert mask_mapping(None) == {}
        assert mask_mapping({}) == {}


class TestHumanBytes:
    def test_bytes(self):
        assert human_bytes(512) == "512 B"

    def test_mb(self):
        assert human_bytes(2 * 1024 * 1024) == "2.0 MB"

    def test_gb(self):
        assert human_bytes(int(2.5 * 1024**3)) == "2.5 GB"


class TestRedactArgs:
    def test_key_equals_value_forms(self):
        out = redact_args(["/usr/bin/tool", "--token=abc123", "API_KEY=xyz", "--verbose=1"])
        assert out == ["/usr/bin/tool", "--token=***", "API_KEY=***", "--verbose=1"]

    def test_flag_then_value(self):
        out = redact_args(["/usr/bin/tool", "--password", "hunter2", "--out", "/tmp/x"])
        assert out == ["/usr/bin/tool", "--password", "***", "--out", "/tmp/x"]

    def test_plain_args_untouched(self):
        args = ["/bin/sh", "-c", "echo hi", "/Users/x/script.sh"]
        assert redact_args(args) == args

    def test_non_string_args(self):
        assert redact_args([1, None]) == ["1", "None"]

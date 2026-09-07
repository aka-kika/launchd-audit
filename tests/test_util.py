from launchd_audit.util import human_bytes, mask_mapping


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

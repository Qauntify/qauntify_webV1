from signals.chart.upload import upload_chart


class _FakeResponse:
    status_code = 200

    def raise_for_status(self):
        return None


class _FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, headers=None, data=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "data": data})
        return _FakeResponse()


def test_upload_chart_posts_png_and_returns_public_url():
    session = _FakeSession()
    url = upload_chart(b"\x89PNG", "sig-123", "https://proj.supabase.co",
                       "service-key", session=session)
    call = session.calls[0]
    assert call["url"].endswith("/storage/v1/object/signal-charts/sig-123.png")
    assert call["headers"]["Content-Type"] == "image/png"
    assert call["data"] == b"\x89PNG"
    assert url == "https://proj.supabase.co/storage/v1/object/public/signal-charts/sig-123.png"

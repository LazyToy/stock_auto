from dashboard.streamlit_compat import image_full_width


class FakeStreamlit:
    def __init__(self, image_func):
        self.image = image_func
        self.calls = []


def test_image_full_width_uses_stretch_width_when_streamlit_supports_it():
    fake = FakeStreamlit(lambda image, width="content", use_column_width=None: fake.calls.append(
        {"image": image, "width": width, "use_column_width": use_column_width}
    ))

    image_full_width(fake, "chart-bytes")

    assert fake.calls == [{"image": "chart-bytes", "width": "stretch", "use_column_width": None}]


def test_image_full_width_uses_legacy_column_width_for_old_streamlit():
    fake = FakeStreamlit(lambda image, width=None, use_column_width=None: fake.calls.append(
        {"image": image, "width": width, "use_column_width": use_column_width}
    ))

    image_full_width(fake, "chart-bytes")

    assert fake.calls == [{"image": "chart-bytes", "width": None, "use_column_width": True}]

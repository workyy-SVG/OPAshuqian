from io import BytesIO
from PIL import Image
from services.food_facts_service import FIELDS, product_image_url
from views.food_facts_view import cached_product_photo


def test_front_image_selection_and_untrusted_urls():
    valid = 'https://images.openfoodfacts.org/images/products/611/test.jpg'
    assert 'image_front_url' in FIELDS.split(',')
    assert product_image_url({'image_front_url': valid}) == valid
    for bad in ('http://localhost/a.jpg', 'https://images.openfoodfacts.org.evil.com/images/products/a',
                'https://user@images.openfoodfacts.org/images/products/a', 'javascript:alert(1)', None):
        assert product_image_url({'image_front_url': bad}) is None
    assert product_image_url({'image_front_url': '', 'image_front_small_url': valid}) == valid


def test_photo_normalized_and_failed_photo_falls_back(monkeypatch):
    output = BytesIO()
    Image.new('RGB', (100, 200), 'blue').save(output, 'PNG')

    class Response:
        status_code = 200
        body = output.getvalue()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def iter_content(self, size):
            yield self.body

    response = Response()
    monkeypatch.setattr('views.food_facts_view.requests.get', lambda *a, **kw: response)
    cached_product_photo.clear()
    result = cached_product_photo('https://images.openfoodfacts.org/images/products/test.jpg')
    with Image.open(BytesIO(result)) as img:
        assert img.size == (380, 440)
        assert img.getpixel((0, 0)) == (255, 255, 255)
    cached_product_photo.clear()
    response.body = b'not an image'
    assert cached_product_photo('https://images.openfoodfacts.org/images/products/test.jpg') is None
    cached_product_photo.clear()
    response.body = b'x' * (4 * 1024 * 1024 + 1)
    assert cached_product_photo('https://images.openfoodfacts.org/images/products/test.jpg') is None
    cached_product_photo.clear()

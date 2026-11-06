from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from .models import Product, Review


class ProductApiTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name="Test Headphones",
            image_url="https://example.com/headphones.jpg",
            price="99.99",
        )

    def test_list_products(self):
        response = self.client.get(reverse("list_products"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()[0]["slug"], "test-headphones")

    def test_product_detail(self):
        response = self.client.get(
            reverse("product_detail", kwargs={"slug": self.product.slug})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["name"], "Test Headphones")

    def test_summary_requires_reviews(self):
        response = self.client.post(
            reverse("generate_reviews_summary", kwargs={"slug": self.product.slug})
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(OPENAI_API_KEY="test-key")
    @patch("review_app.views.summarize_reviews", return_value="A useful summary")
    def test_generate_summary(self, summarize_reviews):
        Review.objects.create(
            product=self.product,
            rating=5,
            comment="Excellent sound quality",
        )

        response = self.client.post(
            reverse("generate_reviews_summary", kwargs={"slug": self.product.slug})
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()["summary"], "A useful summary")
        summarize_reviews.assert_called_once()

    @override_settings(OPENAI_API_KEY="test-key")
    @patch("review_app.views.summarize_reviews")
    def test_recent_summary_is_reused(self, summarize_reviews):
        self.product.review_summary = "Existing summary"
        self.product.summary_updated_at = timezone.now() - timedelta(days=1)
        self.product.save(update_fields=["review_summary", "summary_updated_at"])

        response = self.client.post(
            reverse("generate_reviews_summary", kwargs={"slug": self.product.slug})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["summary"], "Existing summary")
        summarize_reviews.assert_not_called()

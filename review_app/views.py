from datetime import timedelta

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from openai import OpenAI, OpenAIError
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from review_app.models import Product
from review_app.serializers import ListProductSerializer, ProductDetailSerializer


def summarize_reviews(product_name, reviews):
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    reviews_text = "\n".join([f"- {r.rating}/5: {r.comment}" for r in reviews])
    # 4/5 awesome product, really loved it!
    # 2/5 poor product, really loved it!

    prompt_input = f"""
You are an assistant that summarizes customer reviews.

Product: {product_name}

Reviews:
{reviews_text}

Provide:
- Overall sentiment
- Common pros
- Common cons
- Short final summary
"""

    response = client.responses.create(
        model=settings.OPENAI_MODEL,
        input=prompt_input,
        temperature=0.4,
        max_output_tokens=600,
    )

    answer = response.output_text

    return answer


@api_view(["POST"])
def generate_reviews_summary(request, slug):
    product = get_object_or_404(Product, slug=slug)

    # 1️⃣ Enforce 7-day interval
    if product.summary_updated_at:
        next_allowed_time = product.summary_updated_at + timedelta(days=7)

        if timezone.now() < next_allowed_time:
            time_left = next_allowed_time - timezone.now()
            days_left = time_left.days + (1 if time_left.seconds > 0 else 0)

            return Response(
                {
                    "detail": "Summary was recently generated",
                    "summary": product.review_summary,
                    "days_left": days_left,
                    "next_allowed_at": next_allowed_time,
                    "generated_at": product.summary_updated_at,
                    "newly_created": False,
                },
                status=status.HTTP_200_OK,
            )

    # 2️⃣ Fetch latest reviews
    reviews = product.reviews.order_by("-created_at")[:10]
    if not reviews.exists():
        return Response(
            {"error": "No reviews available."}, status=status.HTTP_400_BAD_REQUEST
        )

    # 3️⃣ Generate new summary
    if not settings.OPENAI_API_KEY:
        return Response(
            {"error": "The review summary service is not configured."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    try:
        summary = summarize_reviews(product.name, reviews)
    except OpenAIError:
        return Response(
            {"error": "The review summary service is temporarily unavailable."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    product.review_summary = summary
    product.summary_updated_at = timezone.now()
    product.save(update_fields=["review_summary", "summary_updated_at"])

    return Response(
        {
            "product": product.name,
            "summary": summary,
            "generated_at": product.summary_updated_at,
            "days_left": 7,
            "newly_created": True,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
def list_products(request):
    products = Product.objects.all().order_by("-id")
    serializer = ListProductSerializer(products, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def product_detail(request, slug):
    product = get_object_or_404(Product, slug=slug)
    serializer = ProductDetailSerializer(product)
    return Response(serializer.data)


@api_view(["GET"])
def ask_how_are_you(request):
    return Response({"message": "How are you today?"})


@api_view(["GET"])
def who_are_you(request):
    return Response({"message": "I am an AI assistant."})

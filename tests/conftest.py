"""
Shared pytest fixtures for Byte Bot tests.
Uses moto to mock DynamoDB and unittest.mock for Anthropic.
"""

import os
import pytest
import boto3
from moto import mock_aws

# Set test environment before any bot imports
os.environ.setdefault("ENVIRONMENT", "local")
os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("DYNAMODB_TABLE", "ByteBot-Test")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")


TABLE_NAME = "ByteBot-Test"


def create_test_table(dynamodb_resource):
    return dynamodb_resource.create_table(
        TableName=TABLE_NAME,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
            {"AttributeName": "gsi1pk", "AttributeType": "S"},
            {"AttributeName": "gsi1sk", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "GSI1",
                "KeySchema": [
                    {"AttributeName": "gsi1pk", "KeyType": "HASH"},
                    {"AttributeName": "gsi1sk", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    )


@pytest.fixture
def aws_credentials():
    """Mocked AWS credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture
def dynamodb_table(aws_credentials):
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        table = create_test_table(resource)
        yield table


@pytest.fixture
def sample_profile():
    return {
        "PK": "USER#123456",
        "SK": "PROFILE",
        "discord_username": "testuser",
        "preferred_diet": "keto",
        "dietary_restrictions": ["gluten-free"],
        "allergies": ["peanuts"],
        "fitness_goals": "lose weight",
        "activity_level": "moderately_active",
        "created_at": "2026-03-16T00:00:00+00:00",
        "updated_at": "2026-03-16T00:00:00+00:00",
    }

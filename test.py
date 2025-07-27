import os
from langchain_aws import ChatBedrock
import boto3
# Set AWS profile and region via environment variables
os.environ["AWS_PROFILE"] = "sumit01"
os.environ["AWS_DEFAULT_REGION"] = "us-west-2"
llm = ChatBedrock(
    model_id="anthropic.claude-3-sonnet-20240229-v1:0"
)
import boto3
print("Script AWS identity:", boto3.client("sts").get_caller_identity())
response = llm.invoke("Write a short poem about the sky.")

print(response.content)
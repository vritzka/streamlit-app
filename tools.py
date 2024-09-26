import json
import os
import boto3
import logging
import streamlit as st
from dotenv import load_dotenv
load_dotenv() 
lambda_client = boto3.client(
    'lambda',
    region_name='us-west-2',
    aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY")
);

# example function
def get_recommended_products(customer_product_description):
    logging.info(f"Running: get_recommended_products {customer_product_description}")
    # AWS Lambda function name
    lambda_function_name = "recommendProducts"

    # Prepare the payload
    payload = json.dumps({
        "customer_product_description": customer_product_description,
        "shopify_token": st.session_state['shopify_token'],
        "shop": st.session_state['shopify_shop']
    })

    # Invoke the AWS Lambda function
    response = lambda_client.invoke(
        FunctionName=lambda_function_name,
        Payload=payload
    )
    # Extract the StreamingBody object from the response
    streaming_body = response['Payload']
    
    # Read the content of the StreamingBody
    payload_bytes = streaming_body.read()
    
    # Decode the bytes to a string
    payload_str = payload_bytes.decode('utf-8')
    
    return payload_str


TOOL_MAP = {
    "get_recommended_products": get_recommended_products,
    # ... other functions ...
}

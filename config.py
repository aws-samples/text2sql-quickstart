import os
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

# AWS 설정
AWS_REGION = 'ap-northeast-2'

# Bedrock 모델 설정
BEDROCK_MODELS = {
    'claude': "anthropic.claude-3-5-sonnet-20240620-v1:0",
    'titan_embedding': "amazon.titan-embed-text-v2:0",
    'cross_claude' : "apac.anthropic.claude-3-5-sonnet-20240620-v1:0"
}

# OpenSearch 설정
OPENSEARCH_CONFIG = {
    'host': os.getenv('OPENSEARCH_HOST'),
    'port': int(os.getenv('OPENSEARCH_PORT', 443)),
    'username': os.getenv('OPENSEARCH_USERNAME'),
    'password': os.getenv('OPENSEARCH_PASSWORD'),
    'domain': os.getenv('OPENSEARCH_DOMAIN')
}

# Redshift 설정
REDSHIFT_CONFIG = {
    'host': os.getenv('REDSHIFT_HOST'),
    'port': int(os.getenv('REDSHIFT_PORT', 5439)),
    'database': os.getenv('REDSHIFT_DATABASE'),
    'user': os.getenv('REDSHIFT_USER'),
    'password': os.getenv('REDSHIFT_PASSWORD')
}
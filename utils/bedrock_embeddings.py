# bedrock_embeddings.py

import boto3
import json
from typing import List
from langchain.embeddings.base import Embeddings

import time

class BedrockEmbeddings(Embeddings):
    def __init__(self, model_id: str, region_name: str, client=None):
        """
        Bedrock 임베딩 생성을 위한 Embeddings 클래스

        Args:
            model_id (str): Bedrock 임베딩 모델 ID
            region_name (str): AWS 리전 이름
            client: 기존 Bedrock 클라이언트 (선택사항)
        """
        self.model_id = model_id
        self.client = client or boto3.client('bedrock-runtime', region_name=region_name)
        self.max_retries = 3
        self.base_delay = 1

    def embed_query(self, text: str) -> List[float]:
        """단일 텍스트에 대한 임베딩 생성"""
        if not text.strip():
            return []
        
        for attempt in range(self.max_retries):
            try:
                request_body = {
                    "inputText": text.strip()
                }

                response = self.client.invoke_model(
                    modelId=self.model_id,
                    contentType="application/json",
                    accept="application/json",
                    body=json.dumps(request_body)
                )

                response_body = json.loads(response.get('body').read())

                if 'embedding' in response_body:
                    return response_body['embedding']
                elif 'vector' in response_body:
                    return response_body['vector']
                else:
                    print(f"Warning: No embedding found in response (attempt {attempt + 1}/{self.max_retries})")
                    if attempt == self.max_retries - 1:
                        return []

            except Exception as e:
                print(f"임베딩 생성 중 오류 발생 (attempt {attempt + 1}/{self.max_retries}): {str(e)}")
                if hasattr(e, 'response'):
                    print(f"Response: {e.response}")
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(self.base_delay * (2 ** attempt))  # 지수 백오프

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """다수 문서에 대한 임베딩 생성"""
        return [self.embed_query(t) for t in texts]

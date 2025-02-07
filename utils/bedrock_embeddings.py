# bedrock_embeddings.py

import boto3
import json
from typing import List
from langchain.embeddings.base import Embeddings

class BedrockEmbeddings(Embeddings):
    def __init__(self, model_id: str, region_name: str):
        """
        Bedrock 임베딩 생성을 위한 Embeddings 클래스

        Args:
            model_id (str): Bedrock 임베딩 모델 ID
            region_name (str): AWS 리전 이름
        """
        self.model_id = model_id
        self.client = boto3.client('bedrock-runtime', region_name=region_name)

    def embed_query(self, text: str) -> List[float]:
        """단일 텍스트에 대한 임베딩 생성"""
        if not text.strip():
            return []

        try:
            # Titan 임베딩 모델용 입력 형식
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
                print("Warning: No embedding found in response")
                return []

        except Exception as e:
            print(f"임베딩 생성 중 오류 발생: {str(e)}")
            if hasattr(e, 'response'):
                print(f"Response: {e.response}")
            raise

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """다수 문서에 대한 임베딩 생성"""
        return [self.embed_query(t) for t in texts]
from typing import Dict, Any, List
import os
import json
from datetime import datetime
from utils.indice_opensearch import OpenSearchManager

class FeedbackHandler:
    def __init__(self, opensearch_manager: OpenSearchManager):
        self.opensearch_manager = opensearch_manager
        self.index_name = 'user_feedback_queries'

    def _load_mapping_file(self) -> Dict:
        """매핑 설정 파일 로드"""
        try:
            mapping_path = os.path.join('utils', 'opensearch_mappings', 'user_feedback_queries.json')
            with open(mapping_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"매핑 파일 로드 중 오류 발생: {str(e)}")
            return {}

    def _create_feedback_index(self) -> bool:
        """피드백 저장을 위한 인덱스 생성"""
        try:
            if not self.opensearch_manager.client.indices.exists(index=self.index_name):
                mapping_config = self._load_mapping_file()
                if mapping_config:
                    self.opensearch_manager.client.indices.create(
                        index=self.index_name,
                        body=mapping_config
                    )
            return True
        except Exception as e:
            print(f"인덱스 생성 중 오류 발생: {str(e)}")
            return False

    def save_feedback(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """쿼리 실행 결과와 피드백 저장"""
        try:
            if not self._create_feedback_index():
                return {
                    "success": False,
                    "message": "피드백 저장용 인덱스 생성에 실패했습니다."
                }

            query = state.get("query", "")
            sql = state.get("sql", "")
            results = state.get("query_results", [])
            metadata = state.get("metadata", {})

            # 임베딩 생성
            query_embedding = self.opensearch_manager._get_embedding(query)

            # 문서 생성
            document = {
                "natural_language": query,
                "sql": sql,
                # "results_sample": results[:5] if results else [],
                # "feedback_time": datetime.now().isoformat(),
                # "execution_success": bool(results),
                # "performance_metrics": metadata.get("performance_metrics", {}),
                "embedding": query_embedding
            }

            # OpenSearch에 문서 저장
            response = self.opensearch_manager.client.index(
                index=self.index_name,
                body=document,
                id=f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(query)}"
            )

            return {
                "success": True,
                "message": "쿼리가 성공적으로 저장되었습니다.",
                "document_id": response['_id']
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"쿼리 저장 중 오류가 발생했습니다: {str(e)}"
            }

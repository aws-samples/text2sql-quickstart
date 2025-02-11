from typing import Dict
import streamlit as st
from datetime import datetime

def index_sample_queries(client, embedder, schema_data: Dict, version_id: str = None) -> bool:
    """Index sample queries"""
    try:
        st.info("🔄 샘플 쿼리 인덱싱 중...")
        current_time = datetime.now().isoformat()

        for index, query in enumerate(schema_data['database_schema']['augmented_queries']):
            # 쿼리 정보에 대한 임베딩 생성
            query_text = f"{query.get('description', '')} {query.get('queyr', '')}"
            query_embedding = embedder.embed_query(query_text)

            document = {
                "query": query.get('query', ''),
                "description": {
                    "korean": query.get('description', {}).get('korean', ''),
                    "english": query.get('description', {}).get('english', '')
                },
                "business_purpose": {
                    "korean": query.get('business_purpose', {}).get('korean', ''),
                    "english": query.get('business_purpose', {}).get('english', '')
                },
                "technical_details": {
                    "korean": query.get('technical_details', {}).get('korean', ''),
                    "english": query.get('technical_details', {}).get('english', '')
                },
                "natural_language_variations": {
                    "korean": query.get('natural_language_variations', {}).get('korean', []),
                    "english": query.get('natural_language_variations', {}).get('english', [])
                },
                "keyword_variations": {
                    "terms": [
                        {
                            "base_term": {
                                "korean": term.get('base_term', {}).get('korean', ''),
                                "english": term.get('base_term', {}).get('english', '')
                            },
                            "variations": {
                                "korean": term.get('variations', {}).get('korean', []),
                                "english": term.get('variations', {}).get('english', [])
                            }
                        }
                        for term in query.get('keyword_variations', {}).get('terms', [])
                    ]
                },
                "related_queries": [
                    {
                        "question": {
                            "korean": rq.get('question', {}).get('korean', ''),
                            "english": rq.get('question', {}).get('english', '')
                        },
                        "variations": {
                            "korean": rq.get('variations', {}).get('korean', []),
                            "english": rq.get('variations', {}).get('english', [])
                        },
                        "sql": rq.get('sql', '')
                    }
                    for rq in query.get('related_queries', [])
                ],
                "search_text": query_text,
                "embedding": query_embedding,
                "version_id": version_id or datetime.now().strftime('%Y%m%d_%H%M%S'),
                "updated_at": current_time,
            }

            client.index(
                index='sample_queries',
                body=document,
                id=f"{document['version_id']}_{index}"
            )

        st.success("✅ 샘플 쿼리가 성공적으로 인덱싱되었습니다.")
        return True

    except Exception as e:
        st.error(f"샘플 쿼리 인덱싱 중 오류가 발생했습니다: {str(e)}")
        st.write("Error details:", str(e))
        return False

def index_user_feedback_queries(client, embedder, feedback_data: Dict, version_id: str = None) -> bool:
    """Index user feedback queries"""
    try:
        st.info("🔄 사용자 피드백 쿼리 인덱싱 중...")
        current_time = datetime.now().isoformat()

        for feedback in feedback_data:
            # 쿼리 정보에 대한 임베딩 생성
            query_text = f"{feedback.get('natural_language', '')}"
            query_embedding = embedder.embed_query(query_text)

            document = {
                "natural_language": feedback.get('natural_language', ''),
                "sql": feedback.get('sql', ''),
                "search_text": query_text,
                "embedding": query_embedding,
                "version_id": version_id or datetime.now().strftime('%Y%m%d_%H%M%S'),
                "updated_at": current_time
            }

            client.index(
                index='user_feedback_queries',
                body=document,
                id=f"{document['version_id']}_{hash(feedback.get('sql', ''))}"
            )

        st.success("✅ 사용자 피드백 쿼리가 성공적으로 인덱싱되었습니다.")
        return True

    except Exception as e:
        st.error(f"사용자 피드백 쿼리 인덱싱 중 오류가 발생했습니다: {str(e)}")
        st.write("Error details:", str(e))
        return False

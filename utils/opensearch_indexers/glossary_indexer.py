from typing import Dict, List
import streamlit as st
from datetime import datetime

def index_business_glossary(client, embedder, augmenter, glossary_data: List[Dict]) -> bool:
    """Index business glossary terms"""
    try:
        st.info("🔄 비즈니스 용어 사전 인덱싱 중...")

        for term in glossary_data:
            # 용어 정보에 대한 임베딩 생성
            term_text = f"{term.get('word', {}).get('korean', '')} {term.get('word', {}).get('english', '')} {term.get('description', {}).get('korean', '')}"
            term_embedding = embedder.embed_query(term_text)

            # 용어 정보 증강
            augmented_term = augmenter.augment_glossary_term(term)

            document = {
                "word": {
                    "korean": augmented_term.get('word', {}).get('korean', ''),
                    "english": augmented_term.get('word', {}).get('english', '')
                },
                "abbreviation": augmented_term.get('abbreviation', ''),
                "technical_term": {
                    "korean": augmented_term.get('technical_term', {}).get('korean', ''),
                    "english": augmented_term.get('technical_term', {}).get('english', '')
                },
                "column_reference": {
                    "column_name": augmented_term.get('column_reference', {}).get('column_name', ''),
                    "table_name": augmented_term.get('column_reference', {}).get('table_name', ''),
                    "schema_name": augmented_term.get('column_reference', {}).get('schema_name', '')
                },
                "description": {
                    "korean": augmented_term.get('description', {}).get('korean', ''),
                    "english": augmented_term.get('description', {}).get('english', '')
                },
                "business_context": {
                    "korean": augmented_term.get('business_context', {}).get('korean', ''),
                    "english": augmented_term.get('business_context', {}).get('english', '')
                },
                "examples": [
                    {
                        "value": example.get('value', ''),
                        "description": {
                            "korean": example.get('description', {}).get('korean', ''),
                            "english": example.get('description', {}).get('english', '')
                        },
                        "context": {
                            "korean": example.get('context', {}).get('korean', ''),
                            "english": example.get('context', {}).get('english', '')
                        }
                    }
                    for example in augmented_term.get('examples', [])
                ],
                "synonyms": {
                    "korean": augmented_term.get('synonyms', {}).get('korean', []),
                    "english": augmented_term.get('synonyms', {}).get('english', [])
                },
                "related_terms": {
                    "korean": augmented_term.get('related_terms', {}).get('korean', []),
                    "english": augmented_term.get('related_terms', {}).get('english', [])
                },
                "usage_patterns": [
                    {
                        "pattern": {
                            "korean": pattern.get('pattern', {}).get('korean', ''),
                            "english": pattern.get('pattern', {}).get('english', '')
                        },
                        "examples": {
                            "korean": pattern.get('examples', {}).get('korean', []),
                            "english": pattern.get('examples', {}).get('english', [])
                        }
                    }
                    for pattern in augmented_term.get('usage_patterns', [])
                ],
                "search_text": term_text,
                "embedding": term_embedding,
                "updated_at": datetime.now().isoformat()
            }

            client.index(
                index='business_glossary',
                body=document,
                id=f"{document['word']['korean']}_{document['word']['english']}"
            )

        st.success("✅ 비즈니스 용어 사전이 성공적으로 인덱싱되었습니다.")
        return True

    except Exception as e:
        st.error(f"비즈니스 용어 사전 인덱싱 중 오류가 발생했습니다: {str(e)}")
        st.write("Error details:", str(e))
        return False

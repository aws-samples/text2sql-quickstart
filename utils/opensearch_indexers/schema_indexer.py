from typing import Dict
import streamlit as st
from datetime import datetime

def index_schema(client, embedder, schema_data: Dict, version_id: str = None) -> bool:
    """Index schema information"""
    try:
        st.info("🔄 스키마 정보 인덱싱 중...")
        current_time = datetime.now().isoformat()

        for table in schema_data['database_schema']['tables']:
            # 테이블 정보에 대한 임베딩 생성
            table_text = f"{table['table_name']} {table.get('description', '')}"
            table_embedding = embedder.embed_query(table_text)

            # 테이블 정보 증강
            augmented_info = table.get('augmented_table_info', {})
            augmented_table_info = augmented_info.get('table_info', table.get('table_info', {}))

            document = {
                "table_info": {
                    "name": table['table_name'],
                    "description": {
                        "korean": augmented_table_info.get('description', {}).get('korean', ''),
                        "english": augmented_table_info.get('description', {}).get('english', '')
                    },
                    "business_context": {
                        "korean": augmented_table_info.get('business_context', {}).get('korean', ''),
                        "english": augmented_table_info.get('business_context', {}).get('english', '')
                    },
                    "technical_context": {
                        "korean": augmented_table_info.get('technical_context', {}).get('korean', ''),
                        "english": augmented_table_info.get('technical_context', {}).get('english', '')
                    },
                    "synonyms": {
                        "table_name": {
                            "korean": augmented_table_info.get('synonyms', {}).get('table_name', {}).get('korean', []),
                            "english": augmented_table_info.get('synonyms', {}).get('table_name', {}).get('english', [])
                        },
                        "business_terms": {
                            "korean": augmented_table_info.get('synonyms', {}).get('business_terms', {}).get('korean', []),
                            "english": augmented_table_info.get('synonyms', {}).get('business_terms', {}).get('english', [])
                        }
                    },
                    "related_terms": {
                        "korean": augmented_table_info.get('related_terms', {}).get('korean', []),
                        "english": augmented_table_info.get('related_terms', {}).get('english', [])
                    },
                    "common_queries": {
                        "korean": augmented_table_info.get('common_queries', {}).get('korean', []),
                        "english": augmented_table_info.get('common_queries', {}).get('english', [])
                    },
                    "query_patterns": [
                        {
                            "pattern": {
                                "korean": pattern.get('pattern', {}).get('korean', ''),
                                "english": pattern.get('pattern', {}).get('english', '')
                            },
                            "related_keywords": {
                                "korean": pattern.get('related_keywords', {}).get('korean', []),
                                "english": pattern.get('related_keywords', {}).get('english', [])
                            },
                            "variations": {
                                "korean": pattern.get('variations', {}).get('korean', []),
                                "english": pattern.get('variations', {}).get('english', [])
                            }
                        }
                        for pattern in augmented_table_info.get('query_patterns', [])
                    ]
                },
                "columns": [],
                "search_text": table_text,
                "embedding": table_embedding,
                "version_id": version_id or datetime.now().strftime('%Y%m%d_%H%M%S'),
                "updated_at": current_time
            }

            # 컬럼 정보 처리
            for column in table.get('columns', []):
                augmented_column = column.get('augmented_column_info', {})
                column_text = f"{column['name']} {column.get('description', '')}"
                column_embedding = embedder.embed_query(column_text)

                column_doc = {
                    "name": column['name'],
                    "type": column['type'],
                    "description": {
                        "korean": augmented_column.get('description', {}).get('korean', ''),
                        "english": augmented_column.get('description', {}).get('english', '')
                    },
                    "business_context": {
                        "korean": augmented_column.get('business_context', {}).get('korean', ''),
                        "english": augmented_column.get('business_context', {}).get('english', '')
                    },
                    "technical_context": {
                        "korean": augmented_column.get('technical_context', {}).get('korean', ''),
                        "english": augmented_column.get('technical_context', {}).get('english', '')
                    },
                    "synonyms": {
                        "column_name": {
                            "korean": augmented_column.get('synonyms', {}).get('column_name', {}).get('korean', []),
                            "english": augmented_column.get('synonyms', {}).get('column_name', {}).get('english', [])
                        },
                        "value_meanings": {
                            "values": [
                                {
                                    "value": v.get('value', ''),
                                    "korean": v.get('korean', ''),
                                    "english": v.get('english', '')
                                }
                                for v in augmented_column.get('synonyms', {}).get('value_meanings', {}).get('values', [])
                            ],
                            "status_codes": [
                                {
                                    "code": s.get('code', ''),
                                    "korean": s.get('korean', ''),
                                    "english": s.get('english', '')
                                }
                                for s in augmented_column.get('synonyms', {}).get('value_meanings', {}).get('status_codes', [])
                            ]
                        }
                    },
                    "search_patterns": [
                        {
                            "pattern": {
                                "korean": p.get('pattern', {}).get('korean', ''),
                                "english": p.get('pattern', {}).get('english', '')
                            },
                            "related_keywords": {
                                "korean": p.get('related_keywords', {}).get('korean', []),
                                "english": p.get('related_keywords', {}).get('english', [])
                            },
                            "variations": {
                                "korean": p.get('variations', {}).get('korean', []),
                                "english": p.get('variations', {}).get('english', [])
                            }
                        }
                        for p in augmented_column.get('search_patterns', [])
                    ],
                    "common_conditions": [
                        {
                            "condition": {
                                "korean": c.get('condition', {}).get('korean', ''),
                                "english": c.get('condition', {}).get('english', '')
                            },
                            "examples": [
                                {
                                    "sql": e.get('sql', ''),
                                    "korean": e.get('korean', ''),
                                    "english": e.get('english', '')
                                }
                                for e in c.get('examples', [])
                            ],
                            "use_cases": {
                                "korean": c.get('use_cases', {}).get('korean', []),
                                "english": c.get('use_cases', {}).get('english', [])
                            }
                        }
                        for c in augmented_column.get('common_conditions', [])
                    ],
                    "examples": column.get('examples', []),
                    "valid_values": column.get('valid_values', []),
                    "constraints": {
                        "type": column.get('constraints', ''),
                        "description": {
                            "korean": augmented_column.get('constraints', {}).get('description', {}).get('korean', ''),
                            "english": augmented_column.get('constraints', {}).get('description', {}).get('english', '')
                        }
                    },
                    "embedding": column_embedding
                }
                document["columns"].append(column_doc)

            # OpenSearch에 문서 인덱싱
            client.index(
                index='schema_info',
                body=document,
                id=f"{document['version_id']}_{table['table_name']}"
            )

        st.success("✅ 스키마 정보가 성공적으로 인덱싱되었습니다.")
        return True

    except Exception as e:
        st.error(f"스키마 인덱싱 중 오류가 발생했습니다: {str(e)}")
        st.write("Error details:", str(e))
        return False

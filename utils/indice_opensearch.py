import boto3
from opensearchpy import OpenSearch
import json
from typing import Dict, List, Optional
import streamlit as st
import time
from datetime import datetime
import os
from config import AWS_REGION, OPENSEARCH_CONFIG, BEDROCK_MODELS
from utils.augmentation import SchemaAugmenter
from utils.bedrock_embeddings import BedrockEmbeddings
from utils.opensearch_indexers import (
    index_schema,
    index_sample_queries,
    index_user_feedback_queries,
    index_business_glossary
)

class OpenSearchManager:
    def __init__(self):
        """Initialize OpenSearch manager with required clients"""
        self.region = AWS_REGION
        self.augmenter = SchemaAugmenter()

        # OpenSearch 클라이언트 설정
        self.client = OpenSearch(
            hosts=[{'host': OPENSEARCH_CONFIG['host'], 'port': OPENSEARCH_CONFIG['port']}],
            http_auth=(OPENSEARCH_CONFIG['username'], OPENSEARCH_CONFIG['password']),
            use_ssl=True,
            verify_certs=True
        )
        self.max_retries = 3
        self.base_delay = 2  # 초기 대기 시간 (초)
        self.k = 8

        self.embedder = BedrockEmbeddings(
            model_id=BEDROCK_MODELS['titan_embedding'],
            region_name=AWS_REGION
        )

    def _load_mapping_file(self, filename: str) -> Dict:
        """Load mapping configuration from JSON file"""
        try:
            mapping_path = os.path.join('utils', 'opensearch_mappings', filename)
            with open(mapping_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            st.error(f"매핑 파일 로드 중 오류 발생: {str(e)}")
            return {}

    def create_indices(self) -> bool:
        """Create necessary indices if they don't exist"""
        try:
            # 매핑 설정
            index_mappings = {
                'database_schema': 'database_schema.json',
                'sample_queries': 'sample_queries.json',
                'business_glossary': 'business_glossary.json'
            }

            for index, mapping_file in index_mappings.items():
                if not self.client.indices.exists(index=index):
                    mapping_config = self._load_mapping_file(mapping_file)
                    if mapping_config:
                        self.client.indices.create(index=index, body=mapping_config)
                        st.success(f"✅ {index} 인덱스가 생성되었습니다.")
            return True

        except Exception as e:
            st.error(f"인덱스 생성 중 오류가 발생했습니다: {str(e)}")
            return False

    def _get_embedding(self, text: str, max_retries: int = 3) -> Optional[List[float]]:
        """LangChain Embeddings를 사용하여 임베딩 생성"""
        if not text.strip():
            st.warning("빈 텍스트에 대한 임베딩 시도를 건너뜁니다.")
            return None

        attempt = 0
        while attempt < max_retries:
            try:
                embedding = self.embedder.embed_query(text)
                if embedding and len(embedding) > 0:
                    return embedding
                st.warning(f"임베딩 생성 실패 (시도 {attempt + 1}/{max_retries})")
            except Exception as e:
                st.error(f"임베딩 생성 중 오류 발생: {str(e)}")
                if hasattr(e, 'response'):
                    st.error(f"Response: {e.response}")

            attempt += 1
            if attempt < max_retries:
                st.info(f"임베딩 재시도 중... ({attempt}/{max_retries})")
                time.sleep(2 ** attempt)  # 지수 백오프
        return None

    def index_schema(self, schema_data: Dict, version_id: str = None) -> bool:
        """Index schema information using the schema indexer"""
        if not self.create_indices():
            return False
            
        # 스키마 정보 인덱싱
        schema_result = index_schema(self.client, self.embedder, schema_data, version_id)
        if not schema_result:
            return False
            
        # 샘플 쿼리 인덱싱 (스키마 인덱싱과 함께 자동으로 실행)
        query_result = index_sample_queries(self.client, self.embedder, schema_data, version_id)
        
        return schema_result and query_result

    def index_sample_queries(self, schema_data: Dict, version_id: str = None) -> bool:
        """Index sample queries using the query indexer"""
        if not self.create_indices():
            return False
        return index_sample_queries(self.client, self.embedder, schema_data, version_id)

    def index_user_feedback_queries(self, feedback_data: Dict, version_id: str = None) -> bool:
        """Index user feedback queries using the query indexer"""
        if not self.create_indices():
            return False
        return index_user_feedback_queries(self.client, self.embedder, feedback_data, version_id)

    def index_business_glossary(self, glossary_data: List[Dict]) -> bool:
        """Index business glossary terms using the glossary indexer"""
        if not self.create_indices():
            return False
        return index_business_glossary(self.client, self.embedder, self.augmenter, glossary_data)

    def test_connection(self) -> bool:
        """Test OpenSearch connection"""
        try:
            info = self.client.info()
            return True
        except Exception as e:
            st.error(f"OpenSearch 연결 실패: {str(e)}")
            return False

    def clear_indices(self) -> bool:
        """Clear all indices"""
        try:
            indices = ['database_schema', 'sample_queries', 'business_glossary']
            for index in indices:
                if self.client.indices.exists(index=index):
                    self.client.indices.delete(index=index)
                    st.success(f"✅ {index} 인덱스가 삭제되었습니다.")
            return True
        except Exception as e:
            st.error(f"인덱스 초기화 중 오류가 발생했습니다: {str(e)}")
            return False

    def integrated_search(self, query: str, top_k: int = 10) -> Dict[str, List[Dict]]:
        """Perform integrated search across all indices"""
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            with ThreadPoolExecutor(max_workers=3) as executor:
                # 각 검색 작업을 병렬로 실행
                futures = {
                    executor.submit(self._search_schema, query, top_k): 'database_schema',
                    executor.submit(self._search_queries, query, top_k): 'sample_queries',
                    executor.submit(self._search_user_feedback_queries, query, top_k): 'user_feedback_queries'
                }

                results = {}
                for future in as_completed(futures):
                    search_type = futures[future]
                    try:
                        results[search_type] = future.result()
                    except Exception as e:
                        print(f"{search_type} 검색 중 오류 발생: {str(e)}")
                        results[search_type] = []

            return results

        except Exception as e:
            st.error(f"통합 검색 중 오류가 발생했습니다: {str(e)}")
            return {}

    def _lexical_schema_search(self, query: str, top_k: int = 5):
        """Lexical search for schema information"""
        search_body = {
            "size": top_k,
            "query": {
                "bool": {
                    "should": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": [
                                    "table_info.name^4",
                                    "table_info.description.korean^3",
                                    "table_info.description.english^2",
                                    "table_info.business_context.korean^3",
                                    "table_info.business_context.english^2",
                                    "table_info.technical_context.korean^2",
                                    "table_info.technical_context.english^2",
                                    "table_info.synonyms.table_name.korean^2",
                                    "table_info.synonyms.table_name.english^2",
                                    "table_info.synonyms.business_terms.korean^2",
                                    "table_info.synonyms.business_terms.english^2",
                                    "table_info.related_terms.korean^1.5",
                                    "table_info.related_terms.english^1.5",
                                    "search_text"
                                ],
                                "type": "best_fields",
                                "tie_breaker": 0.3
                            }
                        },
                        {
                            "nested": {
                                "path": "columns",
                                "query": {
                                    "bool": {
                                        "should": [
                                            {
                                                "multi_match": {
                                                    "query": query,
                                                    "fields": [
                                                        "columns.name^4",
                                                        "columns.description.korean^3",
                                                        "columns.description.english^2",
                                                        "columns.business_context.korean^3",
                                                        "columns.business_context.english^2",
                                                        "columns.technical_context.korean^2",
                                                        "columns.technical_context.english^2",
                                                        "columns.synonyms.column_name.korean^2",
                                                        "columns.synonyms.column_name.english^2",
                                                        "columns.synonyms.value_meanings.values.value^2",
                                                        "columns.synonyms.value_meanings.values.korean^2",
                                                        "columns.synonyms.value_meanings.values.english^1.5"
                                                    ],
                                                    "type": "best_fields",
                                                    "tie_breaker": 0.3
                                                }
                                            }
                                        ]
                                    }
                                },
                                "inner_hits": {}
                            }
                        }
                    ]
                }
            },
            "highlight": {
                "fields": {
                    "table_info.description.korean": {},
                    "table_info.description.english": {},
                    "table_info.business_context.korean": {},
                    "table_info.business_context.english": {},
                    "columns.description.korean": {},
                    "columns.description.english": {},
                    "columns.business_context.korean": {},
                    "columns.business_context.english": {}
                },
                "pre_tags": ["<mark>"],
                "post_tags": ["</mark>"]
            }
        }

        response = self.client.search(index='database_schema', body=search_body)
        return response

    def _semantic_schema_search(self, query: str):
        """Semantic search for schema information"""
        embedding_vector = self._get_embedding(text=query)
        search_body = {
            "size": self.k,
            "query": {
                "bool": {
                    "should": [
                        {
                            "knn": {
                                "embedding": {
                                    "vector": embedding_vector,
                                    "k": self.k
                                }
                            }
                        },
                        {
                            "nested": {
                                "path": "columns",
                                "query": {
                                    "knn": {
                                        "columns.embedding": {
                                            "vector": embedding_vector,
                                            "k": self.k
                                        }
                                    }
                                },
                                "inner_hits": {
                                    "size": self.k
                                }
                            }
                        }
                    ]
                }
            }
        }

        results = self.client.search(
            index="database_schema",
            body=search_body
        )

        return results

    def _lexical_query_search(self, query: str, top_k: int = 5):
        """Lexical search for sample queries"""
        search_body = {
            "size": top_k,
            "query": {
                "bool": {
                    "should": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": [
                                    "description.korean^3",
                                    "description.english^2",
                                    "business_purpose.korean^3",
                                    "business_purpose.english^2",
                                    "technical_details.korean^2",
                                    "technical_details.english^2",
                                    "natural_language_variations.korean^2",
                                    "natural_language_variations.english^2",
                                    "search_text"
                                ],
                                "type": "best_fields",
                                "tie_breaker": 0.3
                            }
                        },
                        {
                            "nested": {
                                "path": "keyword_variations.terms",
                                "query": {
                                    "bool": {
                                        "should": [
                                            {
                                                "multi_match": {
                                                    "query": query,
                                                    "fields": [
                                                        "keyword_variations.terms.base_term.korean^2",
                                                        "keyword_variations.terms.base_term.english^2",
                                                        "keyword_variations.terms.variations.korean^1.5",
                                                        "keyword_variations.terms.variations.english^1.5"
                                                    ]
                                                }
                                            }
                                        ]
                                    }
                                }
                            }
                        }
                    ]
                }
            },
            "highlight": {
                "fields": {
                    "description.korean": {},
                    "description.english": {},
                    "business_purpose.korean": {},
                    "business_purpose.english": {},
                    "natural_language_variations.korean": {},
                    "natural_language_variations.english": {}
                },
                "pre_tags": ["<mark>"],
                "post_tags": ["</mark>"]
            }
        }

        response = self.client.search(index='sample_queries', body=search_body)
        return response

    def _semantic_query_search(self, query: str):
        """Semantic search for sample queries"""
        embedding_vector = self._get_embedding(text=query)
        search_body = {
            "size": self.k,
            "query": {
                "knn": {
                    "embedding": {
                        "vector": embedding_vector,
                        "k": 8
                    }
                }
            }
        }

        response = self.client.search(
            index="sample_queries",
            body=search_body
        )

        return response

    def _process_schema_result(self, response: Dict, search_method: str) -> List[Dict]:
        """Process schema search results"""

        result = []
        if response['hits']['hits']:
            for hit in response['hits']['hits']:
                source = hit['_source']

                # 테이블 정보 처리
                table_info = source['table_info']
                table = {
                    "id": table_info['name'],
                    "table_name": table_info['name'],
                    "description": table_info['description']['korean'],
                    "score": hit['_score'],
                    "related_columns": [],
                    "search_method": search_method
                }

                # 컬럼 정보 처리
                hit_columns = hit['inner_hits']['columns']['hits']['hits']
                if not hit_columns:
                    continue

                for column in hit_columns:
                    name = column['_source']['name']
                    column_type = column['_source']['type']
                    description = column['_source'].get('description', {})
                    examples = column['_source'].get('examples', [])
                    valid_values = column['_source'].get('valid_values', [])
                    score = column['_score']

                    table['related_columns'].append({
                        "id": table['table_name'] + '-' + name,
                        "name": name,
                        "type": column_type,
                        "description": description['korean'],
                        "examples": examples,
                        "valid_values": valid_values,
                        "score": score,
                        "search_method": search_method
                    })

                result.append(table)
            return result

        return result

    def _process_query_results(self, response: Dict, search_method: str) -> List[Dict]:
        """Process query search results"""
        results = []

        for hit in response['hits']['hits']:
            source = hit['_source']

            result = {
                "query": source['query'],
                'description': source['description']['korean'],
                "score": hit['_score'],
                "search_method": search_method
            }

            results.append(result)

        return results

    def _count_all_tables(self) -> int:
        response = self.client.count(
            index="database_schema"
        )
        return response['count']

    def _search_all_tables(self) -> List:
        """Search all tables"""
        total_table_count = self._count_all_tables()
        search_body = {
            "size": total_table_count,
            "query": {
                "match_all": {}
            }
        }
        response = self.client.search(
            index="database_schema",
            body=search_body
        )

        result = []
        if response['hits']['hits']:
            for hit in response['hits']['hits']:
                source = hit['_source']

                # 테이블 정보 처리
                table_info = source['table_info']
                table = {
                    "table_name": table_info['name'],
                    "description": table_info['description']['korean'],
                    "columns": []
                }

                # 컬럼 정보 처리
                columns = source['columns']
                for column in columns:
                    name = column['name']
                    column_type = column['type']
                    description = column.get('description', {})
                    examples = column.get('examples', [])
                    valid_values = column.get('valid_values', [])
                    table['columns'].append({
                        "name": name,
                        "type": column_type,
                        "description": description['korean'],
                        "examples": examples,
                        "valid_values": valid_values,
                    })

                result.append(table)

        return result

    def _search_schema(self, query: str, top_k: int = 10, semantic_weight: float = 0.4) -> Dict:
        """Search schema information"""
        search_schema_result = {}
        try:
            # 전체 테이블 서치
            search_schema_result['tables'] = self._search_all_tables()

            # lexical search와 semantic search를 순차적으로 실행
            lexical_results = self._process_schema_result(
                self._lexical_schema_search(query, top_k),
                search_method='lexical_search'
            )
            semantic_results = self._process_schema_result(
                self._semantic_schema_search(query),
                search_method='semantic_search'
            )

            # 결과가 없는 경우 빈 리스트 처리
            lexical_results = lexical_results or []
            semantic_results = semantic_results or []

            # 정규화 함수
            def _normalize_score_in_array(search_results, weight):
                if not search_results:
                    return search_results
                    
                min_score = min(search_result['score'] for search_result in search_results)
                max_score = max(search_result['score'] for search_result in search_results)
                score_range = max_score - min_score
                
                if score_range != 0:
                    for search_result in search_results:
                        search_result['normalized_score'] = ((search_result['score'] - min_score) / score_range) * weight
                else:
                    for search_result in search_results:
                        search_result['normalized_score'] = weight
                return search_results

            # 가중치에 따라 정규화
            lexical_results = _normalize_score_in_array(lexical_results, 1 - semantic_weight)
            semantic_results = _normalize_score_in_array(semantic_results, semantic_weight)
            for lexical_result in lexical_results:
                _normalize_score_in_array(lexical_result['related_columns'], 1 - semantic_weight)
            for semantic_result in semantic_results:
                _normalize_score_in_array(semantic_result['related_columns'], semantic_weight)

            combined_table_map = {}
            for table in lexical_results + semantic_results:
                table_id = table['id']
                table_search_method = table['search_method']
                if table_id not in combined_table_map:
                    combined_table_map[table_id] = table.copy()
                    combined_table_map[table_id]['hybrid_score'] = table.get('normalized_score', 0)
                    combined_table_map[table_id]['search_methods'] = [table_search_method]
                else:
                    combined_table_map[table_id]['hybrid_score'] += table.get('normalized_score', 0)
                    if table_search_method not in combined_table_map[table_id]['search_methods']:
                        combined_table_map[table_id]['search_methods'].append(table_search_method)

                columns = table['related_columns']
                combined_column_map = {}

                for column in columns:
                    column_id = column['id']
                    search_method = column['search_method']
                    if column_id not in combined_column_map:
                        combined_column_map[column_id] = column.copy()
                        combined_column_map[column_id]['hybrid_score'] = column.get('normalized_score', 0)
                        combined_column_map[column_id]['search_methods'] = [search_method]
                    else:
                        combined_column_map[column_id]['hybrid_score'] += column.get('normalized_score', 0)
                        if search_method not in combined_column_map[column_id]['search_methods']:
                            combined_column_map[column_id]['search_methods'].append(search_method)

                combined_column_list = list(combined_column_map.values())
                combined_column_list.sort(key=lambda x: x['hybrid_score'], reverse=True)

                combined_table_map[table_id]['related_columns'] = combined_column_list

            combined_table_list = list(combined_table_map.values())
            combined_table_list.sort(key=lambda x: x['hybrid_score'], reverse=True)

            # 불필요한 값 제거
            for table in combined_table_list:
                table.pop('id', None)
                table.pop('score', None)
                table.pop('normalized_score', None)
                table.pop('search_method', None)
                for column in table['related_columns']:
                    column.pop('id', None)
                    column.pop('score', None)
                    column.pop('normalized_score', None)
                    column.pop('search_method', None)
                    column.pop('examples', None)
                    column.pop('valid_values', None)

            search_schema_result['related_tables'] = combined_table_list

            return search_schema_result

        except Exception as e:
            st.error(f"스키마 검색 중 오류가 발생했습니다: {str(e)}")
            return {'table_name': '', 'description': '', 'columns': [], 'related_columns': []}

    def _search_queries(self, query: str, top_k: int = 10, semantic_weight: float = 0.6) -> List[Dict]:
        """Search sample queries"""
        try:
            lexical_result = self._process_query_results(self._lexical_query_search(query, top_k),
                                                       search_method='lexical_search')
            semantic_result = self._process_query_results(self._semantic_query_search(query),
                                                        search_method='semantic_search')

            def _normalize_score_in_array(search_result, weight):
                if not search_result:
                    return search_result
                    
                min_score = min(sq['score'] for sq in search_result)
                max_score = max(sq['score'] for sq in search_result)
                score_range = max_score - min_score
                
                if score_range != 0:
                    for sq in search_result:
                        sq['normalized_score'] = ((sq['score'] - min_score) / score_range) * weight
                else:
                    for sq in search_result:
                        sq['normalized_score'] = weight

                return search_result

            lexical_result = _normalize_score_in_array(lexical_result, 1 - semantic_weight)
            semantic_result = _normalize_score_in_array(semantic_result, semantic_weight)

            combined_result_map = {}

            for sample_query in lexical_result + semantic_result:
                query_id = sample_query['query']
                search_method = sample_query['search_method']
                if query_id not in combined_result_map:
                    combined_result_map[query_id] = sample_query.copy()
                    combined_result_map[query_id]['hybrid_score'] = sample_query.get('normalized_score', 0)
                    combined_result_map[query_id]['search_methods'] = [search_method]
                else:
                    combined_result_map[query_id]['hybrid_score'] += sample_query.get('normalized_score', 0)
                    if search_method not in combined_result_map[query_id]['search_methods']:
                        combined_result_map[query_id]['search_methods'].append(search_method)

            combined_results = list(combined_result_map.values())
            combined_results.sort(key=lambda x: x['hybrid_score'], reverse=True)

            temp_combined_results = []
            for combined_result in combined_results:
                temp_combined_results.append({
                    "query": combined_result['query'],
                    "description": combined_result['description'],
                    "hybrid_score": combined_result['hybrid_score']
                })

            return temp_combined_results[:40]

        except Exception as e:
            st.error(f"쿼리 검색 중 오류가 발생했습니다: {str(e)}")
            return []

    def _search_user_feedback_queries(self, query: str, top_k: int = 10, semantic_weight: float = 0.7) -> List[Dict]:
        """Search user feedback queries"""
        try:
            lexical_result = self._process_user_feedback_query_results(self._lexical_user_feedback_query_search(query, top_k),
                                                                     search_method='lexical_search')
            semantic_result = self._process_user_feedback_query_results(self._semantic_user_feedback_query_search(query),
                                                                      search_method='semantic_search')

            def _normalize_score_in_array(search_result, weight):
                if not search_result:
                    return search_result
                    
                min_score = min(sq['score'] for sq in search_result)
                max_score = max(sq['score'] for sq in search_result)
                score_range = max_score - min_score
                
                if score_range != 0:
                    for sq in search_result:
                        sq['normalized_score'] = ((sq['score'] - min_score) / score_range) * weight
                else:
                    for sq in search_result:
                        sq['normalized_score'] = weight

                return search_result

            if lexical_result:
                lexical_result = _normalize_score_in_array(lexical_result, 1 - semantic_weight)

            if semantic_result:
                semantic_result = _normalize_score_in_array(semantic_result, semantic_weight)

            combined_result_map = {}

            for sample_query in lexical_result + semantic_result:
                query_id = sample_query['sql']
                search_method = sample_query['search_method']
                if query_id not in combined_result_map:
                    combined_result_map[query_id] = sample_query.copy()
                    combined_result_map[query_id]['hybrid_score'] = sample_query.get('normalized_score', 0)
                    combined_result_map[query_id]['search_methods'] = [search_method]
                else:
                    combined_result_map[query_id]['hybrid_score'] += sample_query.get('normalized_score', 0)
                    if search_method not in combined_result_map[query_id]['search_methods']:
                        combined_result_map[query_id]['search_methods'].append(search_method)

            combined_results = list(combined_result_map.values())
            combined_results.sort(key=lambda x: x['hybrid_score'], reverse=True)
            return combined_results[:40]

        except Exception as e:
            st.error(f"사용자 피드백 쿼리 검색 중 오류가 발생했습니다: {str(e)}")
            return []

    def _lexical_user_feedback_query_search(self, query: str, top_k: int = 5):
        """Lexical search for user feedback queries"""
        search_body = {
            "size": top_k,
            "query": {
                "bool": {
                    "should": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": [
                                    "natural_language^3",
                                    "sql^2"
                                ],
                                "type": "best_fields",
                                "tie_breaker": 0.3
                            }
                        }
                    ]
                }
            }
        }

        response = self.client.search(index='user_feedback_queries', body=search_body)
        return response

    def _semantic_user_feedback_query_search(self, query: str):
        """Semantic search for user feedback queries"""
        embedding_vector = self._get_embedding(text=query)
        search_body = {
            "size": self.k,
            "query": {
                "knn": {
                    "embedding": {
                        "vector": embedding_vector,
                        "k": 8
                    }
                }
            }
        }

        response = self.client.search(
            index="user_feedback_queries",
            body=search_body
        )

        return response

    def _process_user_feedback_query_results(self, response: Dict, search_method: str) -> List[Dict]:
        """Process user feedback query results"""
        results = []

        for hit in response['hits']['hits']:
            source = hit['_source']

            result = {
                "natural_language": source["natural_language"],
                "sql": source["sql"],
                "score": hit['_score'],
                "search_method": search_method
            }

            results.append(result)

        return results

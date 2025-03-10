from typing import Dict, Any, List
from langchain_core.messages import AIMessage
import streamlit as st

class SearchValidator:
    def __init__(self, llm):
        self.llm = llm
        self.relevance_threshold = 0.3  # 관련성 임계값 완화

    def validate_search_results(self,
                                search_results: Dict[str, Any],
                                intent: Dict[str, Any]) -> Dict[str, Any]:
        """검색 결과 검증 및 피드백 생성"""
        try:
            # 기본 검증
            if not search_results:
                return {
                    "is_valid": False,
                    "feedback": "검색 결과가 없습니다.",
                    "suggested_actions": ["rephrase_question"],
                    "relevant_schemas": []
                }

            # 스키마 정보와 샘플 쿼리 확인
            database_schema = search_results.get('database_schema', {})
            sample_queries = search_results.get('sample_queries', [])
            user_feedback = search_results.get('user_feedback_queries', [])

            # 관련성 검사
            validation = self.check_relevance(search_results, intent)
            
            # 사용자 피드백 기반 검증
            if user_feedback:
                feedback_validation = self._validate_with_feedback(user_feedback, intent)
                if feedback_validation["is_valid"]:
                    validation["relevant_schemas"].extend(feedback_validation["relevant_schemas"])
                    validation["is_relevant"] = True

            if validation["relevant_schemas"]:
                return {
                    "is_valid": True,
                    "feedback": "검색 결과가 유효합니다.",
                    "suggested_actions": [],
                    "relevant_schemas": validation["relevant_schemas"]
                }

            # 부분 일치하는 경우도 relevant_schemas에 포함
            if validation.get("partial_matches"):
                validation["relevant_schemas"].extend(validation["partial_matches"])
                return {
                    "is_valid": True,
                    "feedback": "관련된 스키마를 찾았습니다.",
                    "suggested_actions": [],
                    "relevant_schemas": validation["relevant_schemas"]
                }

            return {
                "is_valid": False,
                "feedback": "질문과 관련된 스키마를 찾을 수 없습니다. 다른 방식으로 질문해보세요.",
                "suggested_actions": ["rephrase_question", "provide_more_context"],
                "relevant_schemas": []
            }

        except Exception as e:
            return {
                "is_valid": False,
                "feedback": f"검색 결과 검증 중 오류가 발생했습니다: {str(e)}",
                "suggested_actions": ["retry_search"],
                "relevant_schemas": []
            }

    def check_relevance(self,
                        search_results: Dict[str, Any],
                        intent: Dict[str, Any]) -> Dict[str, Any]:
        """검색 결과와 의도의 관련성 검증"""
        try:
            response = {
                "is_relevant": False,
                "relevant_schemas": [],
                "partial_matches": [],
                "feedback": "",
                "suggested_actions": []
            }

            # 스키마 정보 확인
            database_schema = search_results.get('database_schema', {})
            related_tables = database_schema.get('related_tables', [])
            if not related_tables:
                return response

            # 의도에서 키워드 추출
            intent_keywords = []
            if 'target_entities' in intent:
                intent_keywords.extend([entity.lower() for entity in intent['target_entities']])
            if 'conditions' in intent:
                intent_keywords.extend([condition.lower() for condition in intent['conditions']])

            if not intent_keywords:
                return response

            # 테이블 정보 처리
            for table in related_tables:
                # hybrid_score 확인
                hybrid_score = table.get('hybrid_score', 0)
                
                # hybrid_score 기준 완화 (0.6 이상)
                if hybrid_score >= 0.6:
                    response["is_relevant"] = True
                    if table not in response["relevant_schemas"]:
                        response["relevant_schemas"].append(table)
                    continue

                matches = 0
                total_keywords = len(intent_keywords)
                
                # 테이블명과 설명 매칭
                table_name = table.get('table_name', '').lower()
                table_desc = table.get('description', '').lower()
                related_columns = table.get('related_columns', [])

                # 키워드 매칭 검사
                for keyword in intent_keywords:
                    keyword = keyword.lower()
                    # 테이블명 매칭
                    if keyword in table_name:
                        matches += 1
                        continue
                    
                    # 설명 매칭
                    if keyword in table_desc:
                        matches += 0.8  # 설명 매칭은 0.8점
                        continue
                    
                    # 컬럼 매칭
                    for column in related_columns:
                        column_name = column.get('name', '').lower()
                        column_desc = column.get('description', '').lower()
                        if keyword in column_name or keyword in column_desc:
                            matches += 0.6  # 컬럼 매칭은 0.6점
                            break

                # hybrid_score를 가중치로 사용
                # hybrid_score가 높을수록 더 낮은 매칭률도 허용
                required_match_ratio = self.relevance_threshold
                if hybrid_score > 0.5:
                    required_match_ratio *= (1 - (hybrid_score - 0.5))

                match_ratio = matches / total_keywords
                if match_ratio >= required_match_ratio:
                    response["is_relevant"] = True
                    if table not in response["relevant_schemas"]:
                        response["relevant_schemas"].append(table)
                elif match_ratio >= required_match_ratio * 0.7:  # 부분 매칭 임계값
                    if table not in response["partial_matches"]:
                        response["partial_matches"].append(table)

            # 샘플 쿼리 관련성 검사
            sample_queries = search_results.get('sample_queries', [])
            if sample_queries:
                for query in sample_queries:
                    if self._check_query_relevance(query, intent):
                        response["is_relevant"] = True
                        # SQL 쿼리에서 테이블 정보 추출
                        sql_query = query.get('query', '').lower()
                        if sql_query:
                            from_parts = sql_query.split(' from ')
                            if len(from_parts) > 1:
                                table_part = from_parts[1].split(' where ')[0].strip()
                                # 테이블명에서 스키마 부분 제거 (예: general_system.table_name -> table_name)
                                table_name = table_part.split('.')[-1] if '.' in table_part else table_part
                                matching_schema = next(
                                    (table for table in related_tables
                                     if table.get('table_name', '').lower().endswith(table_name)),
                                    None
                                )
                                if matching_schema and matching_schema not in response["relevant_schemas"]:
                                    response["relevant_schemas"].append(matching_schema)

            # 결과 요약 설정
            if response["relevant_schemas"]:
                response["feedback"] = "관련된 스키마를 찾았습니다."
            elif response["partial_matches"]:
                response["feedback"] = "부분적으로 일치하는 스키마를 찾았습니다."
                response["suggested_actions"].append("provide_more_context")
            else:
                response["feedback"] = "관련된 스키마를 찾을 수 없습니다."
                response["suggested_actions"].extend(["rephrase_question", "provide_more_context"])

            return response

        except Exception as e:
            st.error(f"관련성 검사 중 오류 발생: {str(e)}")
            return {
                "is_relevant": False,
                "relevant_schemas": [],
                "partial_matches": [],
                "feedback": f"관련성 검사 중 오류 발생: {str(e)}",
                "suggested_actions": ["retry_search"]
            }

    def _validate_with_feedback(self, feedback_queries: List[Dict], intent: Dict) -> Dict[str, Any]:
        """사용자 피드백 기반 검증"""
        try:
            result = {
                "is_valid": False,
                "relevant_schemas": [],
                "feedback": ""
            }

            # 피드백 쿼리 분석
            for feedback in feedback_queries:
                # hybrid_score 확인
                hybrid_score = feedback.get('hybrid_score', 0)
                
                # hybrid_score가 높은 경우 (0.8 이상) 바로 관련성 있다고 판단
                if hybrid_score >= 0.8:
                    result["is_valid"] = True
                    sql = feedback.get('sql', '').lower()
                    for table in intent.get('target_entities', []):
                        if table.lower() in sql and table not in result["relevant_schemas"]:
                            result["relevant_schemas"].append(table)
                    continue

                natural_language = feedback.get('natural_language', '').lower()
                if not natural_language:
                    continue

                # 의도에서 키워드 추출
                intent_keywords = []
                if 'target_entities' in intent:
                    intent_keywords.extend([entity.lower() for entity in intent['target_entities']])
                if 'conditions' in intent:
                    intent_keywords.extend([condition.lower() for condition in intent['conditions']])

                if not intent_keywords:
                    continue

                # 키워드 매칭 수행
                matches = 0
                total_keywords = len(intent_keywords)

                for keyword in intent_keywords:
                    if keyword in natural_language:
                        matches += 1

                # hybrid_score를 가중치로 사용
                # hybrid_score가 높을수록 더 낮은 매칭률도 허용
                required_match_ratio = self.relevance_threshold
                if hybrid_score > 0.5:
                    required_match_ratio *= (1 - (hybrid_score - 0.5))  # hybrid_score가 높을수록 임계값 낮춤

                match_ratio = matches / total_keywords
                if match_ratio >= required_match_ratio:
                    result["is_valid"] = True
                    sql = feedback.get('sql', '').lower()
                    for table in intent.get('target_entities', []):
                        if table.lower() in sql and table not in result["relevant_schemas"]:
                            result["relevant_schemas"].append(table)

            if result["is_valid"]:
                result["feedback"] = "유사한 성공적인 쿼리 이력이 있습니다."
            
            return result

        except Exception as e:
            st.error(f"피드백 기반 검증 중 오류 발생: {str(e)}")
            return {
                "is_valid": False,
                "relevant_schemas": [],
                "feedback": f"피드백 검증 중 오류 발생: {str(e)}"
            }

    def _check_query_relevance(self, query: Dict, intent: Dict) -> bool:
        """샘플 쿼리와 의도의 관련성 검사"""
        try:
            # hybrid_score 기준 추가 완화 (0.4 이상)
            hybrid_score = query.get('hybrid_score', 0)
            if hybrid_score >= 0.4:
                return True

            # 쿼리 설명 가져오기
            description = query.get('description', '').lower()
            if not description:
                return False

            # 의도에서 키워드 추출
            intent_keywords = []
            if 'target_entities' in intent:
                intent_keywords.extend([entity.lower() for entity in intent['target_entities']])
            if 'conditions' in intent:
                intent_keywords.extend([condition.lower() for condition in intent['conditions']])

            if not intent_keywords:
                return False

            # 키워드가 설명에 포함되어 있으면 관련성 있다고 판단
            for keyword in intent_keywords:
                if keyword in description:
                    return True

            return False

        except Exception as e:
            st.error(f"쿼리 관련성 검사 중 오류 발생: {str(e)}")
            return False

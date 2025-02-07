from typing import Dict, Any
from datetime import datetime
from uuid import uuid4
from langgraph.graph import StateGraph
from .workflow_state import WorkflowState
from langchain_core.messages import HumanMessage, AIMessage
from chains.intent_analyzer import IntentAnalyzer
from chains.search_validator import SearchValidator
from chains.sql_validator import SQLValidator
from utils.response_handler import ResponseHandler
from typing import Dict, Any
from chains.feedback_handler import FeedbackHandler

class TextToSQLFlow:
    def __init__(
            self,
            opensearch_manager,
            sql_generator,
            redshift_manager,
            performance_monitor,
            package_manager,
            llm
    ):
        self.opensearch_manager = opensearch_manager
        self.package_manager = package_manager
        self.sql_generator = sql_generator
        self.redshift_manager = redshift_manager
        self.performance_monitor = performance_monitor
        self.intent_analyzer = IntentAnalyzer(llm)
        self.search_validator = SearchValidator(llm)
        # SQLValidator 초기화 시 redshift_manager도 전달
        self.sql_validator = SQLValidator(llm, redshift_manager)
        self.response_handler = ResponseHandler()
        self.feedback_handler = FeedbackHandler(opensearch_manager)
        self.graph = self._create_workflow()

    def execute(self, query: str) -> Dict[str, Any]:
        """워크플로우 실행"""
        try:
            # 성능 모니터링 시작
            operation_id = self.performance_monitor.start_operation("complete_workflow")

            # 초기 상태 설정
            initial_state = WorkflowState(
                messages=[HumanMessage(content=query)],
                current_step="analyze_intent",
                query=query,
                intent={},
                search_results={},
                validation_results={},
                sql="",
                query_results=[],
                metadata={
                    "query_id": str(uuid4()),
                    "start_time": datetime.now().isoformat()
                }
            )

            # 워크플로우 실행
            final_state = self.graph.invoke(initial_state)

            # 결과 처리
            result = self.response_handler.format_response(final_state)

            # 성능 모니터링 종료
            self.performance_monitor.end_operation(operation_id, result)

            return result

        except Exception as e:
            # 오류 발생 시 성능 모니터링에 기록
            if 'operation_id' in locals():
                self.performance_monitor.log_error(operation_id, e)

            return {
                "success": False,
                "error": str(e),
                "feedback": "죄송합니다. 예상치 못한 오류가 발생했습니다.",
                "suggested_actions": ["retry_question"],
                "metadata": {
                    "query_id": str(uuid4()),
                    "error_time": datetime.now().isoformat()
                }
            }

    def _create_workflow(self) -> StateGraph:
        """워크플로우 생성"""
        workflow = StateGraph(WorkflowState)

        # 1. 의도 분석 노드
        def analyze_intent(state: WorkflowState) -> WorkflowState:
            """의도 분석 노드"""
            try:
                analysis_result = self.intent_analyzer.analyze_and_validate(state["query"])

                if not analysis_result["is_valid"]:
                    return {
                        **state,
                        "current_step": "complete",
                        "intent": analysis_result["intent"],
                        "validation_results": {
                            "is_valid": False,
                            "feedback": analysis_result["feedback"],
                            "suggested_actions": analysis_result["suggested_actions"]
                        }
                    }

                return {
                    **state,
                    "current_step": "search_schema",
                    "intent": analysis_result["intent"],
                    "validation_results": {
                        "is_valid": True,
                        "feedback": analysis_result["feedback"],
                        "suggested_actions": []
                    }
                }

            except Exception as e:
                return {
                    **state,
                    "current_step": "complete",
                    "intent": {},
                    "validation_results": {
                        "is_valid": False,
                        "feedback": f"의도 분석 중 오류가 발생했습니다: {str(e)}",
                        "suggested_actions": ["rephrase_question"]
                    }
                }

        # 2. 스키마 검색 노드
        def search_schema(state: WorkflowState) -> WorkflowState:
            """스키마 검색 노드"""
            try:
                search_results = self.opensearch_manager.integrated_search(
                    query=state["query"],
                    top_k=5
                ) or {}  # None이 반환되면 빈 딕셔너리로 처리

                # 검색 결과 검증
                validation = self.search_validator.validate_search_results(
                    search_results,
                    state["intent"]
                )

                # 검증 실패 시 즉시 완료
                if not validation["is_valid"] or not validation.get("relevant_schemas"):
                    return {
                        **state,
                        "current_step": "complete",
                        "search_results": search_results,
                        "validation_results": validation,
                        "sql": "",  # SQL 생성 없이 빈 문자열 반환
                        "query_results": [],
                        "feedback": "관련된 스키마를 찾을 수 없습니다. 다른 방식으로 질문해주세요."
                    }

                return {
                    **state,
                    "current_step": "generate_sql",
                    "search_results": search_results,
                    "validation_results": validation
                }

            except Exception as e:
                return {
                    **state,
                    "current_step": "complete",
                    "search_results": {},
                    "validation_results": {
                        "is_valid": False,
                        "feedback": f"스키마 검색 중 오류가 발생했습니다: {str(e)}",
                        "suggested_actions": ["retry_search"],
                        "relevant_schemas": []
                    }
                }

        # 3. SQL 생성 노드
        def generate_sql(state: WorkflowState) -> WorkflowState:
            """SQL 생성 노드"""
            # 스키마 검증 재확인
            if not state["validation_results"].get("is_valid") or \
                    not state["validation_results"].get("relevant_schemas"):
                return {
                    **state,
                    "current_step": "complete",
                    "sql": "",
                    "feedback": "관련된 스키마가 없어 SQL을 생성할 수 없습니다."
                }

            sql_response = self.sql_generator.generate_sql(
                question=state["query"],
                schema_info=state["search_results"]
            )

            if "error" in sql_response:
                return {
                    **state,
                    "current_step": "complete",
                    "sql": "",
                    "feedback": sql_response["error"]
                }

            return {
                **state,
                "current_step": "validate_sql",
                "sql": sql_response["sql"]
            }

        # 3.5. SQL 검증 노드
        def validate_sql(state: WorkflowState) -> WorkflowState:
            """SQL 검증 노드"""
            if not state.get("sql"):
                return {
                    **state,
                    "current_step": "complete",
                    "validation_results": {
                        "is_valid": False,
                        "feedback": "SQL이 생성되지 않았습니다."
                    }
                }

            # LangChain의 SQLValidityChecker를 사용한 검증
            validation_result = self.sql_validator.validate(
                state["sql"],
                state.get("search_results", {})
            )

            if not validation_result["is_valid"]:
                return {
                    **state,
                    "current_step": "complete",
                    "validation_results": validation_result,
                    "feedback": "SQL 검증 실패: " + ", ".join(validation_result.get("errors", [])),
                    "suggested_actions": validation_result.get("suggestions", [])
                }

            return {
                **state,
                "current_step": "execute_sql",
                "validation_results": validation_result
            }

        # 4. SQL 실행 노드
        def execute_sql(state: WorkflowState) -> WorkflowState:
            """SQL 실행 노드"""
            # SQL이 비어있는 경우 실행하지 않음
            if not state.get("sql"):
                return {
                    **state,
                    "current_step": "complete",
                    "query_results": [],
                    "feedback": "SQL이 생성되지 않아 실행할 수 없습니다."
                }

            results = self.redshift_manager.execute_query(state["sql"])

            return {
                **state,
                "current_step": "handle_feedback",
                "query_results": results or []
            }

        # 5. 피드백 처리 노드
        def handle_feedback(state: WorkflowState) -> WorkflowState:
            """피드백 처리 노드"""
            if state.get("feedback_requested", False):
                feedback_result = self.feedback_handler.save_feedback(state)
                return {
                    **state,
                    "current_step": "complete",
                    "feedback_result": feedback_result
                }
            return {
                **state,
                "current_step": "complete",
                "feedback_result": {"success": False, "message": "피드백이 요청되지 않았습니다."}
            }

        # 6. 완료 노드
        def complete(state: WorkflowState) -> WorkflowState:
            """완료 노드 - 최종 상태 정리 및 후처리"""
            try:
                # 실행 시간 기록
                end_time = datetime.now()
                execution_time = (end_time - datetime.fromisoformat(state["metadata"]["start_time"])).total_seconds()

                # 메타데이터 업데이트
                updated_metadata = {
                    **state["metadata"],
                    "end_time": end_time.isoformat(),
                    "execution_time": execution_time,
                    "final_step": state["current_step"],
                    "success": bool(state.get("sql") and state.get("query_results")),
                }

                # 성능 메트릭 추가
                if "performance_metrics" not in updated_metadata:
                    updated_metadata["performance_metrics"] = {}

                updated_metadata["performance_metrics"].update({
                    "total_execution_time": execution_time,
                    "has_results": bool(state.get("query_results")),
                    "result_count": len(state.get("query_results", [])),
                    "has_error": bool(state.get("validation_results", {}).get("is_valid") is False)
                })

                # 최종 상태 반환
                return {
                    **state,
                    "current_step": "completed",  # 상태를 'completed'로 변경
                    "metadata": updated_metadata,
                    # 선택적으로 불필요한 중간 데이터 정리
                    "messages": [msg for msg in state.get("messages", []) if isinstance(msg, (HumanMessage, AIMessage))],
                    # 필요한 경우 에러 정보 포함
                    "error": state.get("validation_results", {}).get("feedback") if not state["validation_results"].get("is_valid", True) else None
                }

            except Exception as e:
                # 에러가 발생하더라도 기본 상태는 반환
                return {
                    **state,
                    "current_step": "completed",
                    "metadata": {
                        **state.get("metadata", {}),
                        "error": str(e),
                        "end_time": datetime.now().isoformat()
                    }
                }

        # 노드 등록 및 엣지 설정
        workflow.add_node("analyze_intent", analyze_intent)
        workflow.add_node("search_schema", search_schema)
        workflow.add_node("generate_sql", generate_sql)
        workflow.add_node("validate_sql", validate_sql)
        workflow.add_node("execute_sql", execute_sql)
        workflow.add_node("handle_feedback", handle_feedback)
        workflow.add_node("complete", complete)

        workflow.set_entry_point("analyze_intent")
        workflow.add_edge("analyze_intent", "search_schema")
        workflow.add_edge("search_schema", "generate_sql")
        workflow.add_edge("generate_sql", "validate_sql")
        workflow.add_edge("validate_sql", "execute_sql")
        workflow.add_edge("execute_sql", "handle_feedback")
        workflow.add_edge("handle_feedback", "complete")

        return workflow.compile()

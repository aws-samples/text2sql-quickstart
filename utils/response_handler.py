from typing import Dict, Any
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage

class ResponseHandler:
    @staticmethod
    def format_response(workflow_state: Dict[str, Any]) -> Dict[str, Any]:
        """워크플로우 결과를 응답 형식으로 변환"""
        validation_results = workflow_state.get("validation_results", {})

        if not validation_results.get("is_valid", True):
            return {
                "success": False,
                "feedback": validation_results.get("feedback", "처리 중 문제가 발생했습니다."),
                "suggested_actions": validation_results.get("suggested_actions", ["rephrase_question"]),
                "intent": workflow_state.get("intent", {}),
                "search_results": workflow_state.get("search_results", {}),
                "metadata": workflow_state.get("metadata", {})
            }

        return {
            "success": True,
            "sql": workflow_state.get("sql", ""),
            "results": workflow_state.get("query_results", []),
            "search_results": workflow_state.get("search_results", {}),
            "intent": workflow_state.get("intent", {}),
            "metadata": workflow_state.get("metadata", {}),
            "messages": [msg.content for msg in workflow_state.get("messages", [])
                         if isinstance(msg, AIMessage)]
        }
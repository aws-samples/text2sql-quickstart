from typing import TypedDict, List, Union, Dict
from langchain_core.messages import HumanMessage, AIMessage

class ValidationResult(TypedDict):
    """SQL 검증 결과"""
    is_valid: bool
    errors: List[str]
    suggestions: List[str]

class WorkflowState(TypedDict):
    """워크플로우 상태 관리"""
    messages: List[Union[HumanMessage, AIMessage]]
    current_step: str
    query: str
    intent: Dict
    search_results: Dict
    validation_results: Dict
    sql: str
    sql_validation: ValidationResult
    query_results: List[Dict]
    metadata: Dict
    feedback_requested: bool
    feedback_result: Dict
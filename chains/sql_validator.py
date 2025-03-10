from typing import Dict, Any, Optional
from datetime import datetime
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_core.language_models import BaseLanguageModel
from langchain_aws import BedrockLLM

class SQLValidator:
    def __init__(self, llm: Optional[BedrockLLM] = None, redshift_manager = None):
        """SQL 검증기 초기화"""
        self.llm = llm
        self.redshift_manager = redshift_manager
        self.db = None
        if redshift_manager and hasattr(redshift_manager, 'db'):
            self.db = redshift_manager.db
        self.validation_cache = {}  # 검증 결과 캐시

    def validate(self, sql: str, database_schema: Dict = None) -> Dict[str, Any]:
        """SQL 쿼리 검증"""
        try:
            # 캐시된 검증 결과가 있는지 확인
            cache_key = f"{sql}_{hash(str(database_schema))}"
            if cache_key in self.validation_cache:
                return self.validation_cache[cache_key]

            # 기본 검사: DML 작업 여부
            dml_check = self._check_dml_operations(sql)
            if not dml_check["is_valid"]:
                self.validation_cache[cache_key] = dml_check
                return dml_check

            # 데이터베이스 연결이 있는 경우 기본적인 SQL 구문 검사
            if self.db:
                try:
                    # 실제로 쿼리를 실행하지 않고 구문만 검사
                    self.db.run(f"EXPLAIN {sql}")
                except Exception as e:
                    result = {
                        "is_valid": False,
                        "errors": [f"SQL 구문 오류: {str(e)}"],
                        "suggestions": ["SQL 문법을 확인하고 다시 시도해주세요."],
                        "timestamp": datetime.now().isoformat()
                    }
                    self.validation_cache[cache_key] = result
                    return result

            # 성능 관련 검사
            performance_check = self._check_performance_issues(sql)
            if not performance_check["is_valid"]:
                self.validation_cache[cache_key] = performance_check
                return performance_check

            result = {
                "is_valid": True,
                "errors": [],
                "suggestions": [],
                "timestamp": datetime.now().isoformat()
            }
            
            # 결과 캐시에 저장
            self.validation_cache[cache_key] = result
            return result

        except Exception as e:
            return {
                "is_valid": False,
                "errors": [str(e)],
                "suggestions": ["SQL 문법을 확인하고 다시 시도해주세요."],
                "timestamp": datetime.now().isoformat()
            }

    def _check_dml_operations(self, sql: str) -> Dict[str, Any]:
        """DML 작업 여부 검증"""
        sql_upper = sql.upper()
        dml_keywords = ['INSERT', 'UPDATE', 'DELETE']

        # 전체 쿼리에서 DML 키워드 검사
        if any(keyword in sql_upper.split() for keyword in dml_keywords):
            return {
                "is_valid": False,
                "errors": ["데이터 수정 쿼리(INSERT, UPDATE, DELETE)는 허용되지 않습니다"],
                "suggestions": ["읽기 전용 쿼리(SELECT)만 사용 가능합니다"]
            }

        return {
            "is_valid": True,
            "errors": [],
            "suggestions": []
        }

    def _check_performance_issues(self, sql: str) -> Dict[str, Any]:
        """성능 관련 기본 검사"""
        sql_upper = sql.upper()
        issues = []
        suggestions = []

        # 전체 테이블 스캔 가능성 검사
        if "SELECT *" in sql_upper:
            issues.append("전체 컬럼 선택은 성능에 영향을 줄 수 있습니다")
            suggestions.append("필요한 컬럼만 명시적으로 선택하세요")

        # LIKE 연산자 사용 패턴 검사
        if "LIKE '%'" in sql_upper or "LIKE '%_'" in sql_upper:
            issues.append("앞쪽 와일드카드 LIKE 검색은 성능이 저하될 수 있습니다")
            suggestions.append("가능한 경우 뒤쪽 와일드카드만 사용하세요")

        # Cross Join 검사
        if "CROSS JOIN" in sql_upper:
            issues.append("CROSS JOIN은 성능에 심각한 영향을 줄 수 있습니다")
            suggestions.append("INNER JOIN이나 LEFT JOIN 사용을 고려하세요")

        if issues:
            return {
                "is_valid": False,
                "errors": issues,
                "suggestions": suggestions
            }

        return {
            "is_valid": True,
            "errors": [],
            "suggestions": []
        }

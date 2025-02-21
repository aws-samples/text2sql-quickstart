from typing import Dict, Any, Tuple
import json
import time
from datetime import datetime
import streamlit as st
from langchain.chains.question_answering.map_reduce_prompt import messages
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain.callbacks import StreamingStdOutCallbackHandler
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_aws import BedrockLLM
import boto3
from pyarrow.jvm import schema
from prompts import load_prompt, format_prompt

from config import AWS_REGION, BEDROCK_MODELS


class SQLGenerator:
    def __init__(self):
        """SQL 생성기 초기화"""
        self.client = boto3.client(
            'bedrock-runtime',
            region_name=AWS_REGION
        )
        self.conversation_history = []  # 대화 기록 저장
        self.max_retries = 4
        self.base_delay = 10  # 기본 대기 시간 (초)
        self.last_trim_time = datetime.now()  # 마지막 trim 시간 기록
        self.system_prompt_initialized = False  # 시스템 프롬프트 초기화 상태
        
        # 프롬프트 로드
        self.prompts = load_prompt('sql', 'generator')
        if not self.prompts:
            raise ValueError("SQL 생성기 프롬프트를 로드할 수 없습니다.")
        
        # 초기 시스템 프롬프트 설정
        self._initialize_system_prompt()

    def _invoke_bedrock(self, new_message: str, keep_history: bool = True) -> str:
        """Bedrock API 호출 (대화 기록 유지 및 재시도 로직 포함)"""
        for attempt in range(self.max_retries):
            try:
                # 이전 메시지가 user 메시지인 경우, assistant 응답이 필요
                if self.conversation_history and self.conversation_history[-1]["role"] == "user":
                    messages_to_send = self.conversation_history
                else:
                    # 새 메시지 추가
                    messages_to_send = self.conversation_history + [{
                        "role": "user",
                        "content": new_message
                    }]

                # API 요청
                response = self.client.invoke_model(
                    modelId=BEDROCK_MODELS['cross_claude'],
                    contentType="application/json",
                    accept="application/json",
                    body=json.dumps({
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 20000,
                        "messages": messages_to_send,
                        "temperature": 0,
                        "top_p": 0.9
                    })
                )

                response_body = json.loads(response.get('body').read())
                assistant_message = response_body.get('content', [{}])[0].get('text', '')

                # 응답 저장
                if keep_history:
                    if messages_to_send != self.conversation_history:
                        self.conversation_history = messages_to_send
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": assistant_message
                    })

                # 응답이 제대로 되었는지 확인
                if assistant_message.strip():
                    return assistant_message
                else:
                    raise ValueError("Bedrock API에서 유효한 응답을 받지 못했습니다.")

            except Exception as e:
                if "ThrottlingException" in str(e):
                    if attempt < self.max_retries - 1:
                        wait_time = self.base_delay * (1.2 ** attempt)
                        st.warning(f"API 호출 제한으로 인해 대기 중... {wait_time:.1f}초 후 재시도 ({attempt + 1}/{self.max_retries})")
                        time.sleep(wait_time)
                        continue

                st.error(f"Bedrock API 호출 중 오류 발생: {str(e)}")
                if attempt < self.max_retries - 1:
                    wait_time = self.base_delay * (2 ** attempt)
                    st.warning(f"재시도 중... ({attempt + 1}/{self.max_retries})")
                    time.sleep(wait_time)
                    continue
                raise

        raise Exception("최대 재시도 횟수를 초과했습니다.")

    def analyze_intent(self, question: str) -> Dict[str, Any]:
        """자연어 질문을 분석하여 의도 파악"""
        try:
            # 초기화가 필요한 경우
            if not self.conversation_history:
                # 초기 지시사항 전송
                self._invoke_bedrock(
                    self.prompts['intent_analysis']['system'],
                    keep_history=True
                )

            # 질문 분석 요청
            response_text = self._invoke_bedrock(question, keep_history=True)

            try:
                # JSON 응답 파싱
                parsed_response = json.loads(response_text)
                parsed_response["original_question"] = question
                return parsed_response

            except json.JSONDecodeError:
                return {
                    "objective": "unknown",
                    "target_entities": [],
                    "conditions": [],
                    "time_context": "",
                    "analysis": "Failed to parse response",
                    "original_question": question
                }

        except Exception as e:
            st.error(f"의도 분석 중 오류가 발생했습니다: {str(e)}")
            return {
                "error": str(e),
                "original_question": question,
                "objective": "unknown",
                "target_entities": [],
                "conditions": [],
                "time_context": "",
                "analysis": f"Error occurred: {str(e)}"
            }

    def _initialize_system_prompt(self):
        """시스템 프롬프트 초기화"""
        if not self.system_prompt_initialized:
            self._invoke_bedrock(
                self.prompts['sql_generation']['system'],
                keep_history=True
            )
            self.system_prompt_initialized = True

    def generate_sql(self, question: str, schema_info: Dict) -> Dict[str, Any]:
        """자연어 질문을 SQL로 변환"""
        try:
            sql_generate_prompt = format_prompt(
                self.prompts['sql_generation']['prompt'],
                question=question,
                tables=schema_info['schema_info']['tables'],
                related_tables=schema_info['schema_info']['related_tables'],
                sample_queries=schema_info['sample_queries']
            )

            # 주기적으로만 토큰 제한 관리 수행 (10분 간격)
            current_time = datetime.now()
            if (current_time - self.last_trim_time).total_seconds() > 600:
                self.trim_conversation_history()
                self.last_trim_time = current_time

            # 스키마 정보와 질문 전송
            response_text = self._invoke_bedrock(sql_generate_prompt, keep_history=True)

            try:
                return json.loads(response_text, strict=False)
            except json.JSONDecodeError:
                return {
                    "error": "Failed to parse SQL generation response",
                    "sql": "",
                    "explanation": {
                        "korean": "SQL 생성 중 오류가 발생했습니다.",
                        "english": "Error occurred during SQL generation."
                    }
                }

        except Exception as e:
            st.error(f"SQL 생성 중 오류가 발생했습니다: {str(e)}")
            return {
                "error": str(e),
                "sql": "",
                "explanation": {
                    "korean": f"오류: {str(e)}",
                    "english": f"Error: {str(e)}"
                }
            }

    def refine_sql(self, sql: str, feedback: str) -> Dict[str, Any]:
        """SQL 쿼리 개선"""
        try:
            # 토큰 제한 관리
            self.trim_conversation_history()

            prompt = format_prompt(
                self.prompts['sql_refinement']['prompt'],
                sql=sql,
                feedback=feedback
            )

            response_text = self._invoke_bedrock(prompt, keep_history=True)

            try:
                return json.loads(response_text, strict=False)
            except json.JSONDecodeError:
                return {
                    "error": "Failed to parse SQL refinement response",
                    "sql": sql,
                    "explanation": {
                        "korean": "SQL 개선 중 오류가 발생했습니다.",
                        "english": "Error occurred during SQL refinement."
                    }
                }

        except Exception as e:
            st.error(f"SQL 개선 중 오류가 발생했습니다: {str(e)}")
            return {
                "error": str(e),
                "sql": sql,
                "explanation": {
                    "korean": f"오류: {str(e)}",
                    "english": f"Error: {str(e)}"
                }
            }

    def validate_sql(self, sql: str) -> Dict[str, Any]:
        """생성된 SQL의 유효성 검사"""
        try:
            prompt = format_prompt(
                self.prompts['sql_validation']['prompt'],
                sql=sql
            )

            response_text = self._invoke_bedrock(prompt, keep_history=True)

            try:
                return json.loads(response_text)
            except json.JSONDecodeError:
                return {
                    "is_valid": False,
                    "analysis": {
                        "korean": "SQL 검증 결과를 파싱할 수 없습니다.",
                        "english": "Could not parse SQL validation results."
                    },
                    "issues": ["Parsing error"]
                }

        except Exception as e:
            return {
                "is_valid": False,
                "error": str(e),
                "analysis": {
                    "korean": f"검증 중 오류 발생: {str(e)}",
                    "english": f"Error during validation: {str(e)}"
                }
            }

    def get_conversation_history(self) -> list:
        """현재 대화 기록 반환"""
        return self.conversation_history

    def get_token_count(self) -> int:
        """현재 대화 기록의 대략적인 토큰 수 계산"""
        # 간단한 휴리스틱: 단어 수 * 1.3
        total_text = " ".join([msg["content"] for msg in self.conversation_history])
        return int(len(total_text.split()) * 1.3)

    def trim_conversation_history(self, max_tokens: int = 8000):
        """대화 기록을 최대 토큰 수에 맞게 조정"""
        while self.get_token_count() > max_tokens and len(self.conversation_history) > 2:
            # 시스템 메시지는 유지하고 가장 오래된 대화 쌍 제거
            self.conversation_history.pop(1)  # user message
            if len(self.conversation_history) > 1:
                self.conversation_history.pop(1)  # assistant message

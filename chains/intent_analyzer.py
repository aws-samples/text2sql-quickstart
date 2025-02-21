# chains/intent_analyzer.py
from typing import Dict, Any, List, Optional
import json
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from config import AWS_REGION, BEDROCK_MODELS
from langchain_aws import BedrockLLM
import boto3
import streamlit as st
from prompts import load_prompt, format_prompt
import time

class IntentAnalyzer:
    def __init__(self, llm):
        self.llm = llm
        self.client = boto3.client('bedrock-runtime', region_name=AWS_REGION)
        # 프롬프트 템플릿 로드
        self.prompts = load_prompt('sql', 'analyzer')
        self.max_retries = 4
        if not self.prompts:
            raise ValueError("의도 분석기 프롬프트를 로드할 수 없습니다.")

    def analyze_intent(self, query: str) -> Dict[str, Any]:
        """사용자 질의 의도 분석"""

        for attempt in range(self.max_retries):
            try:
                # 메시지 구성
                messages = [
                    {
                        "role": "user",
                        "content": format_prompt(self.prompts['intent_analyzer'], query=query)
                    }
                ]

                # Bedrock API 호출
                response = self.client.invoke_model(
                    modelId=BEDROCK_MODELS['cross_claude'],
                    contentType="application/json",
                    accept="application/json",
                    body=json.dumps({
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 2000,
                        "messages": messages,
                        "temperature": 0,
                        "top_p": 0.9
                    })
                )

                response_body = json.loads(response.get('body').read())
                content = response_body.get('content', [{}])[0].get('text', '')

                # JSON 추출 및 파싱
                try:
                    start_idx = content.find('{')
                    end_idx = content.rfind('}') + 1
                    if start_idx != -1 and end_idx != -1:
                        json_str = content[start_idx:end_idx]
                        intent_data = json.loads(json_str)
                    else:
                        raise ValueError("JSON 형식의 응답을 찾을 수 없습니다.")

                    # 기본값 설정으로 필수 필드 보장
                    intent_data.setdefault('objective', 'unknown')
                    intent_data.setdefault('target_entities', [])
                    intent_data.setdefault('conditions', [])
                    intent_data.setdefault('time_context', '')
                    intent_data.setdefault('aggregation', False)
                    intent_data.setdefault('analysis', '')

                    return intent_data

                except json.JSONDecodeError as e:
                    st.error(f"JSON 파싱 오류: {str(e)}")
                    st.write("Raw response:", content)
                    return {
                        "objective": "unknown",
                        "target_entities": [],
                        "conditions": [],
                        "time_context": "",
                        "aggregation": False,
                        "analysis": "JSON 파싱 오류 발생"
                    }

            except Exception as e:
                if "ThrottlingException" in str(e):
                    if attempt < self.max_retries - 1:
                        wait_time = self.base_delay * (1.2 ** attempt)
                        st.warning(f"API 호출 제한으로 인해 대기 중... {wait_time:.1f}초 후 재시도 ({attempt + 1}/{self.max_retries})")
                        time.sleep(wait_time)
                        continue

                st.error(f"의도 분석 중 오류 발생: {str(e)}")
                return {
                    "objective": "unknown",
                    "target_entities": [],
                    "conditions": [],
                    "time_context": "",
                    "aggregation": False,
                    "analysis": f"오류 발생: {str(e)}"
                }

    def validate_intent(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        """분석된 의도의 유효성 검증"""
        try:
            if not intent or "error" in intent:
                return {
                    "is_valid": False,
                    "feedback": "의도 분석 중 오류가 발생했습니다.",
                    "suggested_actions": ["rephrase_question"]
                }

            # 필수 필드 검증
            if not intent.get("objective") or not intent.get("target_entities"):
                return {
                    "is_valid": False,
                    "feedback": "질문의 목적이나 대상을 파악할 수 없습니다.",
                    "suggested_actions": ["clarify_intent"]
                }

            # 의도의 구체성 검증
            if intent["objective"] == "unknown" or not intent["target_entities"]:
                return {
                    "is_valid": False,
                    "feedback": "질문이 너무 모호합니다. 좀 더 구체적으로 질문해 주세요.",
                    "suggested_actions": ["be_more_specific"]
                }

            return {
                "is_valid": True,
                "feedback": "의도가 명확하게 파악되었습니다.",
                "suggested_actions": []
            }

        except Exception as e:
            return {
                "is_valid": False,
                "feedback": f"의도 검증 중 오류가 발생했습니다: {str(e)}",
                "suggested_actions": ["rephrase_question"]
            }

    def analyze_and_validate(self, query: str) -> Dict[str, Any]:
        """사용자 질의 의도 분석 및 유효성 검증"""
        try:
            # 의도 분석
            intent = self.analyze_intent(query)

            # 의도 검증
            validation = self.validate_intent(intent)

            return {
                "is_valid": validation["is_valid"],
                "intent": intent,
                "feedback": validation["feedback"],
                "suggested_actions": validation["suggested_actions"]
            }

        except Exception as e:
            return {
                "is_valid": False,
                "intent": {},
                "feedback": f"의도 분석 중 오류가 발생했습니다: {str(e)}",
                "suggested_actions": ["rephrase_question"]
            }

import copy
import os
from random import sample

import boto3
import json
import time
import yaml
from typing import Dict, List, Optional
from pathlib import Path

import streamlit as st
from config import AWS_REGION, BEDROCK_MODELS
from langchain_aws import BedrockLLM
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

class SchemaAugmenter:
    def __init__(self, max_retries: int = 3, base_delay: int = 2):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.client = boto3.client('bedrock-runtime', region_name=AWS_REGION)
        self.model_id = BEDROCK_MODELS['cross_claude']
        self.prompts = self._load_prompts()

    def _load_prompts(self) -> Dict:
        """프롬프트 YAML 파일 로드"""
        from prompts import load_prompt
        
        prompts = load_prompt('schema', 'augmentation')
        if prompts is None:
            st.error("프롬프트 파일을 로드할 수 없습니다.")
            return {}
        return prompts

    def _get_table_analysis_prompt(self, table_info: Dict) -> str:
        """테이블 분석 프롬프트 생성"""
        from prompts import format_prompt
        
        prompt_template = self.prompts.get('table_analysis', {}).get('prompt', '')
        return format_prompt(prompt_template, 
            table_info=json.dumps(table_info, ensure_ascii=False, indent=2)
        )

    def _get_column_analysis_prompt(self, column_info: Dict) -> str:
        """컬럼 분석 프롬프트 생성"""
        from prompts import format_prompt
        
        prompt_template = self.prompts.get('column_analysis', {}).get('prompt', '')
        return format_prompt(prompt_template,
            column_info=json.dumps(column_info, ensure_ascii=False, indent=2)
        )

    def _get_query_analysis_prompt(self, query_info: Dict) -> str:
        """쿼리 분석 프롬프트 생성"""
        from prompts import format_prompt
        
        prompt_template = self.prompts.get('query_analysis', {}).get('prompt', '')
        return format_prompt(prompt_template,
            query_info=json.dumps(query_info, ensure_ascii=False, indent=2)
        )

    def _get_glossary_analysis_prompt(self, term_info: Dict) -> str:
        """용어 분석 프롬프트 생성"""
        from prompts import format_prompt
        
        prompt_template = self.prompts.get('glossary_analysis', {}).get('prompt', '')
        return format_prompt(prompt_template,
            term_info=json.dumps(term_info, ensure_ascii=False, indent=2)
        )

    def _call_bedrock(self, prompt: str, max_retries: int = 3) -> Dict:
        """Bedrock을 직접 호출하여 응답을 받습니다."""
        for attempt in range(max_retries):
            try:
                # Bedrock 요청 형식
                request = {
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": prompt
                                }
                            ]
                        }
                    ],
                    "max_tokens": 20000,
                    "temperature": 0.0,
                    "top_k": 250,
                    "top_p": 1.0,
                    "anthropic_version": "bedrock-2023-05-31"
                }

                # Bedrock 호출
                response = self.client.invoke_model(
                    modelId=self.model_id,
                    body=bytes(json.dumps(request), 'utf-8')
                )

                # 응답 처리
                response_body = json.loads(response['body'].read().decode('utf-8'))
                
                # content 필드에서 text 추출
                if 'content' in response_body:
                    content = response_body['content']
                    if isinstance(content, list) and content:
                        text = content[0].get('text', '')
                        # JSON 문자열에서 실제 JSON 부분만 추출
                        try:
                            # JSON 시작과 끝 위치 찾기
                            start_idx = text.find('{')
                            end_idx = text.rfind('}') + 1
                            if start_idx != -1 and end_idx != 0:
                                json_str = text[start_idx:end_idx]
                                return json.loads(json_str)
                            elif text.startswith('[') and text.rstrip().endswith(']'):
                                return json.loads(text)
                        except json.JSONDecodeError as e:
                            st.warning(f"\n=== JSON 파싱 에러 ===\n{str(e)}")
                            return {"error": "JSON 파싱 실패", "raw_text": text}

                st.error("응답에서 텍스트를 추출할 수 없습니다.")
                return {"error": "텍스트 추출 실패", "raw_response": response_body}

            except Exception as e:
                if attempt == max_retries - 1:
                    st.error(f"Bedrock 호출 실패 (최대 재시도 횟수 초과): {str(e)}")
                    return {"error": str(e)}

                wait_time = self.base_delay * (2 ** attempt)
                st.warning(f"오류 발생, {wait_time}초 후 재시도 ({attempt + 1}/{max_retries})")
                time.sleep(wait_time)

        return {"error": "모든 재시도 실패"}

    def augment_query(self, sample_queries: list) -> list:
        """쿼리 증강"""
        try:
            result = []

            # 쿼리 분석
            st.info("📝 샘플 쿼리 분석 중...")
            for sample_query in sample_queries:
                query_analysis = self._call_bedrock(self._get_query_analysis_prompt(sample_query))
                if not query_analysis.get('error'):
                    result.append(query_analysis)

            st.success("✅ 쿼리 증강이 완료되었습니다!")

            return result

        except Exception as e:
            st.error(f"쿼리 증강 중 오류가 발생했습니다: {str(e)}")
            return sample_queries

    def augment_schema(self, table_info: Dict) -> Dict:
        """스키마 정보 증강"""
        try:
            augmented_info = copy.deepcopy(table_info)

            # 테이블 분석
            st.info("📊 테이블 분석 중...")
            table_analysis = self._call_bedrock(self._get_table_analysis_prompt(table_info))
            if not table_analysis.get('error'):
                augmented_info["augmented_table_info"] = table_analysis

            # 컬럼 분석
            st.info("🔍 컬럼 분석 중...")
            for i, column in enumerate(augmented_info.get("columns", [])):
                column_analysis = self._call_bedrock(self._get_column_analysis_prompt(column))
                if not column_analysis.get('error'):
                    augmented_info["columns"][i]["augmented_column_info"] = column_analysis

            st.success("✅ 스키마 증강이 완료되었습니다!")
            return augmented_info

        except Exception as e:
            st.error(f"스키마 증강 중 오류가 발생했습니다: {str(e)}")
            return table_info

    def augment_all_tables(self, schema_data: Dict) -> Dict:
        """Augment all tables in the schema"""
        try:
            augmented_schema = copy.deepcopy(schema_data)

            if not isinstance(augmented_schema, dict):
                st.error("잘못된 스키마 데이터 형식입니다.")
                return schema_data

            if 'database_schema' not in augmented_schema:
                st.error("스키마 데이터에 'database_schema' 키가 없습니다.")
                return schema_data

            if 'tables' not in augmented_schema['database_schema']:
                st.error("database_schema에 'tables' 키가 없습니다.")
                return schema_data

            tables = augmented_schema['database_schema']['tables']
            if not isinstance(tables, list):
                st.error(f"잘못된 테이블 데이터 형식입니다: {type(tables)}")
                return schema_data

            sample_queries = augmented_schema['database_schema']['sample_queries']

            total_tables = len(tables)
            for i, table in enumerate(tables, 1):
                st.write(f"테이블 처리 중 ({i}/{total_tables}): {table.get('table_name', 'unknown')}")
                with st.spinner(f"테이블 증강 중... {table.get('table_name', 'unknown')}"):
                    augmented_table = self.augment_schema(table)
                    augmented_schema['database_schema']['tables'][i-1] = augmented_table

            with st.spinner("쿼리 증강 중..."):
                augmented_queries = self.augment_query(sample_queries)
                augmented_schema['database_schema']['augmented_queries'] = augmented_queries

            return augmented_schema

        except Exception as e:
            st.error(f"스키마 증강 중 오류가 발생했습니다: {str(e)}")
            st.write("Error Details:", e)
            return schema_data

    def generate_additional_queries(self, table_info: Dict, existing_queries: List[Dict], num_queries: int = 30) -> List[Dict]:
        """추가 샘플 쿼리 생성"""
        try:
            # 프롬프트 생성
            from prompts import format_prompt
            
            prompt_template = self.prompts.get('additional_queries', {}).get('prompt', '')
            prompt = format_prompt(prompt_template,
                num_queries=num_queries,
                table_info=json.dumps(table_info, ensure_ascii=False, indent=2),
                existing_queries=json.dumps(existing_queries, ensure_ascii=False, indent=2)
            )

            # Bedrock 호출
            response = self._call_bedrock(prompt)

            # 응답이 리스트인지 확인
            if isinstance(response, list):
                # 응답 검증
                validated_queries = []
                for query in response:
                    if isinstance(query, dict) and 'natural_language' in query and 'sql' in query:
                        validated_queries.append(query)

                if validated_queries:
                    st.success(f"✅ {len(validated_queries)}개의 새로운 쿼리가 생성되었습니다.")
                    return validated_queries
                else:
                    st.warning("생성된 쿼리가 올바른 형식이 아닙니다.")
            elif isinstance(response, dict) and 'error' in response:
                st.error(f"쿼리 생성 중 오류가 발생했습니다: {response['error']}")

            else:
                st.warning("쿼리 생성 결과가 올바른 형식이 아닙니다.")

        except Exception as e:
            st.error(f"쿼리 생성 중 오류가 발생했습니다: {str(e)}")
            st.write("Error details:", e)

        return []

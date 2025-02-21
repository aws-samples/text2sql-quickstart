import redshift_connector
from typing import Dict, Optional, Tuple
import streamlit as st
import boto3
import json
import time
import yaml
from pathlib import Path
from botocore.exceptions import ClientError
from config import REDSHIFT_CONFIG, AWS_REGION, BEDROCK_MODELS
from langchain_aws import BedrockLLM
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

class RedshiftManager:
    def __init__(self):
        self.config = REDSHIFT_CONFIG
        self.llm = BedrockLLM(
            model_id=BEDROCK_MODELS['cross_claude'],
            client=boto3.client('bedrock-runtime', region_name=AWS_REGION),
            streaming=False,
            model_kwargs={
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 20000,
                "temperature": 0.0,
                "top_k": 250,
                "top_p": 1.0,
            }
        )
        self.max_retries = 5
        self.base_delay = 2  # 초기 대기 시간 (초)

        self._set_search_path()

    def _set_search_path(self):
        """Redshift search_path를 gold로 설정"""
        try:
            conn = redshift_connector.connect(**self.config)
            cursor = conn.cursor()
            cursor.execute("SET search_path TO gold")
            conn.commit()
        except Exception as e:
            st.warning(f"search_path 설정 중 오류 발생: {str(e)}")
        finally:
            if 'conn' in locals():
                conn.close()

    def _load_prompt(self, prompt_path: str) -> str:
        """Load prompt from yaml file"""
        try:
            with open(prompt_path, 'r') as f:
                prompt_data = yaml.safe_load(f)
                return prompt_data['prompt']
        except Exception as e:
            st.error(f"프롬프트 로드 중 오류 발생: {str(e)}")
            return ""

    def _get_ddl_prompt(self, table_info: Dict) -> str:
        """Generate DDL generation prompt"""
        prompt_path = Path(__file__).parent.parent / 'prompts' / 'redshift' / 'ddl.yaml'
        prompt_template = self._load_prompt(str(prompt_path))
        return prompt_template.format(table_info=json.dumps(table_info, indent=2))

    def _call_bedrock(self, prompt: str, max_retries: int = 3) -> Tuple[bool, str]:
        """Call Bedrock API with retry mechanism"""
        for attempt in range(max_retries):
            try:
                response = self.llm.client.invoke_model(
                    modelId=BEDROCK_MODELS['cross_claude'],
                    contentType="application/json",
                    accept="application/json",
                    body=json.dumps({
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 20000,
                        "messages": [
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        "temperature": 0.0,
                        "top_k": 250,
                        "top_p": 1.0
                    })
                )

                response_body = json.loads(response.get('body').read())
                if 'content' in response_body:
                    return True, response_body['content'][0]['text'].strip()
                return False, "No content in response"

            except Exception as e:
                if attempt == max_retries - 1:
                    st.error(f"Bedrock 호출 실패 (최대 재시도 횟수 초과): {str(e)}")
                    return False, f"Failed to generate DDL: {str(e)}"

                wait_time = self.base_delay * (2 ** attempt)
                st.warning(f"오류 발생, {wait_time}초 후 재시도 ({attempt + 1}/{max_retries})")
                time.sleep(wait_time)

    def create_schema_if_not_exists(self) -> bool:
        """Create schema if it doesn't exist"""
        try:
            conn = redshift_connector.connect(**self.config)
            cursor = conn.cursor()

            # 스키마 존재 여부 확인
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 
                    FROM information_schema.schemata 
                    WHERE schema_name = 'gold'
                );
            """)
            schema_exists = cursor.fetchone()[0]

            if not schema_exists:
                st.info("🔄 'gold' 스키마가 존재하지 않습니다. 생성을 시작합니다...")
                cursor.execute("CREATE SCHEMA IF NOT EXISTS gold;")
                conn.commit()
                st.success("✅ 'gold' 스키마가 생성되었습니다!")

            return True

        except Exception as e:
            st.error(f"스키마 생성 중 오류가 발생했습니다: {str(e)}")
            return False

        finally:
            if 'conn' in locals():
                conn.close()

    def check_table_exists(self, table_name: str) -> bool:
        """Check if table exists in schema"""
        try:
            conn = redshift_connector.connect(**self.config)
            cursor = conn.cursor()

            cursor.execute(f"""
                SELECT EXISTS (
                    SELECT 1 
                    FROM information_schema.tables 
                    WHERE table_schema = 'gold'
                    AND table_name = '{table_name}'
                );
            """)

            exists = cursor.fetchone()[0]
            return exists

        except Exception as e:
            st.error(f"테이블 존재 여부 확인 중 오류가 발생했습니다: {str(e)}")
            return False

        finally:
            if 'conn' in locals():
                conn.close()

    def generate_ddl(self, table_info: Dict) -> Tuple[bool, str]:
        """Generate DDL using Bedrock"""
        prompt = self._get_ddl_prompt(table_info)
        chain = (
                RunnablePassthrough()
                | ChatPromptTemplate.from_messages([("human", "{prompt}")])
                | self.llm
                | StrOutputParser()
        )

        for attempt in range(self.max_retries):
            try:
                response = self._call_bedrock(prompt=prompt, max_retries=self.max_retries)
                return response
            except Exception as e:
                if attempt == self.max_retries - 1:
                    return False, f"Failed to generate DDL: {str(e)}"
                time.sleep(self.base_delay * (2 ** attempt))
                st.warning(f"Retry attempt {attempt + 1} of {self.max_retries}, waiting...")

        return False, "Failed to generate DDL after retries."

    def execute_ddl(self, ddl: str) -> bool:
        """Execute DDL statement"""
        try:
            conn = redshift_connector.connect(**self.config)
            cursor = conn.cursor()

            # DDL 실행 전 로깅
            st.code(ddl, language='sql')

            cursor.execute(ddl)
            conn.commit()
            return True

        except Exception as e:
            st.error(f"DDL 실행 중 오류가 발생했습니다: {str(e)}")
            return False

        finally:
            if 'conn' in locals():
                conn.close()

    def create_table_in_redshift(self, table_info: Dict) -> bool:
        """Create table in Redshift"""
        if not self.create_schema_if_not_exists():
            return False

        table_name = table_info['table_name']

        # 테이블 존재 여부 확인
        if self.check_table_exists(table_name):
            st.info(f"ℹ️ 테이블 '{table_name}'이(가) 이미 존재합니다.")
            return True

        try:
            # DDL 생성
            success, ddl = self.generate_ddl(table_info)
            if not success:
                st.error(f"DDL 생성 실패: {ddl}")
                return False

            # DDL 실행
            st.info(f"🔄 테이블 '{table_name}' 생성 중...")
            if self.execute_ddl(ddl):
                st.success(f"✅ 테이블 '{table_name}'이(가) 성공적으로 생성되었습니다!")
                return True
            return False

        except Exception as e:
            st.error(f"테이블 생성 중 오류가 발생했습니다: {str(e)}")
            return False

    def test_connection(self) -> bool:
        """Test Redshift connection"""
        try:
            conn = redshift_connector.connect(**self.config)
            conn.close()
            return True

        except Exception as e:
            st.error(f"Redshift 연결 실패: {str(e)}")
            return False

    def execute_query(self, query: str) -> Optional[list]:
        """Execute query and return results"""
        try:
            conn = redshift_connector.connect(**self.config)
            cursor = conn.cursor()

            cursor.execute("SET search_path TO gold")

            cursor.execute(query)
            results = cursor.fetchall()

            # 컬럼 이름 가져오기
            column_names = [desc[0] for desc in cursor.description]

            # 결과를 딕셔너리 리스트로 변환
            formatted_results = []
            for row in results:
                formatted_results.append(dict(zip(column_names, row)))

            return formatted_results

        except Exception as e:
            st.error(f"쿼리 실행 중 오류가 발생했습니다: {str(e)}")
            return None

        finally:
            if 'conn' in locals():
                conn.close()
        return []

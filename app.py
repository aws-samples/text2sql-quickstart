import streamlit as st
import json
import time
import pandas as pd
import boto3
from dateutil import parser
# import asyncio
from datetime import datetime
from typing import Any, Dict

# 커스텀 그래프 임포트
from graphs.workflow_state import WorkflowState
from graphs.search_flow import TextToSQLFlow

# 유틸리티 임포트
from utils.load_redshift import RedshiftManager
from utils.indice_opensearch import OpenSearchManager
from utils.augmentation import SchemaAugmenter
from utils.package_manager import PackageManager
from utils.schema_manager import SchemaManager
from utils.display_utils import DisplayManager
from utils.monitoring import PerformanceMonitor
from utils.data_generator import DataGenerator
from utils.style_loader import StyleLoader

# LangChain 관련 임포트
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_aws import BedrockLLM

# 설정 임포트
from config import AWS_REGION, BEDROCK_MODELS, OPENSEARCH_CONFIG

# 상수 정의
index_name = 'schema_info'
DEFAULT_TOP_K = 5

def init_session_state():
    """세션 상태 초기화"""
    if 'page' not in st.session_state:
        st.session_state.page = 'upload'
    if 'redshift_manager' not in st.session_state:
        st.session_state.redshift_manager = RedshiftManager()
    if 'opensearch_manager' not in st.session_state:
        st.session_state.opensearch_manager = OpenSearchManager()
    if 'schema_augmenter' not in st.session_state:
        st.session_state.schema_augmenter = SchemaAugmenter()
    if 'schema_manager' not in st.session_state:
        st.session_state.schema_manager = SchemaManager()
    if 'display_manager' not in st.session_state:
        st.session_state.display_manager = DisplayManager()
    if 'performance_monitor' not in st.session_state:
        st.session_state.performance_monitor = PerformanceMonitor()
    if 'sql_generator' not in st.session_state:
        from chains.sql_generator import SQLGenerator
        st.session_state.sql_generator = SQLGenerator()
    if 'package_manager' not in st.session_state:
        st.session_state.package_manager = PackageManager()
    if 'search_flow' not in st.session_state:
        st.session_state.search_flow = TextToSQLFlow(
            opensearch_manager=st.session_state.opensearch_manager,
            sql_generator=st.session_state.sql_generator,
            redshift_manager=st.session_state.redshift_manager,
            performance_monitor=st.session_state.performance_monitor,
            package_manager=st.session_state.package_manager,
            llm=BedrockLLM(
                model_id=BEDROCK_MODELS['cross_claude'],
                client=boto3.client('bedrock-runtime', region_name=AWS_REGION)
            )
        )
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    if 'data_generator' not in st.session_state:
        st.session_state.data_generator = DataGenerator()

def render_sidebar():
    """사이드바 렌더링"""
    with st.sidebar:
        st.title("🤖 Text to SQL")

        st.write("### 📊 Data Management")
        if st.button("Schema Upload", use_container_width=True,
                     help="Upload and manage database schemas"):
            st.session_state.page = 'upload'

        if st.button("Generate Test Data", use_container_width=True,
                     help="Generate and load test data into Redshift"):
            st.session_state.page = 'data_generation'

        st.write("### 🔄 Schema Enhancement")
        if st.button("Augment Schema", use_container_width=True,
                     help="Enhance schema with additional information"):
            st.session_state.page = 'augment'

        if st.button("Synonym Dictionary", use_container_width=True,
                     help="Manage synonym dictionary for improved query understanding"):
            st.session_state.page = 'synonym_dict'

        if st.button("Clear Indices", use_container_width=True,
                     help="Clear all OpenSearch indices"):
            st.session_state.page = 'clear_indices'

        st.write("### 💡 Query Generation")
        if st.button("Query Generator", use_container_width=True,
                     help="Generate SQL queries from natural language"):
            st.session_state.page = 'query'

        # 시스템 상태 표시
        st.write("### 🔧 System Status")
        system_status = check_system_status()
        for service, status in system_status.items():
            if status:
                st.success(f"✅ {service}: Connected")
            else:
                st.error(f"❌ {service}: Disconnected")

def check_system_status():
    """시스템 연결 상태 확인"""
    return {
        "Redshift": st.session_state.redshift_manager.test_connection(),
        "OpenSearch": st.session_state.opensearch_manager.test_connection()
    }

def process_schema_file(schema_content: Dict) -> bool:
    """스키마 파일 처리"""
    try:
        status_container = st.empty()
        progress_container = st.empty()

        with st.expander("🔍 처리 로그", expanded=True):
            log_container = st.empty()

            # 1. 스키마 증강 (아직 증강되지 않은 테이블만)
            status_container.info("🔄 스키마 증강 중...")
            augmented_schema = st.session_state.schema_augmenter.augment_all_tables(schema_content)

            # 2. Redshift 테이블 생성
            status_container.info("📝 Redshift 테이블 생성 중...")
            tables = augmented_schema['database_schema']['tables']
            total_tables = len(tables)

            for idx, table in enumerate(tables):
                progress = (idx + 1) / total_tables
                progress_container.progress(progress)
                log_container.write(f"테이블 처리 중: {table['table_name']}")

                if not st.session_state.redshift_manager.create_table_in_redshift(table):
                    status_container.error(f"❌ 테이블 생성 실패: {table['table_name']}")
                    return False

            # 3. 스키마 저장
            status_container.info("💾 스키마 정보 저장 중...")
            version_id = f"v_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            description = f"Initial schema upload at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            if not st.session_state.schema_manager.save_schema(
                    augmented_schema,
                    description=description,
                    version_id=version_id
            ):
                status_container.error("❌ 스키마 저장 실패")
                return False

            # 4. OpenSearch 인덱싱 (이미 증강된 데이터 사용)
            status_container.info("🔍 OpenSearch 인덱싱 중...")
            if not st.session_state.opensearch_manager.index_schema(augmented_schema, version_id):
                status_container.error("❌ 스키마 인덱싱 실패")
                return False

            status_container.success("✅ 스키마 처리가 완료되었습니다!")

            # 5. 스키마 정보 표시
            st.write("### 📊 Schema Details")
            st.session_state.display_manager.display_schema_info(augmented_schema)

            return True

    except Exception as e:
        st.session_state.display_manager.display_error(e, "스키마 처리 중 오류가 발생했습니다")
        return False

def render_upload_page():
    """스키마 업로드 페이지 렌더링"""
    st.header("📤 Schema Upload")

    # 스키마 히스토리 표시
    with st.expander("📚 Schema Version History", expanded=False):
        versions = st.session_state.schema_manager.get_schema_versions()
        if versions:
            st.session_state.display_manager.display_dataframe(
                pd.DataFrame(versions),
                "Schema Versions"
            )

            selected_version = st.selectbox(
                "Select version to load:",
                options=[v['version_id'] for v in versions],
                format_func=lambda x: f"{x} - {next(v['timestamp'] for v in versions if v['version_id'] == x)}"
            )

            if st.button("Load Selected Version"):
                schema = st.session_state.schema_manager.load_schema_version(selected_version)
                if schema:
                    st.session_state.display_manager.display_schema_info(schema)
        else:
            st.info("No version history available")

    # 새 스키마 업로드
    uploaded_file = st.file_uploader("Upload Schema JSON", type=['json'])
    if uploaded_file is not None:
        try:
            schema_content = json.load(uploaded_file)

            if st.button("Process Schema"):
                process_schema_file(schema_content)

            st.subheader("📄 Schema Preview")
            st.session_state.display_manager.display_json(schema_content)


        except Exception as e:
            st.session_state.display_manager.display_error(e, "파일 처리 중 오류가 발생했습니다")

def render_augment_page():
    """스키마 증강 페이지 렌더링"""
    st.header("🔄 Schema Augmentation")

    # 스키마 버전 목록 조회
    versions = st.session_state.schema_manager.get_schema_versions()

    if versions:
        st.session_state.display_manager.display_dataframe(
            pd.DataFrame(versions),
            "Available Versions"
        )

        selected_version = st.selectbox(
            "Select version to augment:",
            options=[v['version_id'] for v in versions],
            format_func=lambda x: (
                f"{x} - {next(v['timestamp'] for v in versions if v['version_id'] == x)} "
                f"({'Augmented' if next(v['type'] for v in versions if v['version_id'] == x) == 'augmented' else 'Base'})"
            )
        )

        if st.button("Generate Additional Queries", use_container_width=True):
            with st.spinner("Generating additional queries..."):
                # 선택된 스키마 버전 로드
                current_schema = st.session_state.schema_manager.load_schema_version(selected_version)

                if current_schema:
                    # 새로운 버전 ID 생성
                    new_version_id = f"v_{datetime.now().strftime('%Y%m%d_%H%M%S')}_aug"

                    # 기존 쿼리 로드
                    existing_queries = []
                    for table in current_schema['database_schema']['tables']:
                        existing_queries.extend(table.get('sample_queries', []))

                    # 추가 쿼리 생성
                    for table in current_schema['database_schema']['tables']:
                        new_queries = st.session_state.schema_augmenter.generate_additional_queries(
                            table, existing_queries
                        )
                        if new_queries:
                            table['sample_queries'] = table.get('sample_queries', []) + new_queries

                    # 증강된 스키마 저장
                    if st.session_state.schema_manager.save_schema(
                            current_schema,
                            schema_type="augmented",
                            version_id=new_version_id,
                            description=f"Additional queries generated from {selected_version} at {datetime.now()}"
                    ):
                        st.success(f"✅ Additional queries have been generated and saved as version {new_version_id}")

                        # OpenSearch 재색인
                        if st.session_state.opensearch_manager.index_sample_queries(current_schema, new_version_id):
                            st.success("✅ New queries have been indexed in OpenSearch successfully!")
                        else:
                            st.error("Failed to index new queries in OpenSearch")
                    else:
                        st.error("Failed to save augmented schema")
                else:
                    st.error("Failed to load schema version")
    else:
        st.info("No schema versions available. Please upload a schema first.")

def format_last_updated(last_updated):
    # ISO 형식의 날짜를 사람이 읽기 쉬운 형식으로 변환
    if isinstance(last_updated, datetime):
        return last_updated.strftime("%Y-%m-%d %H:%M:%S")
    else:
        dt = parser.isoparse(last_updated)
        return dt.strftime("%Y-%m-%d %H:%M:%S")

def render_synonym_dict():
    st.header("🔤 Synonym Dictionary Management")

    # 현재 도메인 정보 표시
    domain_name = OPENSEARCH_CONFIG.get('domain')
    st.subheader(f"Domain: {domain_name}")

    # 패키지 목록 표시
    st.subheader("Current Synonym Packages")
    packages = st.session_state.package_manager.describe_dictionaries(domain_name)

    if packages:
        for package in packages:
            with st.expander(f"패키지: {package['package_name']}", expanded=False):

                last_updated_formatted = format_last_updated(package['last_updated'])

                # 카드 스타일로 정보 표시
                st.markdown(f"### 패키지 ID: **{package['package_id']}**")
                st.markdown(f"**패키지 버전:** <span style='color: yellow;'>{package['package_version']}</span>", unsafe_allow_html=True)
                st.markdown(f"**최종 업데이트:** {last_updated_formatted}")
                st.markdown(f"**S3 버킷 이름:** {package['s3_bucket']}")
                st.markdown(f"**동의어 사전 이름:** {package['s3_key']}")

                # 패키지 업데이트 버튼
                if st.button("사전 업데이트", key=f"update_button_{package['package_id']}"):
                    st.session_state.update_package = package['package_id']

                # 패키지 삭제 버튼
                if st.button("사전 삭제", key=f"delete_button_{package['package_id']}"):
                    response = st.session_state.package_manager.delete_dictionary(
                        package_id=package['package_id'],
                        package_name=package['package_name'],
                        domain_name=domain_name
                    )

            # 패키지 업데이트 폼 (조건부 렌더링)
            if hasattr(st.session_state, 'update_package') and st.session_state.update_package == package['package_id']:
                st.subheader("동의어 사전 업데이트")
                update_file = st.file_uploader("Upload your synonym file", type=["txt"], key=f"file_uploader_{package['package_id']}")
                if st.button("Confirm Update", key=f"confirm_update_{package['package_id']}"):
                    if update_file:
                        response = st.session_state.package_manager.update_dictionary(
                            package_id=package['package_id'],
                            package_name=package['package_name'],
                            synonym_file=update_file
                        )
                        if response:
                            st.success(f"Package {st.session_state.update_package} updated successfully!")
                            del st.session_state.update_package
                    else:
                        st.warning("Please fill in all fields to update the package.")
    else:
        st.info("No packages found for this domain.")

    # 새 패키지 생성 버튼
    if st.button("Create New Package"):
        st.session_state.create_new_package = True

    # 새 패키지 생성 "모달"
    if 'create_new_package' in st.session_state and st.session_state.create_new_package:
        with st.form("new_package_form"):
            st.subheader("Create New Package")
            new_package_name = st.text_input("New Package Name")
            uploaded_file = st.file_uploader("Upload your synonym file", type=["txt"])

            submitted = st.form_submit_button("Create")
            if submitted:
                if new_package_name and uploaded_file:
                    response = st.session_state.package_manager.create_dictionary(
                        package_name=new_package_name,
                        synonym_file=uploaded_file
                    )
                    if response:
                        st.success(f"새로운 텍스트 사전 등록이 완료됐습니다.")
                        st.session_state.create_new_package = False

                else:
                    st.warning("Please fill in all fields to create a new package.")
            if st.form_submit_button("Cancel"):
                st.session_state.create_new_package = False

    # 전체 패키지 새로고침 버튼
    if st.button("Refresh All Packages"):
        # 여기에 모든 패키지 새로고침 로직 추가
        st.success("모든 패키지를 새롭게 불러왔습니다.")

def render_clear_indices_page():
    """인덱스 초기화 페이지 렌더링"""
    st.header("🗑️ Clear Indices")

    st.warning("⚠️ This action will remove all indices from OpenSearch!")
    st.info("This will clear all schema information and sample queries.")

    if st.button("Clear All Indices", type="primary", use_container_width=True):
        try:
            with st.spinner("Clearing indices..."):
                if st.session_state.opensearch_manager.clear_indices():
                    st.success("✅ All indices have been cleared successfully!")
                    time.sleep(2)
                else:
                    st.error("Failed to clear indices")

        except Exception as e:
            st.error(f"Error during clear operation: {str(e)}")

def process_query(user_query: str, search_flow, performance_monitor) -> Dict[str, Any]:
    """동기적으로 쿼리 처리"""
    workflow_op_id = performance_monitor.start_operation("complete_workflow")
    result = search_flow.execute(query=user_query)
    performance_monitor.end_operation(workflow_op_id, result)

    if "error" in result:
        return {
            "error": result["error"],
            "metadata": result.get("metadata", {})
        }
    return result

def render_query_page():
    """쿼리 생성 페이지 렌더링"""
    st.header("💡 Query Generator")

    # CSS 스타일 로드
    StyleLoader.load_chat_style()

    # 상태 초기화
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "input_key" not in st.session_state:
        st.session_state.input_key = 0
    if "debug_mode" not in st.session_state:
        st.session_state.debug_mode = False
    if "show_metrics" not in st.session_state:
        st.session_state.show_metrics = False

    def handle_input():
        """입력 필드 변경 처리"""
        input_key = f"user_input_{st.session_state.input_key}"
        if input_key in st.session_state and st.session_state[input_key].strip():
            user_input = st.session_state[input_key]
            st.session_state[input_key] = ""  # 입력 필드 초기화

            # 이미 동일한 메시지가 마지막에 있는지 확인
            if not st.session_state.chat_history or \
                    st.session_state.chat_history[-1].get("content") != user_input:
                # 사용자 입력 처리
                st.session_state.chat_history.append({
                    "role": "user",
                    "content": user_input
                })

            # 결과 생성 및 저장
            with st.spinner("처리 중..."):
                result = process_query(
                    user_input,
                    st.session_state.search_flow,
                    st.session_state.performance_monitor
                )

                assistant_message = {
                    "role": "assistant",
                    "search_results": result.get("search_results", {}),
                }

                if not result.get("success") or not result.get("sql"):
                    feedback_message = (
                        "죄송합니다. 질문하신 내용과 관련된 데이터를 찾지 못했습니다. 다음과 같이 질문을 수정해보시는 건 어떨까요?\n\n"
                        "💡 추천 방법:\n"
                        "1. 더 구체적인 용어 사용하기\n"
                        "2. 다른 관점에서 질문하기\n"
                        "3. 사용 가능한 데이터 범위 내에서 질문하기\n\n"
                    )

                    if result.get("available_schemas"):
                        feedback_message += "\n사용 가능한 테이블:\n"
                        for schema in result["available_schemas"]:
                            feedback_message += f"- {schema}\n"

                    assistant_message.update({
                        "feedback": feedback_message,
                        "type": "error",
                        "suggested_questions": [
                            "사용자 상태별 회원 수가 어떻게 되나요?",
                            "최근 한 달간 가입한 회원 수는?",
                            "통신사별 회원 분포를 알려주세요"
                        ]
                    })
                else:
                    assistant_message.update({
                        "type": "success",
                        "sql": result.get("sql", ""),
                        "query_results": result.get("results", [])
                    })

                st.session_state.chat_history.append(assistant_message)
                st.session_state.input_key += 1

    # 메인 컨테이너에 채팅 히스토리 표시
    main_container = st.container()
    input_container = st.container()
    debug_metrics_container = st.container()

    with main_container:
        # 초기 안내 메시지 표시
        if not st.session_state.chat_history:
            st.info("""
            👋 안녕하세요! 데이터베이스에 대해 궁금한 점을 자연어로 질문해주세요.
            
            예시:
            - "사용자 상태가 NORMAL인 회원 수를 알려줘"
            - "최근 한 달간 가입한 회원의 통신사 분포가 어떻게 되나요?"
            - "외국인 회원의 직업 분포를 보여주세요"
            """)

        # 채팅 히스토리 표시
        for msg_idx, message in enumerate(st.session_state.chat_history):
            if message["role"] == "user":
                with st.chat_message("user", avatar="🧑‍💻"):
                    st.write(message["content"])
            else:
                with st.chat_message("assistant", avatar="🤖"):
                    if message.get("type") == "error":
                        st.error(message["feedback"])
                        if message.get("suggested_questions"):
                            st.write("💡 이런 질문은 어떠세요?")
                            for q_idx, question in enumerate(message["suggested_questions"]):
                                button_key = f"suggest_{msg_idx}_{q_idx}"
                                if st.button(question, key=button_key):
                                    st.session_state[f"user_input_{st.session_state.input_key}"] = question
                                    handle_input()
                    else:
                        if "search_results" in message and message["search_results"]:
                            with st.expander("📊 관련 스키마 정보", expanded=False):
                                st.json(message["search_results"])

                        if "sql" in message and message["sql"]:
                            # SQL 쿼리 표시
                            st.markdown("### 🔍 생성된 SQL")

                            # 개선된 쿼리인 경우 표시
                            if message.get("is_refined"):
                                st.info("🔄 이 쿼리는 피드백을 반영하여 개선되었습니다.")
                                if "explanation" in message:
                                    st.markdown("#### 📝 개선 설명")
                                    st.write(message["explanation"]["korean"])

                            st.code(message["sql"], language="sql")

                        if "query_results" in message and message["query_results"]:
                            st.markdown("### 📈 쿼리 결과")
                            st.dataframe(message["query_results"])

                            # 쿼리 개선 섹션
                            st.markdown("### 🔧 쿼리 개선")
                            col1, col2 = st.columns([4, 1])
                            with col1:
                                feedback_key = f"sql_feedback_{msg_idx}"
                                feedback = st.text_area(
                                    "쿼리 개선을 위한 피드백을 입력하세요",
                                    key=feedback_key,
                                    placeholder="예: 결과를 날짜 기준으로 정렬해주세요, NULL 값 처리가 필요합니다 등"
                                )
                            with col2:
                                if st.button("개선하기", key=f"refine_{msg_idx}"):
                                    if feedback.strip():
                                        with st.spinner("쿼리 개선 중..."):
                                            refined_result = st.session_state.search_flow.sql_generator.refine_sql(
                                                message["sql"],
                                                feedback
                                            )

                                            if "error" not in refined_result:
                                                # 개선된 SQL로 새로운 쿼리 실행
                                                new_results = st.session_state.redshift_manager.execute_query(
                                                    refined_result["sql"]
                                                )

                                                # 새로운 결과를 채팅 히스토리에 추가
                                                st.session_state.chat_history.append({
                                                    "role": "assistant",
                                                    "type": "success",
                                                    "sql": refined_result["sql"],
                                                    "query_results": new_results,
                                                    "explanation": refined_result["explanation"],
                                                    "is_refined": True,  # 개선된 쿼리임을 표시
                                                    "original_query_idx": msg_idx  # 원본 쿼리 참조
                                                })
                                                st.rerun()  # UI 새로고침
                                            else:
                                                st.error(f"쿼리 개선 실패: {refined_result['error']}")
                                    else:
                                        st.warning("피드백을 입력해주세요.")

                            # 피드백 저장 UI
                            st.markdown("---")
                            col1, col2, col3 = st.columns([3, 2, 1])
                            with col1:
                                st.info("🤔 이 질의와 결과가 도움이 되었나요?")
                            with col2:
                                feedback_key = f"feedback_{msg_idx}"
                                if feedback_key not in st.session_state:
                                    st.session_state[feedback_key] = False

                                st.session_state[feedback_key] = st.checkbox(
                                    "향후 비슷한 질문에 활용하기 위해 저장",
                                    key=f"checkbox_{msg_idx}"
                                )
                            with col3:
                                if st.button("저장", key=f"save_{msg_idx}"):
                                    if st.session_state[feedback_key]:
                                        # 피드백 저장 처리
                                        feedback_data = {
                                            "query": st.session_state.chat_history[msg_idx-1]["content"],
                                            "sql": message["sql"],
                                            "query_results": message["query_results"],
                                            "metadata": {
                                                "performance_metrics": {
                                                    "execution_time": st.session_state.performance_monitor.get_last_duration()
                                                }
                                            }
                                        }

                                        try:
                                            feedback_result = st.session_state.search_flow.feedback_handler.save_feedback(feedback_data)

                                            if feedback_result["success"]:
                                                st.success("✅ 피드백이 저장되었습니다!")
                                            else:
                                                st.error(f"❌ 저장 실패: {feedback_result['message']}")
                                        except Exception as e:
                                            st.error(f"❌ 저장 중 오류 발생: {str(e)}")
                                    else:
                                        st.warning("저장 옵션을 선택해주세요.")

    # 입력 컨테이너
    with input_container:
        st.markdown("---")

        col1, col2 = st.columns([6, 1])

        with col1:
            st.text_input(
                "질문을 입력하세요",
                key=f"user_input_{st.session_state.input_key}",
                placeholder="데이터베이스에 대해 궁금한 점을 자연어로 질문해주세요...",
                label_visibility="collapsed",
                on_change=handle_input
            )

        with col2:
            if st.button("전송", use_container_width=True):
                handle_input()

        # 추가 기능 버튼들
        col3, col4, col5, col6 = st.columns([1, 1, 1, 3])
        with col3:
            if st.button("대화 지우기", type="secondary", use_container_width=True):
                st.session_state.chat_history = []
                st.session_state.input_key = 0
                st.rerun()

        with col4:
            if st.button("디버그 정보", type="secondary", use_container_width=True):
                st.session_state.debug_mode = not st.session_state.debug_mode

        with col5:
            if st.button("성능 메트릭", type="secondary", use_container_width=True):
                st.session_state.show_metrics = not st.session_state.show_metrics

    # 디버그 정보와 성능 메트릭을 별도의 컨테이너에 표시
    with debug_metrics_container:
        col_debug = st.columns([1, 1, 2])

        # 디버그 정보 표시
        if st.session_state.debug_mode:
            st.markdown("### 🔍 Debug Information")
            with st.expander("채팅 히스토리", expanded=False):
                st.json(st.session_state.chat_history)

        # 성능 메트릭 표시
        if st.session_state.show_metrics:
            st.markdown("### 📊 Performance Metrics")
            try:
                metrics = st.session_state.performance_monitor.get_metrics()

                # 요약 메트릭
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("총 작업 수", metrics["summary"]["total_operations"])
                with col2:
                    st.metric("완료", metrics["summary"]["completed"])
                with col3:
                    st.metric("오류", metrics["summary"]["errors"])
                with col4:
                    avg_duration = metrics["summary"].get("average_duration", 0)
                    st.metric("평균 소요 시간", f"{avg_duration:.2f}초")

                # 최근 작업 메트릭 (최대 5개만 표시)
                st.markdown("#### 최근 작업 상세")
                recent_metrics = metrics.get("metrics", [])[-5:]  # 최근 5개만 선택

                for metric in recent_metrics:
                    # 작업 이름을 더 이해하기 쉽게 변환
                    operation_name = {
                        'complete_workflow': '전체 처리 과정',
                        'analyze_intent': '의도 분석',
                        'search_schema': '스키마 검색',
                        'generate_sql': 'SQL 생성',
                        'execute_sql': 'SQL 실행'
                    }.get(metric.get('operation_name', ''), metric.get('operation_name', '알 수 없음'))

                    # 작업 상태 한글화
                    status = {
                        'completed': '완료',
                        'running': '실행 중',
                        'error': '오류'
                    }.get(metric.get('status', ''), '알 수 없음')

                    # 메트릭 표시
                    with st.expander(f"⏱️ {operation_name} ({status})", expanded=False):
                        # 진행 상태 표시
                        if 'duration' in metric:
                            duration = float(metric['duration'])
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                st.progress(min(1.0, duration / 10.0))
                            with col2:
                                st.text(f"{duration:.2f}초")

                        # 주요 정보 표시
                        display_info = {
                            'operation_name': '작업 유형',
                            'status': '상태',
                            'duration': '소요 시간(초)',
                            'error': '오류 내용'
                        }

                        filtered_metric = {}
                        for k, v in metric.items():
                            if k in display_info and v is not None:
                                # 상태 한글화
                                if k == 'status':
                                    v = {
                                        'completed': '완료',
                                        'running': '실행 중',
                                        'error': '오류'
                                    }.get(v, v)
                                # 작업 유형 한글화
                                elif k == 'operation_name':
                                    v = {
                                        'complete_workflow': '전체 처리 과정',
                                        'analyze_intent': '의도 분석',
                                        'search_schema': '스키마 검색',
                                        'generate_sql': 'SQL 생성',
                                        'execute_sql': 'SQL 실행'
                                    }.get(v, v)
                                filtered_metric[display_info[k]] = v

                        st.json(filtered_metric)

            except Exception as e:
                st.error(f"성능 메트릭 표시 중 오류가 발생했습니다: {str(e)}")

def render_data_generation_page():
    """테스트 데이터 생성 페이지 렌더링"""
    st.header("🧪 Generate Test Data")
    st.write("테스트용 가상의 데이터를 생성하고 Redshift에 적재할 수 있습니다.")

    num_rows = st.number_input("Number of rows to generate", min_value=100, max_value=1000000, value=10000, step=1000)
    if st.button("Generate CSV"):
        filename = st.session_state.data_generator.generate_csv(num_rows=num_rows)
        if filename:
            st.success(f"✅ CSV 생성 완료: {filename}")
            st.write("생성된 데이터를 Redshift에 적재하려면 아래 버튼을 클릭하세요.")

    if st.session_state.data_generator:
        if st.button("Load to Redshift"):
            if filename is not None:
                success = st.session_state.data_generator.load_to_redshift(filename)
                if success:
                    st.success("✅ 데이터가 성공적으로 Redshift에 적재되었습니다!")
                else:
                    st.error("❌ 데이터 적재 실패")
            else:
                st.error("CSV 파일을 먼저 생성하세요.")

def main():
    st.set_page_config(
        page_title="Text to SQL Generator",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    init_session_state()
    render_sidebar()

    pages = {
        'upload': render_upload_page,
        'augment': render_augment_page,
        'synonym_dict': render_synonym_dict,
        'clear_indices': render_clear_indices_page,
        'query': render_query_page,
        'data_generation': render_data_generation_page  # 데이터 생성 페이지 추가
    }

    current_page = pages.get(st.session_state.page, render_upload_page)
    current_page()

if __name__ == "__main__":
    main()
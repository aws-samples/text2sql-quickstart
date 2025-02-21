import streamlit as st
import pandas as pd
from typing import Optional, Dict, List, Union
import json
from datetime import datetime

class DisplayManager:
    @staticmethod
    def display_dataframe(df: pd.DataFrame, title: str = None, 
                        height: int = None, use_container_width: bool = True) -> None:
        """데이터프레임을 보기 좋게 표시

        Args:
            df: 표시할 데이터프레임
            title: 표시할 제목
            height: 데이터프레임 높이
            use_container_width: 전체 너비 사용 여부
        """
        try:
            if title:
                st.subheader(title)
            
            # 데이터프레임 정보 표시
            st.markdown("#### 📊 데이터 개요")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write(f"**행 수:** {len(df):,}")
            with col2:
                st.write(f"**열 수:** {len(df.columns):,}")
            with col3:
                st.write(f"**메모리 사용량:** {df.memory_usage().sum() / 1024 / 1024:.2f} MB")
            
            # 메인 데이터프레임 표시
            st.markdown("#### 📋 데이터")
            
            # 데이터프레임 복사 및 스타일링 준비
            styled_df = df.copy()
            
            # type 컬럼이 있는 경우 augmented 타입에 대해 스타일링
            if 'type' in styled_df.columns:
                styled_df['type'] = styled_df['type'].apply(
                    lambda x: f"🔄 {x}" if x == 'augmented' else x
                )
            
            # is_latest 컬럼이 있는 경우 Yes에 대해 스타일링
            if 'is_latest' in styled_df.columns:
                styled_df['is_latest'] = styled_df['is_latest'].apply(
                    lambda x: f"✨ {x}" if x == 'Yes' else x
                )
            
            # 모든 컬럼을 문자열로 변환
            for col in styled_df.columns:
                styled_df[col] = styled_df[col].astype(str)
            
            st.dataframe(
                data=styled_df,
                height=height,
                use_container_width=use_container_width,
                hide_index=True
            )
            
        except Exception as e:
            st.error(f"데이터프레임 표시 중 오류가 발생했습니다: {str(e)}")
            st.write("기본 형식으로 표시:")
            st.write(df)

    @staticmethod
    def display_json(data: Union[Dict, List, str], title: str = None) -> None:
        """JSON 데이터를 보기 좋게 표시

        Args:
            data: 표시할 JSON 데이터
            title: 표시할 제목
        """
        try:
            if title:
                st.subheader(title)

            # 문자열인 경우 JSON으로 파싱
            if isinstance(data, str):
                data = json.loads(data)

            # JSON 데이터 포맷팅
            formatted_json = json.dumps(data, indent=2, ensure_ascii=False)

            # 테이블 정보 표시
            if isinstance(data, dict) and 'database_schema' in data:
                st.markdown("### 📋 Schema Preview")
                for table in data['database_schema'].get('tables', []):
                    st.markdown(f"### Table: {table.get('table_name', 'Unknown')}")

                    # 테이블 기본 정보
                    st.markdown("#### 기본 정보")
                    st.json({
                        "table_name": table.get('table_name'),
                        "description": table.get('description')
                    })

                    # 컬럼 정보
                    if 'columns' in table:
                        st.markdown("#### 컬럼 정보")
                        for col in table['columns']:
                            st.markdown(f"**🔹 {col.get('name', 'Unknown')}**")
                            st.json(col)
                            st.markdown("---")

                    # 샘플 쿼리
                    if 'sample_queries' in table:
                        st.markdown("#### 샘플 쿼리")
                        for idx, query in enumerate(table['sample_queries'], 1):
                            st.markdown(f"**💡 Query {idx}**")
                            st.json(query)
                            st.markdown("---")
            else:
                # 일반 JSON 데이터 표시
                st.json(data)

            # 메타데이터 표시
            if isinstance(data, dict):
                st.markdown("### ℹ️ Metadata")
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"키 개수: {len(data.keys())}")
                with col2:
                    st.write(f"데이터 크기: {len(formatted_json):,} bytes")

        except Exception as e:
            st.error(f"JSON 데이터 표시 중 오류가 발생했습니다: {str(e)}")
            st.write("기본 형식으로 표시:")
            st.write(data)

    @staticmethod
    def display_schema_info(schema_data: Dict, title: str = None) -> None:
        """스키마 정보를 보기 좋게 표시"""
        try:
            if title:
                st.subheader(title)

            for table in schema_data.get('database_schema', {}).get('tables', []):
                st.markdown(f"### 📋 테이블: {table['table_name']}")
                st.write(f"**설명:** {table.get('description', '설명 없음')}")

                # 증강된 테이블 정보
                if 'augmented_table_info' in table:
                    st.markdown("#### 📝 증강된 테이블 정보")
                    st.json(table['augmented_table_info'])

                # 컬럼 정보 표시
                if table.get('columns'):
                    st.markdown("#### 📊 컬럼 정보")

                    # 컬럼 선택을 위한 selectbox 추가
                    column_names = [col.get('name', 'Unknown') for col in table['columns']]
                    selected_column = st.selectbox(
                        "컬럼 선택",
                        column_names,
                        key=f"column_select_{table['table_name']}"
                    )

                    # 선택된 컬럼 정보 표시
                    for col in table['columns']:
                        if col.get('name') == selected_column:
                            col1, col2 = st.columns(2)
                            with col1:
                                st.markdown("**기본 정보**")
                                st.write(f"타입: {col.get('type', '')}")
                                st.write(f"설명: {col.get('description', '')}")
                            with col2:
                                st.markdown("**증강된 정보**")
                                if 'augmented_column_info' in col:
                                    st.json(col['augmented_column_info'])

                # 샘플 쿼리 표시
                if table.get('sample_queries'):
                    st.markdown("#### 💡 샘플 쿼리")
                    for idx, query in enumerate(table['sample_queries'], 1):
                        st.markdown(f"**Query {idx}:** {query.get('natural_language', '')}")
                        st.code(query.get('sql', ''), language='sql')
                        if 'augmented_description' in query:
                            st.markdown("**증강된 설명:**")
                            st.write(query['augmented_description'])

                st.markdown("---")

        except Exception as e:
            st.error(f"스키마 정보 표시 중 오류가 발생했습니다: {str(e)}")
            st.write("기본 형식으로 표시:")
            st.write(schema_data)

    @staticmethod
    def display_error(error: Exception, title: str = "오류가 발생했습니다") -> None:
        """에러 메시지를 보기 좋게 표시

        Args:
            error: 표시할 에러
            title: 표시할 제목
        """
        st.error(title)
        with st.expander("🔍 상세 에러 정보", expanded=True):
            st.write(f"**에러 타입:** {type(error).__name__}")
            st.write(f"**에러 메시지:** {str(error)}")
            st.code(f"{type(error).__name__}: {str(error)}")

    @staticmethod
    def display_success(message: str, title: str = "성공") -> None:
        """성공 메시지를 보기 좋게 표시

        Args:
            message: 표시할 메시지
            title: 표시할 제목
        """
        st.success(f"✅ {title}")
        st.write(message)
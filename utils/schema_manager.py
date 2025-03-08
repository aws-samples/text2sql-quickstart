import json
from datetime import datetime
from typing import Dict, Optional, List, Tuple
import streamlit as st
import redshift_connector
from config import REDSHIFT_CONFIG
from utils.indice_opensearch import OpenSearchManager
from utils.augmentation import SchemaAugmenter

class SchemaManager:
    def __init__(self):
        """Initialize SchemaManager with required configurations"""
        self.config = REDSHIFT_CONFIG
        self._init_tables()

    def _check_and_alter_tables(self) -> bool:
        """Check and update table structures if necessary"""
        try:
            conn = redshift_connector.connect(**self.config)
            cursor = conn.cursor()

            # 스키마 생성
            cursor.execute("CREATE SCHEMA IF NOT EXISTS general_system;")

            # schema_versions 테이블 존재 여부 확인
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 
                    FROM information_schema.tables 
                    WHERE table_schema = 'general_system' 
                    AND table_name = 'schema_versions'
                );
            """)

            table_exists = cursor.fetchone()[0]

            if not table_exists:
                # 테이블이 없는 경우 새로 생성
                cursor.execute("""
                CREATE TABLE general_system.schema_versions (
                    version_id VARCHAR(50) PRIMARY KEY,
                    schema_type VARCHAR(50),
                    version_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by VARCHAR(100),
                    schema_content SUPER,
                    description TEXT,
                    is_latest BOOLEAN DEFAULT FALSE
                );
                """)

            conn.commit()
            return True

        except Exception as e:
            st.error(f"테이블 체크/업데이트 중 오류가 발생했습니다: {str(e)}")
            return False

        finally:
            if 'conn' in locals():
                conn.close()

    def _init_tables(self) -> bool:
        """Initialize database tables"""
        return self._check_and_alter_tables()

    def _validate_schema(self, schema_data: Dict) -> Tuple[bool, str]:
        """Validate schema structure and content"""
        try:
            # database_schema 키 확인
            if 'database_schema' not in schema_data:
                return False, "Missing required key: database_schema"

            # tables 키 확인
            if 'tables' not in schema_data['database_schema']:
                return False, "Missing required key: database_schema.tables"

            # tables가 리스트인지 확인
            if not isinstance(schema_data['database_schema']['tables'], list):
                return False, "tables must be a list"

            # 각 테이블 구조 확인
            for table in schema_data['database_schema']['tables']:
                if not isinstance(table, dict):
                    return False, "Each table must be a dictionary"

                if 'table_name' not in table:
                    return False, "Missing table_name in table definition"

                if 'columns' not in table:
                    return False, f"Missing columns in table: {table.get('table_name', 'unknown')}"

                # columns가 리스트인지 확인
                if not isinstance(table['columns'], list):
                    return False, f"columns must be a list in table: {table['table_name']}"

                # 각 컬럼 구조 확인
                for column in table['columns']:
                    if not isinstance(column, dict):
                        return False, f"Each column must be a dictionary in table: {table['table_name']}"

                    if 'name' not in column:
                        return False, f"Missing column name in table: {table['table_name']}"

                    if 'type' not in column:
                        return False, f"Missing column type in table: {table['table_name']}"

            return True, "Schema validation successful"

        except Exception as e:
            return False, f"Schema validation failed: {str(e)}"

    def save_schema(self, schema_data: Dict, schema_type: str = "base", version_id: str = None, description: str = None) -> bool:
        """Save schema information to Redshift"""
        try:
            conn = redshift_connector.connect(**self.config)
            cursor = conn.cursor()

            # 스키마 검증
            is_valid, validation_message = self._validate_schema(schema_data)
            if not is_valid:
                st.error(f"스키마 검증 실패: {validation_message}")
                return False

            # 버전 ID 생성 또는 사용
            if not version_id:
                version_id = f"v_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # 이전 latest 상태 해제
            cursor.execute("""
            UPDATE general_system.schema_versions 
            SET is_latest = FALSE 
            WHERE schema_type = %s AND is_latest = TRUE
            """, (schema_type,))

            # 새 버전 저장
            cursor.execute("""
            INSERT INTO general_system.schema_versions (
                version_id, schema_type, schema_content, description, 
                is_latest, created_by
            )
            VALUES (%s, %s, JSON_PARSE(%s), %s, TRUE, current_user)
            """, (
                version_id,
                schema_type,
                json.dumps(schema_data, ensure_ascii=False),
                description or f"Schema version created at {datetime.now()}"
            ))

            conn.commit()
            st.success(f"✅ 스키마 버전 {version_id}이(가) 저장되었습니다.")
            return True

        except Exception as e:
            st.error(f"스키마 저장 중 오류가 발생했습니다: {str(e)}")
            return False

        finally:
            if 'conn' in locals():
                conn.close()

    def load_schema_version(self, version_id: str) -> Optional[Dict]:
        """Load specific schema version"""
        try:
            conn = redshift_connector.connect(**self.config)
            cursor = conn.cursor()

            cursor.execute("""
            SELECT schema_content
            FROM general_system.schema_versions
            WHERE version_id = %s
            """, (version_id,))

            result = cursor.fetchone()
            if result:
                # SUPER 타입의 데이터를 파싱
                if isinstance(result[0], str):
                    schema_content = json.loads(result[0])
                else:
                    schema_content = result[0]

                st.success(f"✅ 스키마 버전 {version_id}를 성공적으로 불러왔습니다.")
                return schema_content

            st.warning(f"⚠️ 스키마 버전 {version_id}를 찾을 수 없습니다.")
            return None

        except Exception as e:
            st.error(f"스키마 버전 로드 중 오류가 발생했습니다: {str(e)}")
            st.write("Error details:", e)
            return None

        finally:
            if 'conn' in locals():
                conn.close()

    def get_schema_versions(self, schema_type: str = None) -> List[Dict]:
        """Get schema version history"""
        try:
            conn = redshift_connector.connect(**self.config)
            cursor = conn.cursor()

            # schema_type 필터 조건 수정
            where_clause = "WHERE 1=1"
            params = []
            if schema_type:
                where_clause += " AND schema_type = %s"
                params.append(schema_type)

            query = f"""
            SELECT 
                version_id,
                TO_CHAR(version_timestamp, 'YYYY-MM-DD HH24:MI:SS') as version_timestamp,
                created_by,
                description,
                schema_type,
                is_latest
            FROM general_system.schema_versions
            {where_clause}
            ORDER BY version_timestamp DESC
            """

            cursor.execute(query, tuple(params))

            columns = ['version_id', 'timestamp', 'created_by', 'description', 'type', 'is_latest']
            results = []
            for row in cursor.fetchall():
                result = dict(zip(columns, row))
                # is_latest를 Yes/No로 변환
                result['is_latest'] = 'Yes' if result['is_latest'] else 'No'
                results.append(result)

            return results

        except Exception as e:
            st.error(f"스키마 버전 조회 중 오류가 발생했습니다: {str(e)}")
            return []

        finally:
            if 'conn' in locals():
                conn.close()

    def test_connection(self) -> bool:
        """Test database connection"""
        try:
            conn = redshift_connector.connect(**self.config)
            conn.close()
            return True
        except Exception as e:
            st.error(f"데이터베이스 연결 실패: {str(e)}")
            return False
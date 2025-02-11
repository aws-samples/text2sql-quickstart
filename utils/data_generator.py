import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import streamlit as st
import redshift_connector
from typing import Optional, Dict, List
from config import REDSHIFT_CONFIG

class DataGenerator:
    def __init__(self):
        self.config = REDSHIFT_CONFIG
        
        # 상태 값 정의
        self.value_mappings = {
            "user_status": {
                "values": ["INIT", "NORMAL", "LOCK", "HOLD", "DORMANT", "WITHDRAW", 
                          "TEMP", "TEMP_FOR_WALLET", "TEMP_FOR_PAYMENT"],
                "weights": [0.05, 0.6, 0.05, 0.05, 0.1, 0.05, 0.05, 0.025, 0.025]
            },
            "member_type": {
                "values": ["MEMBER", "NON_MEMBER"],
                "weights": [0.8, 0.2]
            },
            "password_status": {
                "values": ["EXIST", "HAD_HISTORY", "NONE"],
                "weights": [0.7, 0.2, 0.1]
            },
            "verification_type": {
                "values": ["PHONE", "BANK", "BANKBOOK", "CARD"],
                "weights": [0.4, 0.3, 0.2, 0.1]
            },
            "verification_status": {
                "values": ["SUCCESS", "FAIL", "CI_CHANGED", "EXPIRED"],
                "weights": [0.8, 0.1, 0.05, 0.05]
            },
            "gender": {
                "values": ["MALE", "FEMALE"],
                "weights": [0.5, 0.5]
            },
            "telecom": {
                "values": ["SKT", "KT", "LGU", "A_SKT", "A_KT", "A_LGU"],
                "weights": [0.3, 0.25, 0.2, 0.1, 0.1, 0.05]
            },
            "occupation": {
                "values": ["OFFICE_WORKER", "HOUSEWIFE_OR_STUDENT", "SOLE_PROPRIETOR", 
                          "CIVIL_SERVANT", "PROFESSIONAL", "VIRTUAL_ASSET_INDUSTRY_WORKER", 
                          "HIGH_RISK_WORKER", "INVESTMENT_INCOME_EARNERS",
                          "PRECIOUS_METAL_SALES_WORKER", "PENSION_BENEFICIARY", "ETC"],
                "weights": [0.3, 0.15, 0.1, 0.1, 0.1, 0.05, 0.05, 0.05, 0.03, 0.05, 0.02]
            },
            "using_purpose": {
                "values": ["SALARY_AND_LIVING_EXPENSES", "PAYING_PRODUCT_AND_SERVICE", 
                          "ETC", "PAYING_CREDIT_CARD_BILL", "BUSINESS_TRANSACTION", 
                          "INHERITANCE_AND_GIFT_TRANSACTION", "SAVING_AND_INVESTMENT",
                          "PAYING_DUES", "LOAN_PRINCIPAL_AND_INTEREST_REPAYMENT"],
                "weights": [0.25, 0.2, 0.1, 0.1, 0.1, 0.05, 0.1, 0.05, 0.05]
            },
            "funding_source": {
                "values": ["EARNED_AND_PENSION_INCOME", "BUSINESS_INCOME", 
                          "INHERITANCE_AND_GIFT", "REAL_ESTATE_TRANSFER_INCOME", 
                          "REAL_ESTATE_RENTAL_INCOME", "RETIREMENT_INCOME", 
                          "STUDY_ABROAD_FUNDS", "FINANCIAL_INCOME", "ETC", ""],
                "weights": [0.2, 0.15, 0.1, 0.1, 0.1, 0.1, 0.05, 0.1, 0.05, 0.05]
            }
        }

    def _generate_realistic_dates(self, num_rows: int) -> Dict[str, List[datetime]]:
        """Generate realistic dates for created_at, updated_at, and last_auth"""
        now = datetime.now()
        
        # created_at 생성 (최근 2년 내)
        created_dates = []
        for _ in range(num_rows):
            date = now - timedelta(
                days=np.random.randint(0, 730),
                hours=np.random.randint(0, 24),
                minutes=np.random.randint(0, 60)
            )
            created_dates.append(date.strftime('%Y-%m-%d %H:%M:%S'))

        # updated_at 생성 (created_at 이후)
        updated_dates = []
        for i in range(num_rows):
            created = datetime.strptime(created_dates[i], '%Y-%m-%d %H:%M:%S')
            date = created + timedelta(
                days=np.random.randint(0, (now - created).days + 1),
                hours=np.random.randint(0, 24),
                minutes=np.random.randint(0, 60)
            )
            updated_dates.append(date.strftime('%Y-%m-%d %H:%M:%S'))

        # last_auth와 device update 생성 (최근 90일 내)
        last_auth_dates = []
        for _ in range(num_rows):
            date = now - timedelta(
                days=np.random.randint(0, 90),
                hours=np.random.randint(0, 24),
                minutes=np.random.randint(0, 60)
            )
            last_auth_dates.append(date.strftime('%Y-%m-%d %H:%M:%S'))

        # 마케팅 및 위치 약관 동의 날짜 생성 (created_at 이후)
        terms_dates = []
        for i in range(num_rows):
            if np.random.random() < 0.7:
                created = datetime.strptime(created_dates[i], '%Y-%m-%d %H:%M:%S')
                date = created + timedelta(
                    days=np.random.randint(0, max(1, (now - created).days)),
                    hours=np.random.randint(0, 24),
                    minutes=np.random.randint(0, 60)
                )
                terms_dates.append(date.strftime('%Y-%m-%d %H:%M:%S'))
            else:
                terms_dates.append(None)

        # KYC 관련 날짜 생성
        kyc_registered_dates = []
        for i in range(num_rows):
            if np.random.random() < 0.8:
                created = datetime.strptime(created_dates[i], '%Y-%m-%d %H:%M:%S')
                date = created + timedelta(days=np.random.randint(1, 30))
                kyc_registered_dates.append(date.strftime('%Y-%m-%d'))
            else:
                kyc_registered_dates.append(None)

        kyc_renewal_dates = []
        for date in kyc_registered_dates:
            if date:
                registered = datetime.strptime(date, '%Y-%m-%d')
                renewal = registered + timedelta(days=365)
                kyc_renewal_dates.append(renewal.strftime('%Y-%m-%d'))
            else:
                kyc_renewal_dates.append(None)
        
        return {
            "created_at": created_dates,
            "updated_at": updated_dates,
            "last_mobile_auth_token_refresh_at": last_auth_dates,
            "last_mobile_device_updated_at": last_auth_dates,
            "marketing_terms_agreed_at": terms_dates,
            "location_terms_agreed_at": terms_dates,
            "enhanced_due_diligence_registered_date": kyc_registered_dates,
            "enhanced_due_diligence_renewal_due_date": kyc_renewal_dates
        }

    def generate_csv(self, num_rows: int = 10000) -> Optional[str]:
        """Generate CSV file with test data"""
        try:
            st.info(f"🔄 {num_rows:,}개의 테스트 데이터 생성 중...")
            
            # 날짜 데이터 생성
            dates = self._generate_realistic_dates(num_rows)
            
            # 기본 데이터 생성
            data = {
                'user_id': [f"USER_{i:06d}" for i in range(num_rows)],
                'user_unique_id': [f"UID_{i:06d}" for i in range(num_rows)],
                'last_mobile_auth_token_refresh_at': dates['last_mobile_auth_token_refresh_at'],
                'user_status': np.random.choice(
                    self.value_mappings['user_status']['values'],
                    num_rows,
                    p=self.value_mappings['user_status']['weights']
                ),
                'member_type': np.random.choice(
                    self.value_mappings['member_type']['values'],
                    num_rows,
                    p=self.value_mappings['member_type']['weights']
                ),
                'password_status': np.random.choice(
                    self.value_mappings['password_status']['values'],
                    num_rows,
                    p=self.value_mappings['password_status']['weights']
                ),
                'fleamarket_user_id': [f"FLEA_{i:06d}" for i in range(num_rows)],
                'created_at': dates['created_at'],
                'updated_at': dates['updated_at'],
                'verification_type': np.random.choice(
                    self.value_mappings['verification_type']['values'],
                    num_rows,
                    p=self.value_mappings['verification_type']['weights']
                ),
                'verification_status': np.random.choice(
                    self.value_mappings['verification_status']['values'],
                    num_rows,
                    p=self.value_mappings['verification_status']['weights']
                ),
                'verification_provider_id': [f"VPI_{i:06d}" if np.random.random() < 0.8 else None for i in range(num_rows)],
                'year_of_birth': [str(np.random.randint(1960, 2005)) if np.random.random() < 0.9 else None for _ in range(num_rows)],
                'gender': np.random.choice(
                    self.value_mappings['gender']['values'],
                    num_rows,
                    p=self.value_mappings['gender']['weights']
                ),
                'is_foreigner': np.random.choice([True, False], num_rows, p=[0.1, 0.9]),
                'telecom': np.random.choice(
                    self.value_mappings['telecom']['values'],
                    num_rows,
                    p=self.value_mappings['telecom']['weights']
                ),
                'normalized_english_name': [f"USER_{i}_EN" if np.random.random() < 0.3 else None for i in range(num_rows)],
                'nationality': ['Korean'] * num_rows,
                'occupation': np.random.choice(
                    self.value_mappings['occupation']['values'],
                    num_rows,
                    p=self.value_mappings['occupation']['weights']
                ),
                'using_purpose': np.random.choice(
                    self.value_mappings['using_purpose']['values'],
                    num_rows,
                    p=self.value_mappings['using_purpose']['weights']
                ),
                'funding_source': np.random.choice(
                    self.value_mappings['funding_source']['values'],
                    num_rows,
                    p=self.value_mappings['funding_source']['weights']
                ),
                'enhanced_due_diligence_renewal_due_date': dates['enhanced_due_diligence_renewal_due_date'],
                'enhanced_due_diligence_registered_date': dates['enhanced_due_diligence_registered_date'],
                'service_type': np.random.choice(['ACCOUNT_WEB', ''], num_rows, p=[0.8, 0.2]),
                'device_name': [f"Device_{i}" if np.random.random() < 0.9 else None for i in range(num_rows)],
                'os_type': np.random.choice(['ANDROID', 'IOS', 'UNKNOWN', ''], 
                                          num_rows, p=[0.45, 0.45, 0.08, 0.02]),
                'os_version': [f"{np.random.randint(8, 15)}.{np.random.randint(0, 9)}" if np.random.random() < 0.9 else None for _ in range(num_rows)],
                'os_version_code': [str(np.random.randint(1000, 9999)) if np.random.random() < 0.9 else None for _ in range(num_rows)],
                'app_version': [f"{np.random.randint(1, 5)}.{np.random.randint(0, 9)}.{np.random.randint(0, 9)}" if np.random.random() < 0.9 else None for _ in range(num_rows)],
                'app_version_code': [str(np.random.randint(100, 999)) if np.random.random() < 0.9 else None for _ in range(num_rows)],
                'last_mobile_device_updated_at': dates['last_mobile_device_updated_at'],
                'marketing_terms_agreed': [True if date else False for date in dates['marketing_terms_agreed_at']],
                'marketing_terms_agreed_at': dates['marketing_terms_agreed_at'],
                'location_terms_agreed': [True if date else False for date in dates['location_terms_agreed_at']],
                'location_terms_agreed_at': dates['location_terms_agreed_at']
            }
            
            # DataFrame 생성
            df = pd.DataFrame(data)
            
            # temp_data 디렉토리 생성
            os.makedirs('temp_data', exist_ok=True)
            
            # CSV 파일로 저장
            filename = f"temp_data/mock_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            df.to_csv(filename, index=False, date_format='%Y-%m-%d %H:%M:%S')
            
            st.success(f"✅ {num_rows:,}개의 테스트 데이터가 생성되었습니다.")
            return filename
            
        except Exception as e:
            st.error(f"데이터 생성 중 오류가 발생했습니다: {str(e)}")
            return None

    def load_to_redshift(self, filename: str) -> bool:
        """Load CSV file to Redshift"""
        conn = None
        try:
            st.write("1️⃣ CSV 파일 읽는 중...")
            # 날짜 컬럼 정의
            date_columns = [
                'last_mobile_auth_token_refresh_at',
                'created_at',
                'updated_at',
                'last_mobile_device_updated_at',
                'marketing_terms_agreed_at',
                'location_terms_agreed_at'
            ]

            # CSV 파일을 딕셔너리 리스트로 읽기
            df = pd.read_csv(filename)
            data = df.to_dict('records')
            total_records = len(data)

            # 날짜 데이터를 datetime으로 변환
            for record in data:
                for col in date_columns:
                    if pd.notna(record[col]):
                        record[col] = pd.to_datetime(record[col]).isoformat()
            st.write(f"📊 총 {total_records:,}개 레코드가 로드되었습니다.")

            st.write("2️⃣ Redshift 연결 중...")
            conn = redshift_connector.connect(**self.config)
            cursor = conn.cursor()

            st.write("3️⃣ 테이블 스키마 확인 중...")
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS gold.mart_user__user_master (
                user_id VARCHAR(100),
                user_unique_id VARCHAR(100),
                last_mobile_auth_token_refresh_at TIMESTAMP,
                user_status VARCHAR(50),
                member_type VARCHAR(50),
                password_status VARCHAR(50),
                fleamarket_user_id VARCHAR(100),
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                verification_type VARCHAR(50),
                verification_status VARCHAR(50),
                verification_provider_id VARCHAR(100),
                year_of_birth VARCHAR(4),
                gender VARCHAR(10),
                is_foreigner BOOLEAN,
                telecom VARCHAR(50),
                normalized_english_name VARCHAR(100),
                nationality VARCHAR(50),
                occupation VARCHAR(100),
                using_purpose VARCHAR(100),
                funding_source VARCHAR(100),
                enhanced_due_diligence_renewal_due_date DATE,
                enhanced_due_diligence_registered_date DATE,
                service_type VARCHAR(50),
                device_name VARCHAR(100),
                os_type VARCHAR(20),
                os_version VARCHAR(20),
                os_version_code VARCHAR(20),
                app_version VARCHAR(20),
                app_version_code VARCHAR(20),
                last_mobile_device_updated_at TIMESTAMP,
                marketing_terms_agreed BOOLEAN,
                marketing_terms_agreed_at TIMESTAMP,
                location_terms_agreed BOOLEAN,
                location_terms_agreed_at TIMESTAMP
            );
            """
            cursor.execute(create_table_sql)
            conn.commit()
            st.success("✅ 테이블 스키마가 확인되었습니다.")

            st.write("4️⃣ 데이터 적재 시작...")
            progress_bar = st.progress(0)
            status_text = st.empty()

            # 배치 크기 설정
            batch_size = 1000
            records_processed = 0

            for i in range(0, total_records, batch_size):
                batch = data[i:i+batch_size]
                
                # 배치 INSERT 쿼리 생성
                values_list = []
                for record in batch:
                    values = []
                    for col, val in record.items():
                        if pd.isna(val):
                            values.append('NULL')
                        elif isinstance(val, bool):
                            values.append(str(val))
                        else:
                            values.append(f"'{str(val)}'")
                    values_list.append(f"({','.join(values)})")

                columns = ','.join(record.keys())
                insert_query = f"""
                    INSERT INTO gold.mart_user__user_master 
                    ({columns})
                    VALUES {','.join(values_list)}
                """
                cursor.execute(insert_query)
                records_processed += len(batch)

                # 진행률 업데이트
                progress = records_processed / total_records
                progress_bar.progress(progress)
                status_text.text(f"⏳ 처리 중... {records_processed:,}/{total_records:,} 레코드")

                # 배치마다 커밋
                conn.commit()

            # 최종 결과 확인
            cursor.execute("SELECT COUNT(*) FROM gold.mart_user__user_master")
            final_count = cursor.fetchone()[0]
            st.success(f"✅ 데이터 적재가 완료되었습니다! 총 {final_count:,}개 레코드가 적재되었습니다.")
            
            return True

        except Exception as e:
            st.error(f"데이터 적재 중 오류가 발생했습니다: {str(e)}")
            if conn:
                conn.rollback()
            return False

        finally:
            if conn:
                conn.close()
                st.write("📡 데이터베이스 연결이 종료되었습니다.")

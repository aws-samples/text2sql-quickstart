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

        # users 테이블 값 매핑
        self.user_value_mappings = {
            "account_status": {"values": ["ACTIVE", "INACTIVE", "SUSPENDED", "DELETED"],
                               "weights": [0.7, 0.1, 0.1, 0.1]},
            "user_type": {"values": ["REGULAR", "GUEST"], "weights": [0.8, 0.2]},
            "password_status": {"values": ["SET", "UNSET", "EXPIRED"], "weights": [0.7, 0.2, 0.1]},
            "auth_method": {"values": ["EMAIL", "PHONE", "CARD"], "weights": [0.5, 0.4, 0.1]},
            "auth_status": {"values": ["VERIFIED", "UNVERIFIED", "EXPIRED"], "weights": [0.8, 0.15, 0.05]},
            "gender": {"values": ["MALE", "FEMALE", "OTHER"], "weights": [0.48, 0.48, 0.04]},
            "occupation": {"values": ["EMPLOYEE", "SELF_EMPLOYED", "STUDENT", "RETIRED", "OTHER"],
                           "weights": [0.4, 0.2, 0.2, 0.1, 0.1]},
            "device_type": {"values": ["ANDROID", "IOS", "WEB"], "weights": [0.45, 0.45, 0.1]}
        }

        # transactions 테이블 값 매핑
        self.transaction_value_mappings = {
            "transaction_type": {"values": ["DEPOSIT", "WITHDRAWAL", "TRANSFER", "PAYMENT", "REFUND", "FEE"],
                                 "weights": [0.2, 0.2, 0.3, 0.2, 0.05, 0.05]},
            "status": {"values": ["PENDING", "COMPLETED", "FAILED", "CANCELLED"], "weights": [0.1, 0.8, 0.05, 0.05]},
            "source_service": {"values": ["APP", "WEB", "BANK", "AGENT", "SYSTEM"],
                               "weights": [0.4, 0.3, 0.15, 0.1, 0.05]},
            "currency": {"values": ["USD", "EUR", "KRW"], "weights": [0.5, 0.3, 0.2]},
            "category": {"values": ["PURCHASE", "TRANSFER", "BILL", "REFUND", "OTHER"],
                         "weights": [0.3, 0.3, 0.2, 0.1, 0.1]},
            "priority": {"values": ["LOW", "MEDIUM", "HIGH"], "weights": [0.5, 0.4, 0.1]}
        }

    def _generate_realistic_dates(self, num_rows: int, is_transaction: bool = False) -> Dict[str, List[str]]:
        """Generate realistic dates for users or transactions"""
        now = datetime.now()
        dates = {}

        # created_at (users: 2년 내, transactions: 1년 내)
        created_dates = []
        for _ in range(num_rows):
            days_range = 365 if is_transaction else 730
            date = now - timedelta(
                days=np.random.randint(0, days_range),
                hours=np.random.randint(0, 24),
                minutes=np.random.randint(0, 60)
            )
            created_dates.append(date.strftime('%Y-%m-%d %H:%M:%S'))
        dates["created_at"] = created_dates

        if not is_transaction:  # users 테이블
            # updated_at (created_at 이후)
            updated_dates = []
            for i in range(num_rows):
                created = datetime.strptime(created_dates[i], '%Y-%m-%d %H:%M:%S')
                date = created + timedelta(
                    days=np.random.randint(0, (now - created).days + 1),
                    hours=np.random.randint(0, 24),
                    minutes=np.random.randint(0, 60)
                )
                updated_dates.append(date.strftime('%Y-%m-%d %H:%M:%S'))
            dates["updated_at"] = updated_dates

            # last_login_at (최근 90일 내)
            last_login_dates = []
            for _ in range(num_rows):
                date = now - timedelta(
                    days=np.random.randint(0, 90),
                    hours=np.random.randint(0, 24),
                    minutes=np.random.randint(0, 60)
                )
                last_login_dates.append(date.strftime('%Y-%m-%d %H:%M:%S'))
            dates["last_login_at"] = last_login_dates

        else:  # transactions 테이블
            # requested_at (created_at 직전)
            requested_dates = []
            for i in range(num_rows):
                created = datetime.strptime(created_dates[i], '%Y-%m-%d %H:%M:%S')
                date = created - timedelta(minutes=np.random.randint(1, 60))
                requested_dates.append(date.strftime('%Y-%m-%d %H:%M:%S'))
            dates["requested_at"] = requested_dates

            # completed_at (created_at 이후, status가 COMPLETED일 경우)
            completed_dates = []
            for i in range(num_rows):
                created = datetime.strptime(created_dates[i], '%Y-%m-%d %H:%M:%S')
                if np.random.choice([True, False], p=[0.8, 0.2]):  # 80% 확률로 completed
                    date = created + timedelta(minutes=np.random.randint(1, 1440))  # 최대 1일 내
                    completed_dates.append(date.strftime('%Y-%m-%d %H:%M:%S'))
                else:
                    completed_dates.append(None)
            dates["completed_at"] = completed_dates

        return dates

    def generate_users_csv(self, num_rows: int = 10000) -> Optional[str]:
        """Generate CSV file with test data for users table"""
        try:
            st.info(f"🔄 {num_rows:,}개의 사용자 테스트 데이터 생성 중...")
            dates = self._generate_realistic_dates(num_rows, is_transaction=False)

            data = {
                'user_id': [f"USER_{i:06d}" for i in range(num_rows)],
                'account_id': [f"ACC_{i:06d}" for i in range(num_rows)],
                'last_login_at': dates['last_login_at'],
                'account_status': np.random.choice(self.user_value_mappings['account_status']['values'], num_rows,
                                                   p=self.user_value_mappings['account_status']['weights']),
                'user_type': np.random.choice(self.user_value_mappings['user_type']['values'], num_rows,
                                              p=self.user_value_mappings['user_type']['weights']),
                'password_status': np.random.choice(self.user_value_mappings['password_status']['values'], num_rows,
                                                    p=self.user_value_mappings['password_status']['weights']),
                'created_at': dates['created_at'],
                'updated_at': dates['updated_at'],
                'auth_method': np.random.choice(self.user_value_mappings['auth_method']['values'], num_rows,
                                                p=self.user_value_mappings['auth_method']['weights']),
                'auth_status': np.random.choice(self.user_value_mappings['auth_status']['values'], num_rows,
                                                p=self.user_value_mappings['auth_status']['weights']),
                'birth_year': [str(np.random.randint(1960, 2005)) if np.random.random() < 0.9 else None for _ in
                               range(num_rows)],
                'gender': np.random.choice(self.user_value_mappings['gender']['values'], num_rows,
                                           p=self.user_value_mappings['gender']['weights']),
                'is_non_resident': np.random.choice([True, False], num_rows, p=[0.1, 0.9]),
                'occupation': np.random.choice(self.user_value_mappings['occupation']['values'], num_rows,
                                               p=self.user_value_mappings['occupation']['weights']),
                'device_type': np.random.choice(self.user_value_mappings['device_type']['values'], num_rows,
                                                p=self.user_value_mappings['device_type']['weights']),
                'app_version': [
                    f"{np.random.randint(1, 5)}.{np.random.randint(0, 9)}.{np.random.randint(0, 9)}" if np.random.random() < 0.9 else None
                    for _ in range(num_rows)]
            }

            df = pd.DataFrame(data)
            os.makedirs('temp_data', exist_ok=True)
            filename = f"temp_data/users_mock_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            df.to_csv(filename, index=False, date_format='%Y-%m-%d %H:%M:%S')
            st.success(f"✅ {num_rows:,}개의 사용자 테스트 데이터가 생성되었습니다.")
            return filename
        except Exception as e:
            st.error(f"데이터 생성 중 오류가 발생했습니다: {str(e)}")
            return None

    def generate_transactions_csv(self, num_rows: int = 10000, user_ids: List[str] = None) -> Optional[str]:
        """Generate CSV file with test data for transactions table"""
        try:
            st.info(f"🔄 {num_rows:,}개의 거래 테스트 데이터 생성 중...")
            dates = self._generate_realistic_dates(num_rows, is_transaction=True)

            # user_ids가 없으면 기본값으로 생성
            if not user_ids:
                user_ids = [f"USER_{i:06d}" for i in range(10000)]

            data = {
                'transaction_id': [f"TXN_{i:06d}" for i in range(num_rows)],
                'user_id': np.random.choice(user_ids, num_rows),
                'amount': [np.random.randint(100, 100000) for _ in range(num_rows)],
                'transaction_type': np.random.choice(self.transaction_value_mappings['transaction_type']['values'],
                                                     num_rows,
                                                     p=self.transaction_value_mappings['transaction_type']['weights']),
                'status': np.random.choice(self.transaction_value_mappings['status']['values'], num_rows,
                                           p=self.transaction_value_mappings['status']['weights']),
                'created_at': dates['created_at'],
                'requested_at': dates['requested_at'],
                'completed_at': dates['completed_at'],
                'external_id': [f"EXT_{i:06d}" if np.random.random() < 0.8 else None for i in range(num_rows)],
                'source_service': np.random.choice(self.transaction_value_mappings['source_service']['values'],
                                                   num_rows,
                                                   p=self.transaction_value_mappings['source_service']['weights']),
                'account_id': [f"ACC_{np.random.randint(1, 1000):03d}" for _ in range(num_rows)],
                'memo': [f"Transaction #{i}" if np.random.random() < 0.7 else None for i in range(num_rows)],
                'parent_transaction_id': [
                    f"TXN_{np.random.randint(0, num_rows):06d}" if np.random.random() < 0.2 else None for _ in
                    range(num_rows)],
                'channel_id': [f"CH_{np.random.randint(1, 1000):03d}" if np.random.random() < 0.5 else None for _ in
                               range(num_rows)],
                'destination_account_id': [f"ACC_{np.random.randint(1, 1000):03d}" if np.random.random() < 0.6 else None
                                           for _ in range(num_rows)],
                'fee_amount': [np.random.randint(10, 1000) if np.random.random() < 0.3 else 0 for _ in range(num_rows)],
                'currency': np.random.choice(self.transaction_value_mappings['currency']['values'], num_rows,
                                             p=self.transaction_value_mappings['currency']['weights']),
                'category': np.random.choice(self.transaction_value_mappings['category']['values'], num_rows,
                                             p=self.transaction_value_mappings['category']['weights']),
                'is_recurring': np.random.choice([True, False], num_rows, p=[0.2, 0.8]),
                'priority': np.random.choice(self.transaction_value_mappings['priority']['values'], num_rows,
                                             p=self.transaction_value_mappings['priority']['weights'])
            }

            df = pd.DataFrame(data)
            os.makedirs('temp_data', exist_ok=True)
            filename = f"temp_data/transactions_mock_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            df.to_csv(filename, index=False, date_format='%Y-%m-%d %H:%M:%S')
            st.success(f"✅ {num_rows:,}개의 거래 테스트 데이터가 생성되었습니다.")
            return filename
        except Exception as e:
            st.error(f"데이터 생성 중 오류가 발생했습니다: {str(e)}")
            return None

    def load_to_redshift(self, filename: str, table_name: str) -> bool:
        """Load CSV file to Redshift"""
        conn = None
        try:
            st.write("1️⃣ CSV 파일 읽는 중...")
            date_columns = ['created_at', 'updated_at', 'last_login_at', 'requested_at', 'completed_at']
            df = pd.read_csv(filename)
            data = df.to_dict('records')
            total_records = len(data)

            for record in data:
                for col in date_columns:
                    if col in record and pd.notna(record[col]):
                        record[col] = pd.to_datetime(record[col]).isoformat()
            st.write(f"📊 총 {total_records:,}개 레코드가 로드되었습니다.")

            st.write("2️⃣ Redshift 연결 중...")
            conn = redshift_connector.connect(**self.config)
            cursor = conn.cursor()

            st.write("3️⃣ 테이블 스키마 확인 중...")
            if table_name == "users":
                create_table_sql = """
                CREATE TABLE IF NOT EXISTS general_system.users (
                    user_id VARCHAR(100),
                    account_id VARCHAR(100),
                    last_login_at TIMESTAMP,
                    account_status VARCHAR(50),
                    user_type VARCHAR(50),
                    password_status VARCHAR(50),
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    auth_method VARCHAR(50),
                    auth_status VARCHAR(50),
                    birth_year VARCHAR(4),
                    gender VARCHAR(10),
                    is_non_resident BOOLEAN,
                    occupation VARCHAR(100),
                    device_type VARCHAR(20),
                    app_version VARCHAR(20)
                );
                """
            elif table_name == "transactions":
                create_table_sql = """
                CREATE TABLE IF NOT EXISTS general_system.transactions (
                    transaction_id VARCHAR(100),
                    user_id VARCHAR(100),
                    amount BIGINT,
                    transaction_type VARCHAR(50),
                    status VARCHAR(50),
                    created_at TIMESTAMP,
                    requested_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    external_id VARCHAR(100),
                    source_service VARCHAR(50),
                    account_id VARCHAR(100),
                    memo VARCHAR(255),
                    parent_transaction_id VARCHAR(100),
                    channel_id VARCHAR(100),
                    destination_account_id VARCHAR(100),
                    fee_amount BIGINT,
                    currency VARCHAR(10),
                    category VARCHAR(50),
                    is_recurring BOOLEAN,
                    priority VARCHAR(20)
                );
                """
            cursor.execute(create_table_sql)
            conn.commit()
            st.success("✅ 테이블 스키마가 확인되었습니다.")

            st.write("4️⃣ 데이터 적재 시작...")
            progress_bar = st.progress(0)
            status_text = st.empty()
            batch_size = 1000
            records_processed = 0

            for i in range(0, total_records, batch_size):
                batch = data[i:i + batch_size]
                values_list = []
                for record in batch:
                    values = [f"'{str(val)}'" if not pd.isna(val) else 'NULL' for val in record.values()]
                    values_list.append(f"({','.join(values)})")
                columns = ','.join(record.keys())
                insert_query = f"INSERT INTO general_system.{table_name} ({columns}) VALUES {','.join(values_list)}"
                cursor.execute(insert_query)
                records_processed += len(batch)
                progress = records_processed / total_records
                progress_bar.progress(progress)
                status_text.text(f"⏳ 처리 중... {records_processed:,}/{total_records:,} 레코드")
                conn.commit()

            cursor.execute(f"SELECT COUNT(*) FROM general_system.{table_name}")
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


if __name__ == "__main__":
    generator = DataGenerator()
    users_file = generator.generate_users_csv(1000)
    if users_file:
        generator.load_to_redshift(users_file, "users")
    transactions_file = generator.generate_transactions_csv(1000)
    if transactions_file:
        generator.load_to_redshift(transactions_file, "transactions")
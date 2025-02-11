import boto3
import redshift_connector
from botocore.exceptions import ClientError
import time

from config import REDSHIFT_CONFIG, AWS_REGION, OPENSEARCH_CONFIG
import streamlit as st

class PackageManager:
    def __init__(self):
        self.redshift_config = REDSHIFT_CONFIG
        self.opensearch_client = boto3.client('opensearch', region_name=AWS_REGION)
        self.s3_client = boto3.client('s3', region_name=AWS_REGION)
        self._init_tables()

    # 패키지 정보 테이블 생성
    def _init_tables(self):
        try:
            create_table_query = """
                CREATE TABLE IF NOT EXISTS synonym_dictionary (
                    package_id VARCHAR(255) NOT NULL,
                    package_name VARCHAR(255) NOT NULL,
                    s3_bucket VARCHAR(255) NOT NULL,
                    s3_key VARCHAR(1024) NOT NULL,
                    domain_name VARCHAR(255),
                    created_at TIMESTAMP DEFAULT GETDATE(),
                    updated_at TIMESTAMP DEFAULT GETDATE(),
                    PRIMARY KEY (package_id)
                );
            """

            conn = redshift_connector.connect(**self.redshift_config)
            cursor = conn.cursor()
            cursor.execute(create_table_query)
            conn.commit()

        except Exception as e:
            print(f"패키지 정보 테이블 생성 중 오류가 발생했습니다: {e}")

    # 도메인 목록
    def list_domain_names(self):
        try:
            domain_names = self.opensearch_client.list_domain_names()
            return domain_names['DomainNames']
        except Exception as e:
            print(f"도메인 목록 조회 중 문제가 발생했습니다. {e}")

    def delete_package(self, package_id: str):
        response = self.opensearch_client.delete_package(
            PackageID=package_id
        )
        return response

    def describe_package(self, package_id: str, domain_name: str):
        package_for_domain = self.opensearch_client.list_packages_for_domain(
            DomainName=domain_name
        )

        all_packages = self.opensearch_client.describe_packages(
            Filters=[
                {
                    'Name': 'PackageID',
                    'Value': [package_id]
                }
            ]
        )

        result = {}
        for package in all_packages['PackageDetailsList']:
            if package['PackageID'] == package_id:
                result['package_id'] = package['PackageID']
                result['package_name'] = package['PackageName']
                result['package_type'] = package['PackageType']
                result['package_status'] = package['PackageStatus']
                break

        for packageDetail in package_for_domain['DomainPackageDetailsList']:
            if packageDetail['PackageID'] == package_id:
                result['domain_package_status'] = packageDetail['DomainPackageStatus']
                result['package_version'] = packageDetail['PackageVersion']
                result['last_updated'] = packageDetail['LastUpdated']
                break

        return result

    def describe_domain(self, domain_name: str):
        domain = self.opensearch_client.describe_domain(
            DomainName=domain_name
        )

        domain_status = domain['DomainStatus']

        result = {
            "domain_id": domain_status['DomainId'],
            "domain_name": domain_status['DomainName'],
            "engine_version": domain_status['EngineVersion'],
            "dashboard_endpoint": domain_status['Endpoint'],
        }

        return result

    def describe_dictionaries(self, domain_name: str):

        packages = self.opensearch_client.list_packages_for_domain(DomainName=domain_name)

        result = []
        try:
            for package in packages['DomainPackageDetailsList']:
                if package['PackageType'] == 'TXT-DICTIONARY':
                    select_package_query = """
                        select package_id
                             , package_name
                             , s3_bucket 
                             , s3_key
                             , domain_name 
                          from synonym_dictionary
                         where package_id = %s
                           and package_name = %s
                    """
                    conn = redshift_connector.connect(**self.redshift_config)
                    cursor = conn.cursor()
                    cursor.execute(select_package_query, (package['PackageID'], package['PackageName']))
                    row = cursor.fetchone()

                    result.append({
                        "package_id": package['PackageID'],
                        "package_name": package['PackageName'],
                        "package_type": package['PackageType'],
                        "domain_package_status": package['DomainPackageStatus'],
                        "package_version": package['PackageVersion'],
                        "last_updated": package['LastUpdated'],
                        "s3_bucket": row[2],
                        "s3_key": row[3]
                    })

        except Exception as e:
            print(f"패키지 정보 조회 중 문제가 발생했습니다: {e}")

        return result

    def _bucket_exists(self, bucket_name: str):
        try:
            self.s3_client.head_bucket(Bucket=bucket_name)
            st.success(f"{bucket_name}의 S3 bucket 이 이미 존재합니다.")
            return True
        except ClientError:
            return False

    def _delete_bucket_objects(self, bucket_name: str):
        try:
            # 버킷의 모든 객체 목록 가져오기
            objects_to_delete = self.s3_client.list_objects_v2(Bucket=bucket_name)

            if 'Contents' in objects_to_delete:
                # 삭제할 객체 목록 생성
                delete_keys = [{'Key': obj['Key']} for obj in objects_to_delete['Contents']]

                # delete_objects API 호출
                response = self.s3_client.delete_objects(
                    Bucket=bucket_name,
                    Delete={'Objects': delete_keys}
                )

                return True

        except ClientError as e:
            st.error(f"S3 버킷 삭제 중 문제가 발생했습니다: {e}")


    def _delete_bucket(self, bucket_name: str):
        try:
            self.s3_client.delete_bucket(
                Bucket=bucket_name
            )
            st.success(f"S3 버킷 '{bucket_name}' 삭제가 완료됐습니다.")
        except ClientError as e:
            st.error(f"S3 버킷 삭제 중 문제가 발생했습니다: {e}")

    def _get_account_id(self):
        # STS 클라이언트를 생성합니다.
        sts_client = boto3.client('sts')
        # 현재 AWS 계정 ID를 가져옵니다.
        return sts_client.get_caller_identity().get('Account')

    # 버킷 생성
    def _create_bucket(self, bucket_name: str):
        try:
            self.s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={
                    'LocationConstraint': AWS_REGION
                }
            )
            st.success(f"S3 버킷 '{bucket_name}' 생성이 완료됐습니다.")
        except ClientError as e:
            st.error(f"S3 버킷 생성 중 문제가 발생했습니다: {e}")

    # 파일 업로드
    def _upload_file(self, file, bucket_name, s3_key):
        try:
            self.s3_client.upload_fileobj(file, bucket_name, s3_key)
            st.success(f"버킷에 텍스트 사전 {s3_key} 업로드가 완료됐습니다.")
        except ClientError as e:
            st.error(f"텍스트 사전 업로드 중 문제가 발생했습니다: {e}")

    def wait_package_associated(self, package_id: str, domain_name: str, timeout=300):
        try:
            start_time = time.time()
            st.info(f"도메인 {OPENSEARCH_CONFIG.get('domain')}에 텍스트 사전 연결 중...")
            while True:
                associating_package = self.describe_package(package_id=package_id, domain_name=domain_name)
                # 도메인과의 연결 상태 확인
                status = associating_package['domain_package_status']
                if status == 'ACTIVE':
                    st.success("텍스트 사전 연결 완료.")
                    return associating_package
                elif status == 'ASSOCIATING':
                    elapsed_time = time.time() - start_time
                    if elapsed_time >= timeout:
                        raise TimeoutError(f"Timed out waiting for package {package_id} to be associated with domain {domain_name}.")
                    time.sleep(10)  # 10초 대기 후 다시 확인
                else:
                    raise Exception(f"Package {package_id} is not associated with the specified domain.")
        except Exception as e:
            st.error({e})
            return False

    def wait_package_dissociated(self, package_id: str, domain_name: str, timeout=300):
        try:
            start_time = time.time()
            st.info(f"도메인 {OPENSEARCH_CONFIG.get('domain')}에 텍스트 사전 연결 해제 중...")
            while True:
                associating_package = self.describe_package(package_id=package_id, domain_name=domain_name)
                # 도메인과의 연결 상태 확인
                if 'domain_package_status' not in associating_package:
                    st.success("텍스트 사전 연결 해제 완료.")
                    return True
                else:
                    status = associating_package['domain_package_status']
                    if status in ['DISSOCIATING', 'ACTIVE', 'ASSOCIATING']:
                        elapsed_time = time.time() - start_time
                        if elapsed_time >= timeout:
                            raise TimeoutError(f"Timed out waiting for package {package_id} to be associated with domain {domain_name}.")
                        time.sleep(10)  # 10초 대기 후 다시 확인
                    else:
                        raise Exception(f"Package {package_id} is not associated with the specified domain.")
        except Exception as e:
            st.error({e})
            return False

    def wait_bucket_objects_deleted(self, bucket_name: str):
        while True:
            objects_remaining = self.s3_client.list_objects_v2(Bucket=bucket_name)
            if 'Contents' not in objects_remaining:
                break  # 더 이상 남아 있는 객체가 없으면 루프 종료
            time.sleep(3)  # 1초 대기 후 다시 확인

        st.success(f"버킷 {bucket_name} 비우기가 완료됐습니다.")
        return True

    def wait_package_available(self, package_id: str, domain_name: str, timeout=300):
        try:
            start_time = time.time()
            st.info("패키지 활성화 대기 중...")
            while True:
                package_available = self.describe_package(package_id=package_id, domain_name=domain_name)
                status = package_available['package_status']

                if status == 'AVAILABLE':
                    st.success("패키지 활성화가 완료됐습니다.")
                    return package_available
                elif status in ['PROCESSING', 'COPYING', 'VALIDATING']:
                    elapsed_time = time.time() - start_time
                    if elapsed_time >= timeout:
                        raise TimeoutError(f"패키지 활성화 대기 시간이 초과됐습니다.")
                    time.sleep(10)  # 10초 대기 후 다시 확인
                else:
                    raise Exception(f"패키지 상태 확인 중 문제가 발생했습니다: {status}")
        except Exception as e:
            st.error({e})
            return False

    # 패키지 삭제
    def delete_dictionary(self, package_id: str, package_name: str, domain_name: str):

        result = {}
        try:
            domain_name = OPENSEARCH_CONFIG.get('domain')
            account_id = self._get_account_id()
            s3_bucket_name = f"{package_name}-{domain_name}-{account_id}"

            # 패키지 도메인에서 연결 해제
            dissociate_response = self._dessociate_package(package_id=package_id, domain_name=domain_name)

            # 연결 해제 대기
            if self.wait_package_dissociated(package_id=package_id, domain_name=domain_name):
                # 패키지 삭제
                delete_response = self.delete_package(package_id=package_id)

                # S3 버킷 비우기
                self._delete_bucket_objects(bucket_name=s3_bucket_name)

                # S3 버킷 제거
                if self.wait_bucket_objects_deleted(bucket_name=s3_bucket_name):
                    self._delete_bucket(bucket_name=s3_bucket_name)
                    delete_query = """
                                       delete from synonym_dictionary 
                                        where package_id = %s
                                   """
                    conn = redshift_connector.connect(**self.redshift_config)
                    cursor = conn.cursor()
                    cursor.execute(delete_query, package_id)
                    conn.commit()
                    st.success(f"텍스트 사전 {package_name} 삭제가 완료됐습니다.")
        except Exception as e:
            print(f"패키지 정보 삭제 중 오류가 발생했습니다: {e}")

        return result

    # 패키지 업데이트
    def update_dictionary(self, package_id: str, package_name: str, synonym_file):
        result = {}
        try:

            domain_name = OPENSEARCH_CONFIG.get('domain')
            account_id = self._get_account_id()
            s3_bucket_name = f"{package_name}-{domain_name}-{account_id}"

            # 새로운 텍스트 사전 업로드
            self._upload_file(
                file=synonym_file,
                bucket_name=s3_bucket_name,
                s3_key=synonym_file.name
            )

            # 패키지 업데이트
            response = self.opensearch_client.update_package(
                PackageID=package_id,
                PackageSource={
                    'S3BucketName': s3_bucket_name,
                    'S3Key': synonym_file.name
                },
                PackageConfiguration={
                    'LicenseRequirement': 'NONE',
                    'ConfigurationRequirement': 'NONE'
                }
            )

            # 패키지 업데이트 여부 확인
            package_available = self.wait_package_available(package_id=package_id, domain_name=domain_name)
            if package_available:
                # 업데이트한 패키지를 도메인에 적용
                associate_response = self._associate_package(
                    package_id=package_id,
                    domain_name=domain_name
                )

                # 적용 여부 확인
                package_associated = self.wait_package_associated(package_id=package_id, domain_name=domain_name)
                if package_associated:
                    # 패키지 정보 수정
                    update_query = """
                                   update synonym_dictionary
                                      set s3_bucket = %s,
                                          s3_key = %s,
                                          updated_at = getdate()
                                    where package_id = %s
                                      and package_name = %s
                               """
                    conn = redshift_connector.connect(**self.redshift_config)
                    cursor = conn.cursor()
                    cursor.execute(update_query, (s3_bucket_name, synonym_file.name, package_id, package_name))
                    conn.commit()
                    st.success(f"텍스트 사전 {package_name} 수정이 완료됐습니다.")

                    result['package_id'] = package_id
                    result['package_name'] = package_name
                    result['bucket_name'] = s3_bucket_name
                    result['synonym_file'] = synonym_file
                    result['domain_name'] = domain_name
                    result['package_version'] = package_available['package_version']
                    result['package_status'] = package_available['package_status']
                    result['domain_package_status'] = package_associated['domain_package_status']
        except Exception as e:
            print(f"패키지 정보 업데이트 중 오류가 발생했습니다: {e}")

        return result

    # 패키지 생성
    def create_dictionary(self, package_name: str, synonym_file):

        result = {}
        try:
            domain_name = OPENSEARCH_CONFIG.get('domain')
            account_id = self._get_account_id()
            s3_bucket_name = f"{package_name}-{domain_name}-{account_id}"

            # 버킷 유무 확인
            if not self._bucket_exists(s3_bucket_name):
                self._create_bucket(s3_bucket_name)

            # 텍스트 사전 업로드
            self._upload_file(file=synonym_file,
                              bucket_name=s3_bucket_name,
                              s3_key=synonym_file.name)

            # 패키지 생성
            package = self.opensearch_client.create_package(
                PackageName=package_name,
                PackageType='TXT-DICTIONARY',
                PackageSource={
                    'S3BucketName': s3_bucket_name,
                    'S3Key': synonym_file.name
                }
            )

            package_id = package['PackageDetails']['PackageID']

            # 패키지 활성화 여부 확인
            package_available = self.wait_package_available(package_id=package_id, domain_name=domain_name)
            if package_available:
                # 패키지를 도메인에 연결
                associate_response = self._associate_package(
                    package_id=package_id,
                    domain_name=domain_name
                )

                # 패키지의 도메인 연결 여부 확인
                package_associated = self.wait_package_associated(package_id=package_id, domain_name=domain_name)

                if package_associated:
                    # 패키지 정보 데이터베이스에 입력
                    insert_query = """
                        INSERT INTO synonym_dictionary (
                            package_id,
                            package_name,
                            s3_bucket,
                            s3_key,
                            domain_name
                        )
                        VALUES (%s, %s, %s, %s, %s)
                    """
                    conn = redshift_connector.connect(**self.redshift_config)
                    cursor = conn.cursor()
                    cursor.execute(insert_query, (package_id, package_name, s3_bucket_name, synonym_file.name, domain_name))
                    conn.commit()

                    result['package_id'] = package_id
                    result['package_name'] = package_name
                    result['bucket_name'] = s3_bucket_name
                    result['synonym_file'] = synonym_file
                    result['domain_name'] = domain_name
                    result['package_version'] = package['package_version']
                    result['package_status'] = package_available['package_status']
                    result['domain_package_status'] = package_associated['domain_package_status']

        except Exception as e:
            print(f"패키지 정보 저장 중 오류가 발생했습니다: {e}")

        return result

    # 패키지 도메인에 연계
    def _associate_package(self, package_id: str, domain_name: str):
        response = self.opensearch_client.associate_package(
            PackageID=package_id,
            DomainName=domain_name,
            AssociationConfiguration={
                'KeyStoreAccessOption': {
                    'KeyStoreAccessEnabled': False
                }
            }
        )

        return response

    def _dessociate_package(self, package_id: str, domain_name: str):
        response = self.opensearch_client.dissociate_package(
            PackageID=package_id,
            DomainName=domain_name
        )

        return response

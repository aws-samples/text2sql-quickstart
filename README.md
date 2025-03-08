# Text2SQL QuickStart
이 프로젝트는 Redshift, OpenSearch, Bedrock을 활용한 Text-to-SQL 시스템을 빠르게 시작할 수 있도록 설계되었습니다. 아래 단계를 따라 환경을 설정하고 실행하세요.
## Prerequisites
- **AWS 계정**: AdministratorAccess 권한을 가진 IAM 사용자 추천.
- **AWS CLI**: 설치 및 설정 완료 (`aws configure` 실행).
- **Python**: 3.8 이상 버전.
- **필수 패키지**: `requirements.txt`에 명시된 의존성 설치 필요.
- **CloudFormation 템플릿**: `cloud-formation/template.yaml` 파일 준비.
- **SSH 키 페어**: EC2 접속을 위해 키 페어 생성 필요.
  - 생성 방법:
    ```bash
    aws ec2 create-key-pair --key-name my-key-pair --query 'KeyMaterial' --output text > my-key-pair.pem
    chmod 400 my-key-pair.pem
    ```
  - 생성 후 my-key-pair.pem 파일을 안전하게 보관.
## Execution Steps
### Install required packages:
```bash
pip install -r requirements.txt
```
* Note : 여러 패키지가 설치됩니다. 환경에 따라 의존성 충돌이 발생할 수 있으니, requirements.txt 파일에서 버전 호환성을 확인하세요.
### Provision AWS Resources
AWS 리소스를 배포하려면 다음 단계를 따르세요.
#### 1. Redshift + OpenSearch 배포
Redshift 클러스터와 OpenSearch 도메인을 CloudFormation으로 배포합니다.
* 템플릿 파일: text2sql-quickstart/cloud-formation.yaml
* 배포 명령어:
```bash
aws cloudformation create-stack \
  --stack-name Text2SQLStack \
  --template-body file://cloud-formation/template.yaml \
  --parameters ParameterKey=MasterUserPassword,ParameterValue=<YourPass123> \
  --region ap-northeast-2
```
MasterUserPassword는 최소 8자 이상, 대문자/소문자/숫자를 포함해야 합니다(예: YourPass123).
배포는 약 10~15분 소요되며, 진행 상황은 AWS Management Console의 CloudFormation에서 확인 가능.
* 출력값 확인:
```bash
aws cloudformation describe-stacks --stack-name Text2SQLStack --query "Stacks[0].Outputs"
```
* RedshiftClusterEndpoint: Redshift 연결 엔드포인트 (예: my-redshift-cluster.xxx.ap-northeast-2.redshift.amazonaws.com:5439).
* RedshiftDatabaseName: Redshift 데이터베이스 이름 (예: dev).
* RedshiftUsername: Redshift 마스터 사용자 이름 (예: admin).
* OpenSearchDomainEndpoint: OpenSearch 엔드포인트 (예: https://search-text2sql-opensearch-xxx.ap-northeast-2.es.amazonaws.com).
* OpenSearchUsername: OpenSearch 마스터 사용자 이름 (예: admin).
* BedrockRoleArn: Bedrock API 호출용 IAM 역할 ARN.

환경 변수 설정:
* 프로젝트 루트의 .env 파일에 CloudFormation 출력값을 반영합니다.
```text
OPENSEARCH_HOST=<OpenSearchDomainEndpoint에서 'https://' 제외한 호스트 부분>
OPENSEARCH_USERNAME=<OpenSearch 마스터 사용자 이름>
OPENSEARCH_PASSWORD=<OpenSearch 마스터 비밀번호>
OPENSEARCH_DOMAIN=<OpenSearchDomainEndpoint에서 도메인 이름만, 예: text2sql-opensearch>
REDSHIFT_HOST=<RedshiftClusterEndpoint에서 포트 제외한 호스트 부분>
REDSHIFT_DATABASE=dev
REDSHIFT_USERNAME=admin
REDSHIFT_PASSWORD=YourPass123
```

* 주의:
  * REDSHIFT_HOST와 OPENSEARCH_HOST는 포트를 제외한 호스트만 입력. 포트는 기본값(5439, 443)으로 설정됨.
  * 비밀번호는 출력값에 없으므로 배포 시 입력한 값을 수동으로 기록할 것.

#### 2. Bedrock 파운데이션 모델 활성화
Bedrock의 Foundation Model은 자동으로 활성화할 수 없습니다. 다음 단계를 따라 필요한 모델을 활성화 하세요.
* AWS 콘솔에서 모델 활성화:
1. AWS Management Console에 로그인.
2. Bedrock 서비스로 이동 → "Model access" 선택.
3. 다음 모델들을 활성화:
    * Anthropic Claude 3.5 Sonnet (anthropic.claude-3-5-sonnet-20240620-v1:0)
    * Amazon Titan Embed Text V2 (amazon.titan-embed-text-v2:0)
    * APAC Anthropic Claude 3.5 Sonnet (apac.anthropic.claude-3-5-sonnet-20240620-v1:0)
4. 각 모델 옆의 "Enable" 버튼을 클릭.
5. 승인 후(즉시 또는 몇 분 소요) 모델 사용 가능.

### Other preparations

#### 1. Schema Information + Sample Queries
* 위치: sample-data/multi_schema_info.json 파일에 Redshift 테이블(users, transactions)의 스키마 정의 포함.
* 사용: Text2SQL 모델이 테이블 구조를 이해하는 데 필요.

### Execution Examples

### 

# Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

# License

This library is licensed under the MIT-0 License. See the LICENSE file.


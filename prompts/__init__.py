import yaml
from pathlib import Path
from typing import Dict, Optional

def load_prompt(category: str, name: str) -> Optional[Dict]:
    """
    지정된 카테고리와 이름의 프롬프트 파일을 로드합니다.
    
    Args:
        category: 프롬프트 카테고리 (예: 'schema', 'sql', 'search')
        name: 프롬프트 파일 이름 (확장자 제외)
    
    Returns:
        Dict: 로드된 프롬프트 데이터
        None: 파일을 찾을 수 없거나 로드 실패시
    """
    try:
        prompt_path = Path(__file__).parent / category / f"{name}.yaml"
        if not prompt_path.exists():
            print(f"프롬프트 파일을 찾을 수 없습니다: {prompt_path}")
            return None
            
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"프롬프트 로드 중 오류 발생: {str(e)}")
        return None

def get_prompt_path(category: str, name: str) -> Path:
    """
    지정된 카테고리와 이름의 프롬프트 파일 경로를 반환합니다.
    
    Args:
        category: 프롬프트 카테고리 (예: 'schema', 'sql', 'search')
        name: 프롬프트 파일 이름 (확장자 제외)
    
    Returns:
        Path: 프롬프트 파일의 전체 경로
    """
    return Path(__file__).parent / category / f"{name}.yaml"

def format_prompt(prompt_template: str, **kwargs) -> str:
    """
    프롬프트 템플릿에 주어진 인자들을 적용합니다.
    JSON 예제의 중괄호는 포맷팅에서 제외됩니다.
    
    Args:
        prompt_template: 프롬프트 템플릿 문자열
        **kwargs: 템플릿에 적용할 키워드 인자들
    
    Returns:
        str: 포맷팅된 프롬프트 문자열
    """
    try:
        # 실제 포맷팅할 플레이스홀더만 임시 토큰으로 변경
        placeholders = {}
        for key in kwargs.keys():
            placeholder = "{" + key + "}"
            if placeholder in prompt_template:
                token = f"__FORMAT_TOKEN_{key}__"
                prompt_template = prompt_template.replace(placeholder, token)
                placeholders[token] = kwargs[key]
        
        # 임시 토큰을 실제 값으로 대체
        result = prompt_template
        for token, value in placeholders.items():
            result = result.replace(token, str(value))
        
        return result
    except Exception as e:
        print(f"프롬프트 포맷팅 중 오류 발생: {str(e)}")
        return prompt_template

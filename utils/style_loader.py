import os
import streamlit as st

class StyleLoader:
    @staticmethod
    def load_css(css_file: str) -> None:
        """CSS 파일을 로드하여 적용"""
        try:
            with open(css_file, 'r', encoding='utf-8') as f:
                css = f.read()
                st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
        except Exception as e:
            st.error(f"CSS 파일 로드 중 오류 발생: {str(e)}")

    @staticmethod
    def load_chat_style() -> None:
        """채팅 인터페이스용 CSS 스타일 로드"""
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        css_path = os.path.join(current_dir, 'static', 'css', 'chat_style.css')
        StyleLoader.load_css(css_path)
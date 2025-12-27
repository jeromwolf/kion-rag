#!/usr/bin/env python3
"""
KION RAG PoC - 서버 실행 스크립트
"""

import uvicorn
from app.data_loader import load_sample_data
from app.rag import rag_pipeline


def main():
    # RAG 초기화 및 샘플 데이터 로드
    rag_pipeline.initialize()

    if rag_pipeline.get_count() == 0:
        print("[Run] 샘플 데이터 로드 중...")
        load_sample_data()

    print(f"[Run] 장비 데이터: {rag_pipeline.get_count()}개")
    print("[Run] 서버 시작: http://localhost:8000")
    print("[Run] API 문서: http://localhost:8000/docs")

    # 서버 실행
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )


if __name__ == "__main__":
    main()

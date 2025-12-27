"""
KION RAG PoC - Sample Data Loader
"""

import json
from pathlib import Path
from typing import List

from .models import Equipment
from .rag import rag_pipeline


# 샘플 장비 데이터 (KION 팹서비스 기반)
SAMPLE_EQUIPMENTS = [
    {
        "equipment_id": "EQ001",
        "name": "Hybrid RTA",
        "name_en": "Hybrid Rapid Thermal Annealer",
        "category": "열처리",
        "part": "Front-end",
        "wafer_sizes": ["4 inch", "6 inch"],
        "materials": ["Si", "SiC", "GaN"],
        "temp_min": 200,
        "temp_max": 1200,
        "description": "급속 열처리 장비로 디스플레이 및 반도체 소자 공정에 사용됩니다. 급속 가열/냉각이 가능하며 다양한 분위기 가스를 지원합니다.",
        "tags": ["RTA", "급속열처리", "어닐링", "활성화"],
        "institution": "KION",
        "location": "A동 2층",
        "reservation_url": "https://kion.or.kr/equipment/EQ001"
    },
    {
        "equipment_id": "EQ002",
        "name": "MOCVD",
        "name_en": "Metal Organic Chemical Vapor Deposition",
        "category": "증착",
        "part": "Front-end",
        "wafer_sizes": ["2 inch", "4 inch", "6 inch"],
        "materials": ["GaN", "AlGaN", "InGaN", "sapphire"],
        "temp_min": 400,
        "temp_max": 1100,
        "description": "GaN 계열 에피 성장용 MOCVD 장비입니다. HEMT, LED, 파워소자용 에피택시 성장이 가능합니다.",
        "tags": ["MOCVD", "에피성장", "GaN", "HEMT", "LED"],
        "institution": "KION",
        "location": "B동 1층",
        "reservation_url": "https://kion.or.kr/equipment/EQ002"
    },
    {
        "equipment_id": "EQ003",
        "name": "ICP-RIE",
        "name_en": "Inductively Coupled Plasma Reactive Ion Etcher",
        "category": "식각",
        "part": "Front-end",
        "wafer_sizes": ["2 inch", "4 inch", "6 inch", "8 inch"],
        "materials": ["Si", "SiO2", "SiN", "GaN", "Al"],
        "temp_min": -10,
        "temp_max": 200,
        "description": "고밀도 플라즈마를 이용한 건식 식각 장비입니다. 이방성 식각이 가능하며 다양한 재료의 미세 패턴 형성에 사용됩니다.",
        "tags": ["ICP", "RIE", "건식식각", "플라즈마", "패터닝"],
        "institution": "KION",
        "location": "A동 3층",
        "reservation_url": "https://kion.or.kr/equipment/EQ003"
    },
    {
        "equipment_id": "EQ004",
        "name": "PECVD",
        "name_en": "Plasma Enhanced Chemical Vapor Deposition",
        "category": "증착",
        "part": "Front-end",
        "wafer_sizes": ["4 inch", "6 inch", "8 inch"],
        "materials": ["SiO2", "SiN", "a-Si"],
        "temp_min": 100,
        "temp_max": 400,
        "description": "플라즈마를 이용한 저온 CVD 장비입니다. 절연막, 패시베이션 막 증착에 사용됩니다.",
        "tags": ["PECVD", "CVD", "절연막", "패시베이션", "저온"],
        "institution": "KION",
        "location": "B동 2층",
        "reservation_url": "https://kion.or.kr/equipment/EQ004"
    },
    {
        "equipment_id": "EQ005",
        "name": "E-beam Evaporator",
        "name_en": "Electron Beam Evaporator",
        "category": "증착",
        "part": "Back-end",
        "wafer_sizes": ["2 inch", "4 inch", "6 inch"],
        "materials": ["Au", "Pt", "Ti", "Ni", "Al", "Cr"],
        "temp_min": 20,
        "temp_max": 200,
        "description": "전자빔을 이용한 금속 박막 증착 장비입니다. 전극, 배선, 반사막 등의 형성에 사용됩니다.",
        "tags": ["E-beam", "금속증착", "전극", "배선"],
        "institution": "KION",
        "location": "A동 1층",
        "reservation_url": "https://kion.or.kr/equipment/EQ005"
    },
    {
        "equipment_id": "EQ006",
        "name": "Sputter",
        "name_en": "DC/RF Magnetron Sputter",
        "category": "증착",
        "part": "Back-end",
        "wafer_sizes": ["4 inch", "6 inch", "8 inch"],
        "materials": ["Al", "Cu", "Ti", "TiN", "W", "ITO"],
        "temp_min": 20,
        "temp_max": 400,
        "description": "마그네트론 스퍼터링 장비입니다. DC 및 RF 스퍼터링이 가능하며 금속 및 투명전극 증착에 사용됩니다.",
        "tags": ["스퍼터", "금속증착", "ITO", "투명전극"],
        "institution": "KION",
        "location": "B동 1층",
        "reservation_url": "https://kion.or.kr/equipment/EQ006"
    },
    {
        "equipment_id": "EQ007",
        "name": "Mask Aligner",
        "name_en": "UV Mask Aligner",
        "category": "리소그래피",
        "part": "Front-end",
        "wafer_sizes": ["2 inch", "4 inch", "6 inch"],
        "materials": ["Si", "GaAs", "sapphire", "glass"],
        "temp_min": 20,
        "temp_max": 150,
        "description": "UV 노광 장비로 마스크 패턴을 포토레지스트에 전사합니다. 접촉식/근접식 노광이 가능합니다.",
        "tags": ["노광", "리소그래피", "마스크", "포토"],
        "institution": "KION",
        "location": "A동 2층",
        "reservation_url": "https://kion.or.kr/equipment/EQ007"
    },
    {
        "equipment_id": "EQ008",
        "name": "Stepper",
        "name_en": "i-line Stepper",
        "category": "리소그래피",
        "part": "Front-end",
        "wafer_sizes": ["6 inch", "8 inch"],
        "materials": ["Si"],
        "temp_min": 20,
        "temp_max": 30,
        "description": "고해상도 스텝 노광 장비입니다. 서브마이크론 패터닝이 가능하며 반도체 소자 제조에 사용됩니다.",
        "tags": ["스테퍼", "노광", "고해상도", "패터닝"],
        "institution": "KION",
        "location": "클린룸 A",
        "reservation_url": "https://kion.or.kr/equipment/EQ008"
    },
    {
        "equipment_id": "EQ009",
        "name": "MBE",
        "name_en": "Molecular Beam Epitaxy",
        "category": "증착",
        "part": "Front-end",
        "wafer_sizes": ["2 inch", "3 inch", "4 inch"],
        "materials": ["GaAs", "InP", "AlGaAs", "InGaAs"],
        "temp_min": 200,
        "temp_max": 700,
        "description": "분자빔 에피택시 장비입니다. III-V 화합물 반도체의 고품질 에피 성장에 사용됩니다.",
        "tags": ["MBE", "에피성장", "GaAs", "III-V", "화합물반도체"],
        "institution": "KION",
        "location": "B동 지하1층",
        "reservation_url": "https://kion.or.kr/equipment/EQ009"
    },
    {
        "equipment_id": "EQ010",
        "name": "ALD",
        "name_en": "Atomic Layer Deposition",
        "category": "증착",
        "part": "Front-end",
        "wafer_sizes": ["4 inch", "6 inch", "8 inch"],
        "materials": ["Al2O3", "HfO2", "TiO2", "ZnO"],
        "temp_min": 80,
        "temp_max": 350,
        "description": "원자층 증착 장비입니다. 고품질 고유전체 박막 및 산화물 박막 증착에 사용됩니다.",
        "tags": ["ALD", "원자층증착", "high-k", "산화물"],
        "institution": "KION",
        "location": "A동 3층",
        "reservation_url": "https://kion.or.kr/equipment/EQ010"
    },
    {
        "equipment_id": "EQ011",
        "name": "Furnace",
        "name_en": "High Temperature Furnace",
        "category": "열처리",
        "part": "Front-end",
        "wafer_sizes": ["4 inch", "6 inch", "8 inch"],
        "materials": ["Si", "SiO2"],
        "temp_min": 400,
        "temp_max": 1200,
        "description": "고온 열처리 퍼니스입니다. 산화, 확산, 어닐링 공정에 사용됩니다.",
        "tags": ["퍼니스", "산화", "확산", "열처리"],
        "institution": "KION",
        "location": "A동 1층",
        "reservation_url": "https://kion.or.kr/equipment/EQ011"
    },
    {
        "equipment_id": "EQ012",
        "name": "SEM",
        "name_en": "Scanning Electron Microscope",
        "category": "분석",
        "part": "분석",
        "wafer_sizes": ["2 inch", "4 inch", "6 inch", "8 inch"],
        "materials": ["Si", "GaN", "metal", "polymer"],
        "temp_min": 20,
        "temp_max": 30,
        "description": "주사전자현미경입니다. 시료 표면의 미세구조 관찰 및 분석에 사용됩니다.",
        "tags": ["SEM", "전자현미경", "표면분석", "미세구조"],
        "institution": "KION",
        "location": "분석동 1층",
        "reservation_url": "https://kion.or.kr/equipment/EQ012"
    },
    {
        "equipment_id": "EQ013",
        "name": "AFM",
        "name_en": "Atomic Force Microscope",
        "category": "분석",
        "part": "분석",
        "wafer_sizes": ["2 inch", "4 inch", "6 inch"],
        "materials": ["Si", "GaN", "thin film"],
        "temp_min": 20,
        "temp_max": 30,
        "description": "원자힘현미경입니다. 나노스케일 표면 형상 및 거칠기 측정에 사용됩니다.",
        "tags": ["AFM", "표면거칠기", "나노", "형상측정"],
        "institution": "KION",
        "location": "분석동 1층",
        "reservation_url": "https://kion.or.kr/equipment/EQ013"
    },
    {
        "equipment_id": "EQ014",
        "name": "XRD",
        "name_en": "X-Ray Diffractometer",
        "category": "분석",
        "part": "분석",
        "wafer_sizes": ["2 inch", "4 inch", "6 inch"],
        "materials": ["Si", "GaN", "thin film", "crystal"],
        "temp_min": 20,
        "temp_max": 30,
        "description": "X선 회절 분석 장비입니다. 박막 및 결정의 구조, 결정성, 응력 분석에 사용됩니다.",
        "tags": ["XRD", "결정구조", "박막분석", "응력"],
        "institution": "KION",
        "location": "분석동 2층",
        "reservation_url": "https://kion.or.kr/equipment/EQ014"
    },
    {
        "equipment_id": "EQ015",
        "name": "Probe Station",
        "name_en": "Manual Probe Station",
        "category": "측정",
        "part": "측정",
        "wafer_sizes": ["2 inch", "4 inch", "6 inch", "8 inch"],
        "materials": ["Si", "GaN", "SiC"],
        "temp_min": -50,
        "temp_max": 200,
        "description": "프로브 스테이션입니다. 반도체 소자의 전기적 특성 측정에 사용됩니다. DC/RF 측정이 가능합니다.",
        "tags": ["프로브", "전기측정", "DC", "RF", "소자특성"],
        "institution": "KION",
        "location": "측정동 1층",
        "reservation_url": "https://kion.or.kr/equipment/EQ015"
    },
    {
        "equipment_id": "EQ016",
        "name": "Wire Bonder",
        "name_en": "Automatic Wire Bonder",
        "category": "패키징",
        "part": "Back-end",
        "wafer_sizes": ["4 inch", "6 inch"],
        "materials": ["Au wire", "Al wire"],
        "temp_min": 20,
        "temp_max": 200,
        "description": "와이어 본더 장비입니다. 칩과 패키지 간의 전기적 연결을 위한 와이어 본딩에 사용됩니다.",
        "tags": ["와이어본딩", "패키징", "Au", "Al"],
        "institution": "KION",
        "location": "패키징동",
        "reservation_url": "https://kion.or.kr/equipment/EQ016"
    },
    {
        "equipment_id": "EQ017",
        "name": "Dicing Saw",
        "name_en": "Automatic Dicing Saw",
        "category": "패키징",
        "part": "Back-end",
        "wafer_sizes": ["4 inch", "6 inch", "8 inch"],
        "materials": ["Si", "sapphire", "glass", "ceramic"],
        "temp_min": 20,
        "temp_max": 30,
        "description": "다이싱 소우 장비입니다. 웨이퍼를 개별 칩으로 절단하는 데 사용됩니다.",
        "tags": ["다이싱", "절단", "칩분리"],
        "institution": "KION",
        "location": "패키징동",
        "reservation_url": "https://kion.or.kr/equipment/EQ017"
    },
    {
        "equipment_id": "EQ018",
        "name": "Wet Etcher",
        "name_en": "Wet Etching Station",
        "category": "식각",
        "part": "Front-end",
        "wafer_sizes": ["2 inch", "4 inch", "6 inch", "8 inch"],
        "materials": ["Si", "SiO2", "metal", "GaN"],
        "temp_min": 20,
        "temp_max": 120,
        "description": "습식 식각 장비입니다. 다양한 화학약품을 사용한 등방성 식각 및 세정에 사용됩니다.",
        "tags": ["습식식각", "화학식각", "세정"],
        "institution": "KION",
        "location": "A동 1층",
        "reservation_url": "https://kion.or.kr/equipment/EQ018"
    },
    {
        "equipment_id": "EQ019",
        "name": "Spin Coater",
        "name_en": "Spin Coater",
        "category": "코팅",
        "part": "Front-end",
        "wafer_sizes": ["2 inch", "4 inch", "6 inch", "8 inch"],
        "materials": ["photoresist", "SOG", "polymer"],
        "temp_min": 20,
        "temp_max": 250,
        "description": "스핀 코터 장비입니다. 포토레지스트 및 각종 코팅막의 균일 도포에 사용됩니다.",
        "tags": ["스핀코팅", "포토레지스트", "도포"],
        "institution": "KION",
        "location": "A동 2층",
        "reservation_url": "https://kion.or.kr/equipment/EQ019"
    },
    {
        "equipment_id": "EQ020",
        "name": "Ellipsometer",
        "name_en": "Spectroscopic Ellipsometer",
        "category": "측정",
        "part": "분석",
        "wafer_sizes": ["2 inch", "4 inch", "6 inch", "8 inch"],
        "materials": ["thin film", "dielectric", "semiconductor"],
        "temp_min": 20,
        "temp_max": 30,
        "description": "분광 엘립소미터입니다. 박막의 두께 및 광학 상수 측정에 사용됩니다.",
        "tags": ["엘립소미터", "박막두께", "광학상수", "굴절률"],
        "institution": "KION",
        "location": "분석동 1층",
        "reservation_url": "https://kion.or.kr/equipment/EQ020"
    }
]


def load_sample_data() -> int:
    """샘플 장비 데이터 로드"""
    equipments = [Equipment(**eq) for eq in SAMPLE_EQUIPMENTS]
    count = rag_pipeline.add_equipments_batch(equipments)
    print(f"[DataLoader] {count}개 장비 데이터 로드 완료")
    return count


def load_from_json(file_path: str) -> int:
    """JSON 파일에서 장비 데이터 로드"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    equipments = [Equipment(**eq) for eq in data]
    count = rag_pipeline.add_equipments_batch(equipments)
    print(f"[DataLoader] {file_path}에서 {count}개 장비 데이터 로드 완료")
    return count


if __name__ == "__main__":
    # 직접 실행 시 샘플 데이터 로드
    load_sample_data()

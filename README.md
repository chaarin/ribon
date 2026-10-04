# ribon

Ti-6Al-4V 밀링 공정에서 4날 코팅 카바이드 엔드밀의 절삭날별 마모를 예측하고,
표면 품질 위험·생산 상황·공구 비용을 전문 Agent들이 분석하여
최적의 공구 유지·검사·교체 행동을 결정하는 Multi-Agent 공구 유지보수 의사결정 시스템

## 데이터

QIT-CEMC 밀링 데이터셋(Force/Torque, Vibration, Sound, Cycle별 Edge 1~4 VBmax)을 사용합니다.
용량 문제로 저장소에는 포함하지 않으며, 받은 파일을 `data/raw/`에 풀어서 사용합니다.
